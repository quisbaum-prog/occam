"""Regression checks for actual Codex 0.159 child-rollout ownership and usage."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile

source = Path(__file__).resolve().parents[1] / 'container' / 'cell.py'
spec = importlib.util.spec_from_file_location('cell_metrics', source)
cell = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cell)
job = {'model': 'gpt-6.1-sol', 'effort': 'ultra', 'arm': 'base', 'rules': '', 'delegation': False}

def event(kind, payload):
    return {'type': kind, 'payload': payload}

def usage(input_count, output_count):
    return {'input_tokens': input_count, 'cached_input_tokens': input_count - 1,
            'output_tokens': output_count, 'reasoning_output_tokens': 1,
            'total_tokens': input_count + output_count}

def write(path, values):
    path.write_text('\n'.join(json.dumps({**value, 'ordinal': i}) for i, value in enumerate(values)), encoding='utf-8')

root_usage, child_usage = usage(10, 3), usage(5, 2)
root = [event('session_meta', {'id': 'root', 'source': 'exec', 'cli_version': '0.159.0'}),
        event('turn_context', {'model': job['model'], 'effort': 'ultra'}),
        event('token_usage_record', {'thread_id': 'root', 'response_id': 'r1', 'usage': root_usage}),
        event('event_msg', {'type': 'token_count', 'info': {'total_token_usage': root_usage}}),
        event('event_msg', {'type': 'task_complete'})]
child = [
    event('session_meta', {'id': 'child', 'source': {'subagent': {'thread_spawn': {'parent_thread_id': 'root'}}},
                           'cli_version': '0.159.0', 'subagent_history_start_ordinal': 5}),
    event('session_meta', {'id': 'root', 'source': 'exec'}),
    event('turn_context', {'model': 'inherited-other-model', 'effort': 'low'}),
    event('event_msg', {'type': 'token_count', 'info': {'total_token_usage': usage(99999, 888)}}),
    event('event_msg', {'type': 'task_complete'}),
    event('event_msg', {'type': 'task_started'}),
    event('turn_context', {'model': job['model'], 'effort': 'ultra'}),
    event('token_usage_record', {'thread_id': 'child', 'response_id': 'c1', 'usage': child_usage}),
    event('token_usage_record', {'thread_id': 'child', 'response_id': 'c1', 'usage': child_usage}),
    event('event_msg', {'type': 'token_count', 'info': {'total_token_usage': child_usage}}),
    event('event_msg', {'type': 'token_count', 'info': {'total_token_usage': child_usage}}),
    event('event_msg', {'type': 'task_complete'}),
]
with tempfile.TemporaryDirectory() as temp:
    directory = Path(temp)
    sessions = directory / 'sessions'
    sessions.mkdir()
    stream = directory / 'events.jsonl'
    write(stream, [{'type': 'thread.started', 'thread_id': 'root'}])
    write(sessions / 'root.jsonl', root)
    write(sessions / 'child.jsonl', child)
    result = cell.metrics(stream, directory, job)
    assert result['session_count'] == 2 and result['child_session_count'] == 1
    assert result['usage']['total_tokens'] == 20
    assert result['root_usage'] == root_usage
    assert result['model_effort_verified'] and result['delegation_family_verified'] and result['delegation_verified']
    assert result['usage_complete'] and all(s['response_usage_verified'] for s in result['sessions'])
    assert {s['id'] for s in result['sessions']} == {'root', 'child'}
    # Ordinary modes still reject undeclared child sessions.
    normal_job = {**job, 'effort': 'medium'}
    assert not cell.metrics(stream, directory, normal_job)['delegation_verified']

    # An inherited parent completion cannot complete an active child.
    write(sessions / 'child.jsonl', child[:-1])
    result = cell.metrics(stream, directory, job)
    assert not result['usage_complete'] and result['usage'] is None

    # A completed first child task cannot complete a later unfinished task.
    write(sessions / 'child.jsonl', child + [event('event_msg', {'type': 'task_started'})])
    assert not cell.metrics(stream, directory, job)['usage_complete']

    broken = copy.deepcopy(child)
    broken[-2]['payload']['info']['total_token_usage'] = usage(6, 2)
    write(sessions / 'child.jsonl', broken)
    assert not cell.metrics(stream, directory, job)['usage_complete']

    unrelated = copy.deepcopy(child)
    unrelated[0]['payload']['source']['subagent']['thread_spawn']['parent_thread_id'] = 'outside-root'
    write(sessions / 'child.jsonl', unrelated)
    assert not cell.metrics(stream, directory, job)['delegation_family_verified']

    wrong_context = copy.deepcopy(child)
    wrong_context[6]['payload']['effort'] = 'medium'
    write(sessions / 'child.jsonl', wrong_context)
    assert not cell.metrics(stream, directory, job)['model_effort_verified']

    wrong_rules = copy.deepcopy(child)
    wrong_rules.append(event('response_item', {'role': 'developer', 'content': [{'text': 'OCCAM MODE (full)'}]}))
    write(sessions / 'child.jsonl', wrong_rules)
    assert not cell.metrics(stream, directory, job)['rules_verified']

    conflicting_response = copy.deepcopy(child)
    conflicting_response[8]['payload']['usage'] = usage(6, 2)
    write(sessions / 'child.jsonl', conflicting_response)
    try:
        cell.metrics(stream, directory, job)
    except ValueError as error:
        assert 'duplicate response' in str(error)
    else:
        raise AssertionError('Conflicting duplicate response must be rejected')

print('PASS: stable child identity, inherited-history exclusion, unique response totals, task completion and family validation.')
