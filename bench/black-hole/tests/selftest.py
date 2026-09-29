"""Accounting and configuration checks without model calls or Docker."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bench

spec = importlib.util.spec_from_file_location('cell', ROOT / 'container' / 'cell.py')
cell = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cell)


def check():
    _, rules = bench.validate_sources()
    config = bench.read(ROOT / 'benchmark.json')
    planned = bench.schedule(config)
    expected = len(config['models']) * len(config['arms']) * config['repetitions']
    assert len(planned) == expected and len({c['cell_id'] for c in planned}) == expected
    assert planned == bench.schedule(config)
    for model in config['models']:
        group = [c for c in planned if c['model'] == model['id'] and c['effort'] == model['effort']]
        assert {arm: sum(c['arm'] == arm for c in group) for arm in config['arms']} == dict.fromkeys(config['arms'], config['repetitions'])
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch)
        sessions = path / 'sessions'
        sessions.mkdir()
        events = path / 'events.jsonl'
        events.write_text(json.dumps({'type': 'thread.started', 'thread_id': 'root'}) + '\n')
        def session(name, input_tokens, output_tokens, completed=True, rule=None):
            items = [
                {'type': 'session_meta', 'payload': {'id': name, 'source': 'exec' if name == 'root' else {'subagent': {'thread_spawn': {'parent_thread_id': 'root'}}}, 'cli_version': config['codex_version']}},
                {'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol', 'effort': 'medium'}},
                {'type': 'response_item', 'payload': {'role': 'developer', 'content': [{'text': rule or rules['occam']}]}},
                {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': {
                    'input_tokens': input_tokens, 'cached_input_tokens': min(70, input_tokens),
                    'output_tokens': output_tokens, 'reasoning_output_tokens': 10}}}}]
            if completed:
                items.append({'type': 'event_msg', 'payload': {'type': 'task_complete'}})
            (sessions / f'{name}.jsonl').write_text('\n'.join(json.dumps(i) for i in items), encoding='utf-8')
        job = {'arm': 'occam', 'rules': rules['occam'], 'model': 'gpt-6.1-sol', 'effort': 'medium', 'delegation': True}
        session('root', 100, 20)
        session('child', 50, 15)
        metrics = cell.metrics(events, path, job)
        assert metrics['usage']['total_tokens'] == 185  # no double-counted cache or reasoning
        assert metrics['usage_complete'] and metrics['rules_verified'] and metrics['model_effort_verified']
        assert metrics['delegation_verified'] and metrics['delegation_family_verified']
        session('child', 50, 15, completed=False)
        incomplete = cell.metrics(events, path, job)
        assert not incomplete['usage_complete'] and incomplete['usage'] is None
        assert incomplete['observed_usage']['total_tokens'] == 185
        session('child', 50, 15, rule=rules['ponytail'])
        assert not cell.metrics(events, path, job)['rules_verified']
        job['delegation'] = False
        assert not cell.metrics(events, path, job)['delegation_verified']
    print('PASS: frozen sources, balanced schedule, cache/reasoning accounting, child usage, incomplete usage, rule contamination.')


if __name__ == '__main__':
    check()
