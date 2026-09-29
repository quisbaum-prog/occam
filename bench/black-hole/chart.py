"""Render the public three-arm pilot as accessible SVG; no model calls."""
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data' / 'sol61-max-fast' / 'pilot.json'
ASSETS = HERE.parents[1] / 'assets' / 'black-hole'
THEMES = {
    'light': {'bg': '#ffffff', 'ink': '#17212e', 'muted': '#526171', 'line': '#dce3eb',
              'occam': '#18754a', 'base': '#65768b', 'ponytail': '#bd5526'},
    'dark': {'bg': '#0d1117', 'ink': '#f0f6fc', 'muted': '#a5b1c0', 'line': '#303b48',
             'occam': '#50c88e', 'base': '#8d9eb5', 'ponytail': '#f49a66'},
}


def savings(rows):
    counts = {r['arm']: r['usage']['total_tokens'] for r in rows}
    assert set(counts) == {'base', 'occam', 'ponytail'} and all(v > 0 for v in counts.values())
    return counts, 100 * (counts['base'] - counts['occam']) / counts['base']


def render(data, colors):
    counts, saving = savings(data['results'])
    removed = counts['base'] - counts['occam']
    headline = f'{saving:.1f}% fewer tokens with Occam' if saving >= 0 else f'{-saving:.1f}% more tokens with Occam'
    desc = ' | '.join(f'{arm}: {counts[arm]:,} tokens' for arm in ('base', 'occam', 'ponytail'))
    items = [f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="388" viewBox="0 0 960 388" role="img" aria-labelledby="title description" font-family="Segoe UI,Arial,sans-serif">',
        f'<title id="title">{headline}</title><desc id="description">{html.escape(desc)}. One run per arm, GPT-6.1 Sol max, Fast requested. Total input plus output, cached input included.</desc>',
        f'<rect x="0.5" y="0.5" width="959" height="387" rx="16" fill="{colors["bg"]}" stroke="{colors["line"]}"/>',
        f'<text x="32" y="40" fill="{colors["muted"]}" font-size="14">BLACK-HOLE PILOT · GPT-6.1 SOL · MAX · FAST</text>',
        f'<text x="32" y="85" fill="{colors["ink"]}" font-size="30" font-weight="700">{headline}</text>',
        f'<text x="32" y="112" fill="{colors["muted"]}" font-size="16">{removed:,} fewer tokens than Base on the same animation task</text>' if removed >= 0 else
        f'<text x="32" y="112" fill="{colors["muted"]}" font-size="16">{-removed:,} additional tokens compared with Base on this task</text>']
    x, plot_width = 160, 520
    maximum = max(counts.values())
    for tick in (0, 0.25, 0.5, 0.75, 1):
        position = x + tick * plot_width
        items.append(f'<line x1="{position}" x2="{position}" y1="144" y2="320" stroke="{colors["line"]}"/>')
    for i, arm in enumerate(('base', 'occam', 'ponytail')):
        y = 155 + i * 57
        width = counts[arm] / maximum * plot_width
        change = 100 * (counts[arm] / counts['base'] - 1)
        suffix = 'reference' if arm == 'base' else f'{change:+.1f}% vs Base'
        name = {'base': 'Base', 'occam': 'Occam', 'ponytail': 'Ponytail 4.10'}[arm]
        items.extend([
            f'<text x="32" y="{y+25}" fill="{colors["ink"]}" font-size="17" font-weight="{700 if arm == "occam" else 500}">{name}</text>',
            f'<rect x="{x}" y="{y}" width="{width:.3f}" height="36" rx="5" fill="{colors[arm]}"><title>{name}: {counts[arm]:,} tokens; {suffix}</title></rect>',
            f'<text x="704" y="{y+17}" fill="{colors["ink"]}" font-size="18" font-weight="700">{counts[arm]:,}</text>',
            f'<text x="704" y="{y+36}" fill="{colors["muted"]}" font-size="13">{suffix}</text>'])
    items.extend([
        f'<text x="32" y="347" fill="{colors["muted"]}" font-size="14">Total tokens = input + output · cache and reasoning subsets counted once</text>',
        f'<text x="32" y="370" fill="{colors["muted"]}" font-size="13">One attempt per arm · no confidence interval · compare visual results in the video</text>',
        '</svg>'])
    return '\n'.join(items) + '\n'


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    assert all(r['valid_run'] and r['usage_complete'] for r in data['results'])
    ASSETS.mkdir(parents=True, exist_ok=True)
    for theme, colors in THEMES.items():
        (ASSETS / f'sol61-max-fast-tokens-{theme}.svg').write_text(render(data, colors), encoding='utf-8')
    counts, saving = savings(data['results'])
    print(json.dumps({'tokens': counts, 'occam_saving_percent': saving}))


if __name__ == '__main__':
    main()
