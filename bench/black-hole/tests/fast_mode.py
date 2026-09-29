"""Check speed selection survives scheduling without contaminating rule or effort settings."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bench

spec = importlib.util.spec_from_file_location('generation', ROOT / 'container' / 'cell.py')
cell = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cell)
config = bench.read(ROOT / 'benchmark.json')
selected = [{'id': 'gpt-6.1-sol', 'effort': 'max', 'service_tier': 'fast'}]
scheduled = bench.schedule(config, selected, 1)
assert len(scheduled) == 3 and {s['arm'] for s in scheduled} == {'base', 'occam', 'ponytail'}
assert all(s['model'] == 'gpt-6.1-sol' and s['effort'] == 'max' and s['service_tier'] == 'fast' for s in scheduled)
assert all(cell.speed_settings(s) == {'service_tier': 'fast', 'features.fast_mode': True} for s in scheduled)
assert cell.speed_settings({'effort': 'ultra'}) == {}
try:
    cell.speed_settings({'service_tier': 'invented'})
except ValueError:
    pass
else:
    raise AssertionError('An unsupported tier must fail rather than silently fall back')
with tempfile.TemporaryDirectory() as temporary:
    runtime = Path(temporary)
    assert cell.model_capabilities(runtime, {'model': 'gpt-6.1-sol'})['slug'] is None
    (runtime / 'models_cache.json').write_text(json.dumps({'models': [
        {'slug': 'other', 'additional_speed_tiers': ['fast']},
        {'slug': 'gpt-6.1-sol', 'additional_speed_tiers': ['fast'], 'private_field': 'exclude'}]}), encoding='utf-8')
    caps = cell.model_capabilities(runtime, {'model': 'gpt-6.1-sol'})
    assert caps['slug'] == 'gpt-6.1-sol' and caps['additional_speed_tiers'] == ['fast']
    assert 'private_field' not in caps
print('PASS: balanced Max/Fast arms, explicit tier, unsupported-tier rejection and model-specific catalog evidence.')
