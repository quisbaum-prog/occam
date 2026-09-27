"""Run the unchanged Occam scenarios through isolated Codex CLI sessions (stdlib).

Raw sessions stay in the gitignored output directory. Auth is linked only inside
each temporary runtime and removed after the session; never included in exports.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import bench as B
import scenarios as S


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest(path):
    return {str(p.relative_to(path)): digest(p.read_bytes())
            for p in sorted(path.rglob('*')) if p.is_file() and '.git' not in p.parts}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def stream_metrics(path):
    usage, tools, chars, errors = None, {}, 0, []
    for line in path.read_text(errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'turn.completed':
            usage = event.get('usage')
        if event.get('type') in ('error', 'turn.failed'):
            errors.append(event)
        if event.get('type') == 'item.completed':
            item = event.get('item', {})
            kind = item.get('type', '')
            if kind not in ('agent_message', 'reasoning'):
                tools[kind] = tools.get(kind, 0) + 1
                chars += len(item.get('aggregated_output', '') or '')
    return {'root_usage': usage, 'tools': tools, 'tool_calls': sum(tools.values()),
            'tool_result_chars': chars, 'errors': errors}


def rollout_metrics(runtime, arm, instructions):
    sessions, developers = [], []
    for path in sorted((runtime / 'sessions').rglob('*.jsonl')):
        meta, contexts, usage, done, session_developers = {}, [], None, False, []
        for line in path.read_text(errors='replace').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get('payload', {})
            if event.get('type') == 'session_meta' and not meta:
                meta = {k: payload.get(k) for k in ('id', 'source', 'cli_version', 'model_provider')}
            elif event.get('type') == 'turn_context':
                contexts.append({k: payload.get(k) for k in ('model', 'effort')})
            elif event.get('type') == 'event_msg':
                if payload.get('type') == 'token_count' and payload.get('info'):
                    usage = payload['info'].get('total_token_usage')
                if payload.get('type') == 'task_complete':
                    done = True
            elif event.get('type') == 'response_item' and payload.get('role') == 'developer':
                text = '\n'.join(x.get('text', '') for x in payload.get('content', []))
                developers.append(text)
                session_developers.append(text)
        session_text = '\n'.join(session_developers)
        session_rules = {'ponytail': 'PONYTAIL MODE ACTIVE' in session_text,
                         'occam': 'OCCAM MODE (full)' in session_text}
        session_rules_ok = session_rules == {a: a == arm for a in ('ponytail', 'occam')}
        if instructions:
            session_rules_ok = session_rules_ok and instructions.strip() in session_text
        sessions.append({**meta, 'contexts': contexts, 'usage': usage, 'completed': done,
                         'rules_verified': session_rules_ok, 'active_rules': session_rules})
    root = next((s for s in sessions if s['source'] == 'exec'), None)
    context_ok = bool(root and root['contexts']) and all(
        c == {'model': 'gpt-6-astra', 'effort': 'ultra'}
        for s in sessions for c in s['contexts'])
    combined = '\n'.join(developers)
    # Check rule presence against actual injected developer messages, not CLI flags.
    active = {'ponytail': 'PONYTAIL MODE ACTIVE' in combined,
              'occam': 'OCCAM MODE (full)' in combined}
    rules_ok = bool(sessions) and all(s['rules_verified'] for s in sessions)
    usage_complete = bool(sessions) and all(s['usage'] is not None and s['contexts'] for s in sessions)
    return {'sessions': sessions, 'model_effort_verified': context_ok,
            'rules_verified': rules_ok, 'active_rules': active,
            'usage_complete': usage_complete,
            'developer_message_hashes': sorted({digest(t.encode()) for t in developers})}


def one_run(job, args, rules):
    scenario, seed, arm = job
    rd = args.out / f'{scenario}-s{seed}-{arm}-r0'
    if (rd / 'result.json').exists():
        return json.loads((rd / 'result.json').read_text())
    if rd.exists():
        raise RuntimeError(f'Incomplete previous cell: {rd}; preserve and use a fresh output directory')
    rd.mkdir(parents=True)
    # All arms copy one frozen fixture. The generator's set ordering cannot drift.
    fixture = args.out / 'fixtures' / f'{scenario}-s{seed}'
    with tempfile.TemporaryDirectory(prefix='astra-verifier-') as verifier_dir:
        task = S.SCENARIOS[scenario](seed, verifier_dir)
    scratch = Path(tempfile.mkdtemp(prefix='astra-cell-'))
    ws, user_dir, runtime, venv = scratch / 'ws', scratch / 'user', scratch / 'user' / '.codex', scratch / 'venv'
    runtime.mkdir(parents=True)
    shutil.copytree(fixture, ws)
    original = manifest(ws)
    (rd / 'prompt.txt').write_text(task.prompt)
    save(rd / 'initial_manifest.json', original)
    for cmd in (['git', 'init', '-q'], ['git', 'add', '-A'],
                ['git', '-c', 'user.name=bench', '-c', 'user.email=bench@localhost', 'commit', '-qm', 'start']):
        subprocess.run(cmd, cwd=ws, check=True, capture_output=True,
                       env={**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'})
    subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True, capture_output=True)
    auth_link = runtime / 'auth.json'
    auth_link.symlink_to(args.auth)
    env = {k: os.environ[k] for k in ('TMPDIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY',
            'SSL_CERT_FILE', 'NODE_EXTRA_CA_CERTS') if k in os.environ}
    env.update(PATH=f'{venv}/bin:{os.environ["PATH"]}', VIRTUAL_ENV=str(venv),
               HOME=str(user_dir), CODEX_HOME=str(runtime), LANG='en_US.UTF-8',
               PYTHONHASHSEED='1', PYTHONNOUSERSITE='1')
    settings = {'model_reasoning_effort': 'ultra', 'project_doc_max_bytes': 0,
                'features.memories': False, 'memories.use_memories': False,
                'features.hooks': False, 'features.plugins': False,
                'features.remote_plugin': False, 'features.apps': False,
                'features.recommended_plugins': False, 'web_search': 'disabled',
                'approval_policy': 'never', 'sandbox_workspace_write.network_access': True,
                'developer_instructions': rules[arm]}
    cmd = [args.codex, 'exec', '--ignore-user-config', '--ignore-rules', '--json',
           '--model', 'gpt-6-astra', '--sandbox', 'workspace-write', '--cd', str(ws),
           '--output-last-message', str(rd / 'final.txt')]
    for key, value in settings.items():
        cmd.extend(['-c', key + '=' + json.dumps(value)])
    cmd.append('-')
    save(rd / 'invocation.json', {'command': cmd, 'settings': settings,
                                 'scratch': str(scratch), 'fixture_sha256': digest(json.dumps(original, sort_keys=True).encode())})
    t0, timed_out = time.monotonic(), False
    try:
        with (rd / 'events.jsonl').open('w') as out, (rd / 'stderr.txt').open('w') as err:
            proc = subprocess.Popen(cmd, cwd=ws, env=env, stdin=subprocess.PIPE,
                                    stdout=out, stderr=err, start_new_session=True, text=True)
            try:
                proc.communicate(task.prompt, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        duration = round(time.monotonic() - t0, 3)
        final = (rd / 'final.txt').read_text() if (rd / 'final.txt').exists() else ''
        metrics = stream_metrics(rd / 'events.jsonl')
        metadata = rollout_metrics(runtime, arm, rules[arm])
        if (runtime / 'sessions').exists():
            shutil.copytree(runtime / 'sessions', rd / 'sessions')
        try:
            verdict = task.verify(ws, final, str(venv / 'bin' / 'python'))
        except Exception as exc:
            verdict = {'pass': False, 'score': 0, 'notes': f'verifier crashed: {exc!r}'}
        diff, patch = B.diff_stats(ws)
        (rd / 'diff.patch').write_text(patch)
        valid = (proc.returncode == 0 and not timed_out and metrics['root_usage'] is not None
                 and metadata['usage_complete']
                 and metadata['model_effort_verified'] and metadata['rules_verified'])
        result = {'scenario': scenario, 'seed': seed, 'arm': arm, 'rep': 0,
                  'model': 'gpt-6-astra', 'effort': 'ultra', 'backend': 'codex-cli',
                  'exit_code': proc.returncode, 'timed_out': timed_out, 'valid_run': valid,
                  'wall_s': duration, 'final': final, 'cost': None,
                  'rules_sha256': digest(rules[arm].encode()),
                  'fixture_sha256': digest(json.dumps(original, sort_keys=True).encode()),
                  **metrics, **metadata, **diff, **verdict}
        save(rd / 'result.json', result)
        return result
    finally:
        auth_link.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--ponytail', type=Path, required=True)
    ap.add_argument('--auth', type=Path, default=Path.home() / '.codex' / 'auth.json')
    ap.add_argument('--codex', default=shutil.which('codex'))
    ap.add_argument('--seeds', type=int, nargs='+', default=[1, 2])
    ap.add_argument('--arms', default='baseline,ponytail,occam')
    ap.add_argument('--scenarios', default='all')
    ap.add_argument('--jobs', type=int, default=3)
    ap.add_argument('--timeout', type=int, default=1800)
    args = ap.parse_args()
    args.out = args.out.resolve()
    args.auth = args.auth.resolve()
    args.ponytail = args.ponytail.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    assert args.auth.is_file(), 'An authenticated Codex CLI is required'
    assert os.environ.get('PYTHONHASHSEED') == '1', 'Start with PYTHONHASHSEED=1 for reproducible generators'
    root = Path(__file__).resolve().parent.parent
    rules = {'baseline': '', 'occam': subprocess.check_output(
        ['sh', str(root / 'plugin/hooks/occam.sh'), 'session'], text=True,
        env={**os.environ, 'OCCAM_LEVEL': 'full', 'CLAUDE_PLUGIN_ROOT': str(root / 'plugin')}),
        'ponytail': subprocess.check_output(['node', '-e',
            'process.stdout.write(require(process.argv[1]).getPonytailInstructions("full"))',
            str(args.ponytail / 'hooks/ponytail-instructions.js')], text=True)}
    for arm, text in rules.items():
        path = args.out / f'{arm}-instructions.txt'
        if path.exists():
            assert path.read_text() == text, f'Arm rules changed: {arm}'
        else:
            path.write_text(text)
    scens = list(S.SCENARIOS) if args.scenarios == 'all' else args.scenarios.split(',')
    for scenario in scens:
        for seed in args.seeds:
            fixture = args.out / 'fixtures' / f'{scenario}-s{seed}'
            if not fixture.exists():
                fixture.mkdir(parents=True)
                S.SCENARIOS[scenario](seed, fixture)
    jobs = [(s, seed, arm) for s in scens for seed in args.seeds for arm in args.arms.split(',')]
    random.Random(0).shuffle(jobs)
    config = {'model': 'gpt-6-astra', 'effort': 'ultra',
         'cli': subprocess.check_output([args.codex, '--version'], text=True).strip(),
         'python': sys.version, 'seeds': args.seeds, 'jobs': args.jobs,
         'scenario_sha256': digest((root / 'bench/scenarios.py').read_bytes()),
         'repo_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
         'ponytail_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.ponytail, text=True).strip(),
         'runner_sha256': digest(Path(__file__).read_bytes()),
         'planned_cells': len(jobs), 'schedule': [list(job) for job in jobs]}
    config_path = args.out / 'run_config.json'
    if config_path.exists():
        assert json.loads(config_path.read_text()) == config, 'Configuration changed; use a fresh output directory'
    else:
        save(config_path, config)
    with cf.ThreadPoolExecutor(args.jobs) as executor:
        futures = [executor.submit(one_run, job, args, rules) for job in jobs]
        for done, future in enumerate(cf.as_completed(futures), 1):
            r = future.result()
            print(f'[{done}/{len(jobs)}] {r["scenario"]} s{r["seed"]} {r["arm"]}: '
                  f'{"PASS" if r["pass"] else "FAIL"} valid={r["valid_run"]} '
                  f'{r["wall_s"]:.1f}s {r["notes"][:100]}', flush=True)
            if not r['valid_run']:
                print('Infrastructure or isolation check failed; inspect before further runs.', flush=True)
                # Queued futures are cancelled; already-running cells finish and keep evidence.
                for pending in futures:
                    pending.cancel()
                raise RuntimeError('Invalid benchmark session')


if __name__ == '__main__':
    main()
