"""Docker benchmark runner. Model calls happen only in the explicit run command."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'benchmark.json'
IMAGES = {'agent': 'black-hole-bench-agent:0.159.0', 'render': 'black-hole-bench-render:1.63.0'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def docker(*args, **kwargs):
    return subprocess.run(['docker', *map(str, args)], check=True, **kwargs)


def output(*args):
    return docker(*args, capture_output=True, text=True).stdout.strip()


def validate_sources():
    lock = read(ROOT / 'sources.lock.json')
    rules = {}
    for arm, entry in lock['rules'].items():
        data = (ROOT / entry['file']).read_bytes()
        if sha(data) != entry['sha256']:
            raise RuntimeError(f'Rule source hash changed: {arm}')
        rules[arm] = data.decode('utf-8')
    assert rules['base'] == ''
    assert rules['occam'].startswith('OCCAM MODE (full)')
    assert rules['ponytail'].startswith('PONYTAIL MODE ACTIVE')
    return lock, rules


def build():
    validate_sources()
    for kind in IMAGES:
        docker('build', '-f', ROOT / 'container' / f'{kind}.Dockerfile',
               '-t', IMAGES[kind], ROOT / 'container')
    freeze()


def freeze():
    # Also completes provenance when both builds succeeded but host-side recording failed.
    # Compare actual in-image code with the saved source before accepting existing images.
    for kind, filename in (('agent', 'cell.py'), ('render', 'capture.py')):
        code = ('import hashlib; from pathlib import Path; '
                f'print(hashlib.sha256(Path("/opt/benchmark/{filename}").read_bytes()).hexdigest())')
        actual = output('run', '--rm', '--network', 'none', '--cap-drop', 'ALL',
                        '--entrypoint', 'python3', IMAGES[kind], '-c', code)
        if actual != sha((ROOT / 'container' / filename).read_bytes()):
            raise RuntimeError(f'{kind} image code differs from source. Build again.')
    lock = {'created_utc': datetime.now(timezone.utc).isoformat(),
            'images': {kind: output('image', 'inspect', '--format', '{{.Id}}', tag)
                       for kind, tag in IMAGES.items()},
            'docker_server': json.loads(output('version', '--format', '{{json .Server}}')),
            'source_files': {str(p.relative_to(ROOT)): sha(p.read_bytes())
                 for p in [CONFIG, ROOT / 'prompt.txt', ROOT / 'bench.py',
                           *sorted(p for p in (ROOT / 'container').glob('*') if p.is_file())]}}
    save(ROOT / 'runtime-lock.json', lock)
    print('Both container images built and pinned by image ID.', flush=True)


def runtime():
    lock_path = ROOT / 'runtime-lock.json'
    if not lock_path.exists():
        raise RuntimeError('Container images are not built yet. Run: python bench.py build')
    lock = read(lock_path)
    for kind, image in lock['images'].items():
        output('image', 'inspect', '--format', '{{.Id}}', image)
    for relative, expected in lock['source_files'].items():
        if sha((ROOT / relative).read_bytes()) != expected:
            raise RuntimeError(f'Benchmark source changed since build: {relative}. Build again before a new batch.')
    return lock


def container(kind, config, mounts=(), arguments=(), export=None, timeout=None, log=None):
    """No writable host mount and no Docker socket; export only after the cell stops."""
    image = runtime()['images'][kind]
    name = 'bhbench-' + uuid.uuid4().hex[:16]
    command = ['create', '--name', name, '--label', 'benchmark=gargantua-offline-v1',
               '--init', '--cpus', str(config['cpus']), '--memory', config['memory'],
               '--pids-limit', str(config['pids_limit']), '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--shm-size', '512m',
               '--network', 'none' if kind == 'render' or '--probe' in arguments else 'bridge']
    for source, target in mounts:
        source = Path(source).resolve()
        if not source.exists():
            raise RuntimeError(f'Mount source missing: {source}')
        command.extend(['--mount', f'type=bind,source={source},target={target},readonly'])
    command.extend([image, *arguments])
    container_id = output(*command)
    evidence = json.loads(output('inspect', name))[0]
    safe_inspect = {'id': container_id, 'image': image,
        'network_mode': evidence['HostConfig']['NetworkMode'],
        'cpus_nano': evidence['HostConfig']['NanoCpus'], 'memory': evidence['HostConfig']['Memory'],
        'pids_limit': evidence['HostConfig']['PidsLimit'],
        'mounts': [{'destination': m['Destination'], 'writable': m['RW']} for m in evidence['Mounts']],
        'user': evidence['Config']['User'], 'privileged': evidence['HostConfig']['Privileged']}
    if any(m['writable'] for m in safe_inspect['mounts']):
        raise RuntimeError('Writable host mount is forbidden')
    stream = log.open('w', encoding='utf-8') if log else None
    try:
        started = time.monotonic()
        try:
            process = subprocess.run(['docker', 'start', '--attach', name],
                         stdout=stream, stderr=subprocess.STDOUT if stream else None, timeout=timeout)
        except subprocess.TimeoutExpired:
            docker('kill', name, capture_output=True)
            raise RuntimeError('Container timed out; logs retained, no result fabricated')
        exit_code = int(output('inspect', '--format', '{{.State.ExitCode}}', name))
        safe_inspect.update(exit_code=exit_code, container_wall_s=round(time.monotonic() - started, 3))
        if export:
            export.mkdir(parents=True, exist_ok=True)
            copy = subprocess.run(['docker', 'cp', name + ':/home/bench/export/.', str(export)],
                                  capture_output=True, text=True)
            if copy.returncode and exit_code == 0:
                raise RuntimeError('Container produced no export: ' + copy.stderr)
            save(export / 'container.json', safe_inspect)
        if process.returncode or exit_code:
            raise RuntimeError(f'{kind} container failed ({exit_code}); inspect {log or "its logs"}')
        return safe_inspect
    finally:
        if stream:
            stream.close()
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)


def doctor():
    config = read(CONFIG)
    lock, _ = validate_sources()
    status = {'sources_verified': True, 'prompt_sha256': sha((ROOT / 'prompt.txt').read_bytes()),
              'sources': {arm: lock[arm]['commit'] for arm in ('occam', 'ponytail')},
              'auth_file_available': (Path.home() / '.codex' / 'auth.json').is_file(),
              'docker_available': bool(shutil.which('docker'))}
    try:
        status['docker_server'] = output('version', '--format', '{{.Server.Version}}')
        status['runtime'] = runtime()
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        status['ready'] = False
        status['issue'] = str(exc)
    else:
        status['ready'] = status['auth_file_available']
    save(ROOT / 'SETUP-STATUS.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return status


def smoke():
    config = read(CONFIG)
    runtime()
    run = ROOT / 'runs' / ('smoke-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    run.mkdir(parents=True)
    probes = []
    for arm in ('base', 'occam', 'ponytail'):
        folder = run / arm
        evidence = container('agent', config, arguments=['--probe'], export=folder,
                             timeout=90, log=run / f'{arm}.log')
        probe = read(folder / 'probe.json')
        assert probe['fresh_home'] and probe['empty_workspace'] and probe['no_personal_skills']
        assert probe['no_docker_socket'] and probe['uid'] != 0
        probes.append(evidence)
    assert len({p['id'] for p in probes}) == 3
    render = run / 'reference'
    render.mkdir()
    shutil.copyfile(ROOT / 'tests' / 'reference.html', render / 'index.html')
    container('render', config, mounts=[(render / 'index.html', '/source/index.html'),
              (CONFIG, '/input/benchmark.json')], arguments=['capture'], export=render / 'render',
              timeout=600, log=run / 'render.log')
    checks = read(render / 'render' / 'checks.json')
    assert all(checks[k] for k in ('offline_load', 'motion_detected', 'pause_stable',
                                  'resume_moves', 'restart_reproducible', 'fits_viewport'))
    # A deliberate broken control checks that the verifier can report failure.
    negative = run / 'negative'
    negative.mkdir()
    shutil.copyfile(ROOT / 'tests' / 'broken.html', negative / 'index.html')
    short_config = {**config, 'capture': {'seconds': 1, 'fps': 2, 'screenshot_second': 0}}
    save(negative / 'benchmark.json', short_config)
    container('render', config, mounts=[(negative / 'index.html', '/source/index.html'),
              (negative / 'benchmark.json', '/input/benchmark.json')], arguments=['capture'],
              export=negative / 'render', timeout=90, log=run / 'negative.log')
    bad_checks = read(negative / 'render' / 'checks.json')
    assert not bad_checks['pause_stable'] and not bad_checks['restart_reproducible']
    evidence = {'passed': True, 'model_calls': 0, 'distinct_container_ids': [p['id'] for p in probes],
                'reference_checks': checks, 'negative_checks': bad_checks,
                'evidence_folder': str(run), 'generation_tested': False}
    save(ROOT / 'SMOKE-TEST.json', evidence)
    print('Isolation and browser capture checks passed. No model calls made.', flush=True)


def schedule(config, selected=None, repetitions=None):
    models = selected or config['models']
    repetitions = repetitions or config['repetitions']
    cells = []
    for model in models:
        safe = re.sub(r'[^a-zA-Z0-9_-]', '-', model['id'] + '-' + model['effort'])
        for rep in range(1, repetitions + 1):
            for arm in config['arms']:
                cells.append({'cell_id': f'{safe}-{arm}-r{rep}', 'model': model['id'],
                              'effort': model['effort'], 'arm': arm, 'repetition': rep})
                if model.get('service_tier'):
                    cells[-1]['service_tier'] = model['service_tier']
    random.Random(config['schedule_seed']).shuffle(cells)
    for i, cell in enumerate(cells, 1):
        cell['blind_id'] = f'view-{i:03d}'
    return cells


def render_cell(folder, config):
    artifact = folder / 'index.html'
    if not artifact.exists():
        return
    save(folder / 'render-config.json', config)
    container('render', config, mounts=[(artifact, '/source/index.html'),
              (folder / 'render-config.json', '/input/benchmark.json')], arguments=['capture'],
              export=folder / 'render', timeout=config.get('render_timeout_s', 1800), log=folder / 'render.log')


def run(args):
    config = read(CONFIG)
    if args.model:
        models = [{'id': args.model, 'effort': args.effort or 'medium'}]
    elif args.effort:
        raise RuntimeError('--effort requires --model')
    else:
        models = config['models']
    if args.service_tier:
        models = [{**model, 'service_tier': args.service_tier} for model in models]
    repetitions = config['repetitions'] if args.repetitions is None else args.repetitions
    if repetitions < 1:
        raise RuntimeError('Repetitions must be positive')
    lock, rules = validate_sources()
    planned = schedule(config, models, repetitions)
    target = (args.out or ROOT / 'runs' / datetime.now().strftime('models-%Y%m%d-%H%M%S')).resolve()
    if args.dry_run:
        print(json.dumps({'model_calls': len(planned), 'schedule': planned, 'out': str(target)}, indent=2))
        return
    active_runtime = runtime()
    if target.exists():
        raise RuntimeError('Output folder already exists. Preserve it and choose a fresh folder.')
    auth = args.auth.resolve()
    if not auth.is_file():
        raise RuntimeError('Codex CLI auth.json is missing. Sign in with Codex before running.')
    target.mkdir(parents=True)
    manifest = {'benchmark_id': config['benchmark_id'], 'models': models,
                'repetitions': repetitions, 'schedule': planned, 'config': config,
                'runtime': active_runtime, 'sources': lock,
                'prompt_sha256': sha((ROOT / 'prompt.txt').read_bytes()),
                'generation_policy': 'fresh container per cell, one attempt, sequential, full rules'}
    save(target / 'manifest.json', manifest)
    shutil.copyfile(ROOT / 'prompt.txt', target / 'prompt.txt')
    print(f'{len(planned)} container runs planned; each gets a fresh container.', flush=True)
    for index, cell in enumerate(planned, 1):
        folder = target / 'cells' / cell['cell_id']
        folder.mkdir(parents=True)
        job = {**cell, 'prompt': (ROOT / 'prompt.txt').read_text(encoding='utf-8'),
               'rules': rules[cell['arm']], 'delegation': config['delegation'],
               'timeout_s': config['timeout_s']}
        save(folder / 'job.json', job)
        print(f'[{index}/{len(planned)}] {cell["model"]} {cell["effort"]} {cell["arm"]} r{cell["repetition"]}', flush=True)
        container('agent', config, mounts=[(folder / 'job.json', '/input/job.json'),
                  (auth, '/run/secrets/auth.json')], export=folder,
                  timeout=config['timeout_s'] + 120, log=folder / 'container.log')
        result = read(folder / 'result.json')
        if not result['valid_run']:
            report(target)
            raise RuntimeError('Isolation, model, rule, or usage verification failed. Evidence preserved; batch stopped.')
        # Rendering is delayed until all generation calls finish, avoiding capture load during model timing.
    if not args.no_render:
        for cell in planned:
            render_cell(target / 'cells' / cell['cell_id'], config)
        compose(target)
    report(target)
    print('Finished: ' + str(target / 'report.md'), flush=True)


def compose(target):
    manifest = read(target / 'manifest.json')
    container('render', manifest['config'], mounts=[(target, '/run-data'),
              (CONFIG, '/input/benchmark.json')], arguments=['compose'],
              export=target / 'comparison', timeout=600, log=target / 'comparison.log')


def report(target):
    manifest = read(target / 'manifest.json')
    results = []
    for cell in manifest['schedule']:
        path = target / 'cells' / cell['cell_id'] / 'result.json'
        if path.exists():
            result = read(path)
            checks = path.parent / 'render' / 'checks.json'
            if checks.exists():
                result['browser_checks'] = read(checks)
            results.append(result)
    with (target / 'results.jsonl').open('w', encoding='utf-8') as stream:
        for result in results:
            public = {k: v for k, v in result.items() if k not in ('sessions', 'root_id', 'errors')}
            stream.write(json.dumps(public, ensure_ascii=False) + '\n')
    lines = ['# Schwarzes-Loch-Benchmark', '',
             'Full-mode rule-text comparison in Codex. Visual scores are pending independent review.', '',
             '| Model | Effort | Arm | Valid / planned | Median total tokens | Median generation seconds |',
             '|---|---|---|---:|---:|---:|']
    for model in manifest['models']:
        for arm in ('base', 'occam', 'ponytail'):
            group = [r for r in results if r['model'] == model['id'] and r['effort'] == model['effort'] and r['arm'] == arm]
            valid = [r for r in group if r['valid_run'] and r.get('usage_complete')]
            tokens = statistics.median(r['usage']['total_tokens'] for r in valid) if valid else 'unavailable'
            seconds = statistics.median(r['generation_wall_s'] for r in group) if group else 'unavailable'
            lines.append(f'| {model["id"]} | {model["effort"]} | {arm} | {len(valid)}/{manifest["repetitions"]} | {tokens} | {seconds} |')
    lines.extend(['', 'Input includes cached input. Output includes reasoning; neither is added twice.',
                  'All unique root and child sessions are counted; incomplete usage has no total.',
                  'Generation time and rendering time are separate. Subscription tokens are not converted to dollars.',
                  'Small repeated samples and one visual task do not establish general model quality.', '',
                  'Each repetition is retained. No best-looking run is selected automatically.'])
    (target / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    cards = []
    for cell in manifest['schedule']:
        folder = target / 'cells' / cell['cell_id']
        label = html.escape(f'{cell["model"]} / {cell["effort"]} / {cell["arm"]} / r{cell["repetition"]}')
        relative = folder.relative_to(target).as_posix()
        if (folder / 'render' / 'clip.mp4').exists():
            content = f'<video controls loop muted src="{relative}/render/clip.mp4"></video>'
        else:
            content = '<p>No video available.</p>'
        cards.append(f'<article><h2>{label}</h2>{content}<a href="{relative}/index.html">Open original HTML</a></article>')
    gallery = ('<!doctype html><meta charset="utf-8"><title>Black-hole benchmark</title>'
               '<style>body{background:#101018;color:#eee;font:16px system-ui;margin:24px}'
               'main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}'
               'h2{font-size:15px}video{width:100%}a{color:#c9b0ff}</style>'
               '<h1>Black-hole benchmark</h1><button onclick="document.querySelectorAll(\'video\').forEach(v=>v.play())">Play all</button> '
               '<button onclick="document.querySelectorAll(\'video\').forEach(v=>v.pause())">Pause all</button> '
               '<button onclick="document.querySelectorAll(\'video\').forEach(v=>{v.currentTime=0;v.play()})">Restart all</button>'
               '<main>' + ''.join(cards) + '</main>')
    (target / 'gallery.html').write_text(gallery, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('build', 'freeze', 'doctor', 'smoke'):
        commands.add_parser(command)
    runner = commands.add_parser('run')
    runner.add_argument('--model')
    runner.add_argument('--effort', choices=['low', 'medium', 'high', 'xhigh', 'max', 'ultra'])
    runner.add_argument('--service-tier', choices=['fast'], help='Explicit speed setting for every arm in this batch')
    runner.add_argument('--repetitions', type=int)
    runner.add_argument('--out', type=Path)
    runner.add_argument('--auth', type=Path, default=Path.home() / '.codex' / 'auth.json')
    runner.add_argument('--dry-run', action='store_true')
    runner.add_argument('--no-render', action='store_true')
    for command in ('render', 'report'):
        sub = commands.add_parser(command)
        sub.add_argument('folder', type=Path)
    args = parser.parse_args()
    if args.command == 'build':
        build()
    elif args.command == 'freeze':
        freeze()
    elif args.command == 'doctor':
        doctor()
    elif args.command == 'smoke':
        smoke()
    elif args.command == 'run':
        run(args)
    elif args.command == 'report':
        report(args.folder.resolve())
    else:
        target = args.folder.resolve()
        manifest = read(target / 'manifest.json')
        for cell in manifest['schedule']:
            folder = target / 'cells' / cell['cell_id']
            if not (folder / 'render' / 'checks.json').exists():
                render_cell(folder, manifest['config'])
        compose(target)
        report(target)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, AssertionError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
