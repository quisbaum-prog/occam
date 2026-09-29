"""One generation cell. Only its job and one auth file are mounted from the host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def speed_settings(job):
    tier = job.get('service_tier')
    if tier is None:
        return {}
    if tier != 'fast':
        raise ValueError('Unsupported explicit service tier')
    return {'service_tier': tier, 'features.fast_mode': True}


def model_capabilities(runtime, job):
    path = runtime / 'models_cache.json'
    models = json.loads(path.read_text(encoding='utf-8')).get('models', []) if path.is_file() else []
    model = next((m for m in models if m.get('slug') == job['model']), {})
    return {key: model.get(key) for key in
            ('slug', 'supported_reasoning_levels', 'additional_speed_tiers', 'service_tiers')}


def metrics(events, runtime, job):
    stream, root_id, tool_calls, errors = [], None, 0, []
    for line in events.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        stream.append(event)
        if event.get('type') == 'thread.started':
            root_id = event.get('thread_id')
        if event.get('type') in ('error', 'turn.failed'):
            errors.append(event)
        if event.get('type') == 'item.completed':
            tool_calls += event.get('item', {}).get('type') not in ('agent_message', 'reasoning')
    sessions = {}
    for path in sorted((runtime / 'sessions').rglob('*.jsonl')):
        meta, contexts, usage, done, developers, responses = {}, [], None, False, [], {}
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get('payload', {})
            if event.get('type') == 'session_meta':
                # Child rollouts contain a second, inherited parent metadata record.
                # The first metadata identifies the actual thread; never replace it.
                if not meta:
                    meta = payload
                elif payload.get('id') == meta.get('id'):
                    meta.update(payload)
                continue
            if event.get('type') == 'response_item' and payload.get('role') == 'developer':
                # Inherited instructions remain model context even though inherited
                # usage and completion events must not be counted as child activity.
                developers.extend(c.get('text', '') for c in payload.get('content', []))
            boundary = meta.get('subagent_history_start_ordinal')
            if boundary is not None:
                ordinal = event.get('ordinal')
                if ordinal is None or ordinal < boundary:
                    continue
            if event.get('type') == 'turn_context':
                contexts.append({'model': payload.get('model'), 'effort': payload.get('effort')})
            elif event.get('type') == 'token_usage_record' and payload.get('thread_id') == meta.get('id'):
                response_id = payload.get('response_id')
                if response_id and payload.get('usage'):
                    if response_id in responses and responses[response_id] != payload['usage']:
                        raise ValueError('Conflicting duplicate response usage')
                    responses[response_id] = payload['usage']
            elif event.get('type') == 'event_msg':
                if payload.get('type') == 'token_count' and payload.get('info'):
                    usage = payload['info'].get('total_token_usage')
                if payload.get('type') == 'task_complete':
                    done = True
                elif payload.get('type') in ('task_started', 'turn_aborted', 'task_failed'):
                    done = False
        if not meta.get('id'):
            continue
        text = '\n'.join(developers)
        active = {'occam': 'OCCAM MODE (full)' in text,
                  'ponytail': 'PONYTAIL MODE ACTIVE' in text}
        expected = {arm: arm == job['arm'] for arm in active}
        rules_ok = active == expected and (not job['rules'] or job['rules'].strip() in text)
        response_totals = {key: sum(r.get(key, 0) for r in responses.values())
                           for key in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens')}
        response_check = (not responses or usage is not None and
                          all(response_totals[key] == usage.get(key, 0) for key in response_totals))
        record = {
            'id': meta['id'], 'source': meta.get('source'), 'contexts': contexts,
            'usage': usage, 'completed': done, 'active_rules': active,
            'rules_verified': rules_ok, 'cli_version': meta.get('cli_version'),
            'owned_history_start_ordinal': meta.get('subagent_history_start_ordinal'),
            'response_count': len(responses), 'response_usage_verified': response_check}
        if meta['id'] in sessions and sessions[meta['id']] != record:
            raise ValueError('Conflicting duplicate thread rollouts')
        sessions[meta['id']] = record
    session_list = list(sessions.values())
    complete = bool(session_list) and all(s['usage'] and s['completed'] and
                                         s['response_usage_verified'] for s in session_list)
    context_ok = bool(session_list) and all(
        s['contexts'] and all(c == {'model': job['model'], 'effort': job['effort']}
                              for c in s['contexts']) for s in session_list)
    totals = {key: sum((s['usage'] or {}).get(key, 0) for s in session_list)
              for key in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens')}
    totals['total_tokens'] = totals['input_tokens'] + totals['output_tokens']
    root = sessions.get(root_id)
    family = {root_id} if root else set()
    parents = {}
    for sid, session in sessions.items():
        source = session.get('source')
        if sid != root_id and isinstance(source, dict):
            parents[sid] = source.get('subagent', {}).get('thread_spawn', {}).get('parent_thread_id')
    while True:
        expanded = family | {child for child, parent in parents.items() if parent in family}
        if expanded == family:
            break
        family = expanded
    family_ok = bool(root) and root.get('source') == 'exec' and family == set(sessions)
    allow_children = job['delegation'] or job['effort'] == 'ultra'
    return {
        'sessions': session_list, 'session_count': len(session_list),
        'root_id': root_id, 'root_usage': root['usage'] if root else None,
        'observed_usage': totals, 'usage': totals if complete else None,
        'usage_complete': complete,
        'model_effort_verified': context_ok,
        'rules_verified': bool(session_list) and all(s['rules_verified'] for s in session_list),
        'delegation_verified': family_ok and (allow_children or len(session_list) == 1),
        'delegation_family_verified': family_ok, 'delegation_configured': job['delegation'],
        'automatic_ultra_delegation_allowed': job['effort'] == 'ultra',
        'child_session_count': max(0, len(session_list) - 1), 'accounting_version': 2,
        'root_tool_calls': tool_calls, 'errors': errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--job', default='/input/job.json')
    args = parser.parse_args()
    home = Path('/home/bench')
    runtime, ws, out = home / '.codex', home / 'ws', home / 'export'
    if any(p.exists() for p in (runtime, ws, out)):
        raise RuntimeError('Container is not fresh; no cell reuse permitted')
    for path in (runtime, ws, out):
        path.mkdir()
    if args.probe:
        evidence = {'fresh_home': True, 'empty_workspace': not list(ws.iterdir()),
                    'no_personal_skills': not (home / '.agents').exists(),
                    'no_docker_socket': not Path('/var/run/docker.sock').exists(),
                    'uid': os.getuid(),
                    'codex': subprocess.check_output(['codex', '--version'], text=True).strip()}
        save(out / 'probe.json', evidence)
        (ws / 'previous-cell-sentinel').write_text('must never reach the next container')
        print(json.dumps(evidence), flush=True)
        return
    job = json.loads(Path(args.job).read_text(encoding='utf-8'))
    if job['arm'] not in ('base', 'occam', 'ponytail'):
        raise ValueError('Unknown arm')
    auth = runtime / 'auth.json'
    try:
        shutil.copyfile('/run/secrets/auth.json', auth)
        auth.chmod(0o600)
        settings = {
            'model_reasoning_effort': job['effort'], 'approval_policy': 'never',
            'project_doc_max_bytes': 0, 'features.memories': False,
            'memories.use_memories': False, 'features.hooks': False,
            'features.plugins': False, 'features.remote_plugin': False,
            'features.apps': False, 'features.recommended_plugins': False,
            'features.multi_agent': job['delegation'], 'web_search': 'disabled',
            'developer_instructions': job['rules']}
        settings.update(speed_settings(job))
        cmd = ['codex', 'exec', '--ignore-user-config', '--ignore-rules',
               '--skip-git-repo-check', '--json', '--color', 'never',
               '--model', job['model'], '--sandbox', 'danger-full-access',
               '--cd', str(ws), '--output-last-message', str(out / 'final.txt')]
        for key, value in settings.items():
            cmd.extend(['-c', key + '=' + json.dumps(value, ensure_ascii=False)])
        cmd.append('-')
        env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'CODEX_HOME': str(runtime),
               'LANG': 'C.UTF-8', 'PYTHONHASHSEED': '1', 'PYTHONNOUSERSITE': '1'}
        save(out / 'invocation.json', {'settings': settings, 'command': cmd,
             'prompt_sha256': sha(job['prompt'].encode()), 'rules_sha256': sha(job['rules'].encode())})
        started, timed_out = time.monotonic(), False
        with (out / 'events.jsonl').open('w', encoding='utf-8') as stdout, \
                (out / 'stderr.txt').open('w', encoding='utf-8') as stderr:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                    cwd=ws, env=env, start_new_session=True, text=True)
            try:
                proc.communicate(job['prompt'], timeout=job['timeout_s'])
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        duration = round(time.monotonic() - started, 3)
        measured = metrics(out / 'events.jsonl', runtime, job)
        capabilities = model_capabilities(runtime, job)
        save(out / 'model-capabilities.json', capabilities)
        requested_tier = job.get('service_tier')
        speed_supported = (requested_tier is None or
                           requested_tier in (capabilities.get('additional_speed_tiers') or []))
        artifact = ws / 'index.html'
        safe_artifact = artifact.is_file() and not artifact.is_symlink()
        if safe_artifact:
            shutil.copyfile(artifact, out / 'index.html')
        if (runtime / 'sessions').is_dir():
            shutil.copytree(runtime / 'sessions', out / 'sessions')
        result = {
            'cell_id': job['cell_id'], 'model': job['model'], 'effort': job['effort'],
            'service_tier_requested': requested_tier,
            'service_tier_supported': speed_supported,
            'service_tier_served': None,
            'service_tier_evidence': 'explicit CLI configuration and live model catalog; served tier is not exposed in CLI JSON usage',
            'arm': job['arm'], 'repetition': job['repetition'],
            'backend': 'codex-cli', 'comparison': 'full-mode-rule-text',
            'generation_wall_s': duration, 'exit_code': proc.returncode,
            'timed_out': timed_out, 'artifact_present': safe_artifact,
            'artifact_sha256': sha(artifact.read_bytes()) if safe_artifact else None,
            'artifact_bytes': artifact.stat().st_size if safe_artifact else None,
            'prompt_sha256': sha(job['prompt'].encode()),
            'rules_sha256': sha(job['rules'].encode()), 'cost_usd': None, **measured}
        result['valid_run'] = (proc.returncode == 0 and not timed_out and speed_supported and
                              all(measured[k] for k in ('usage_complete', 'model_effort_verified',
                                  'rules_verified', 'delegation_verified')))
        save(out / 'result.json', result)
        print(json.dumps({k: result[k] for k in ('cell_id', 'valid_run', 'artifact_present',
                                                'generation_wall_s')}), flush=True)
    finally:
        auth.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
