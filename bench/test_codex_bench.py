"""Small offline checks for benchmark attribution and isolation guards."""
import json
from pathlib import Path
import tempfile

from codex_bench import rollout_metrics, stream_metrics
from report_codex import public_row, scrub_values


def event(kind, **payload):
    return {'type': kind, 'payload': payload}


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sessions = root / 'sessions'
        sessions.mkdir()
        usage = {'input_tokens': 20, 'cached_input_tokens': 10,
                 'output_tokens': 8, 'reasoning_output_tokens': 5}
        rules = 'OCCAM MODE (full). Test rules.'
        context = event('turn_context', model='gpt-6-astra', effort='ultra')
        developer = event('response_item', role='developer', content=[{'text': rules}])
        count = event('event_msg', type='token_count', info={'total_token_usage': usage})
        done = event('event_msg', type='task_complete')
        def write(name, records):
            (sessions / name).write_text('\n'.join(map(json.dumps, records)))
        write('root.jsonl', [event('session_meta', id='root', source='exec'),
                            context, developer, count, done])
        write('child.jsonl', [event('session_meta', id='child', source={'subagent': {}}),
                             event('session_meta', id='root', source='exec'), context, count, done])
        metrics = rollout_metrics(root, 'occam', rules)
        assert not metrics['rules_verified'], 'A child without rules must not pass isolation'
        assert {s['id'] for s in metrics['sessions']} == {'root', 'child'}
        write('child.jsonl', [event('session_meta', id='child', source={'subagent': {}}),
                             context, developer, count, done])
        metrics = rollout_metrics(root, 'occam', rules)
        assert metrics['rules_verified'] and metrics['usage_complete']
        assert metrics['model_effort_verified']
        write('child.jsonl', [event('session_meta', id='child', source={'subagent': {}}),
                             context, developer])
        assert not rollout_metrics(root, 'occam', rules)['usage_complete']
        stream = root / 'stream.jsonl'
        stream.write_text(json.dumps({'type': 'turn.completed', 'usage': usage}) + '\n')
        assert stream_metrics(stream)['root_usage'] == usage
        write('child.jsonl', [event('session_meta', id='child', source={'subagent': {}}),
                             context, developer, count, done])
        (root / 'result.json').write_text(json.dumps({'root_usage': usage, 'final': 'Grüße "quoted"\nnext'}))
        row = public_row(root)
        assert row['session_count'] == 2
        assert row['all_usage']['total'] == 56, 'Cache and reasoning subsets must not count twice'
        assert row['root_usage']['output'] == 8 and row['all_usage']['output'] == 16
        assert row['final'] == 'Grüße "quoted"\nnext'
        write('child.jsonl', [event('session_meta', id='child', source={'subagent': {}}),
                             context, developer, count, event('event_msg', type='turn_aborted')])
        interrupted = public_row(root)
        assert interrupted['all_usage']['total'] is None
        assert interrupted['observed_usage']['total'] == 56 and not interrupted['usage_complete']
        value = {'diff': 'name = "/tmp/example"\n# Grüße'}
        assert scrub_values(value, {}) == {'diff': 'name = "<private-path>"\n# Grüße'}
    print('PASS: isolation, session identity, usage completeness, accounting, export escaping')


if __name__ == '__main__':
    main()
