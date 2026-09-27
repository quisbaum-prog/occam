"""Render the README chart (median cost per scenario and arm) as light and dark SVG. Stdlib only.

    python3 chart.py results/opus-r1.jsonl ../assets
"""
import json, statistics as st, sys
from pathlib import Path

ARMS = [("occam", "Occam"), ("ponytail", "Ponytail 4.10"), ("baseline", "no plugin")]
THEMES = {  # series steps validated for colour-vision deficiency on light and dark surfaces
    "light": {"ink": "#1f2328", "muted": "#59636e", "grid": "#d1d9e0", "bad": "#d03b3b",
              "occam": "#2a78d6", "ponytail": "#eb6834", "baseline": "#1baf7a"},
    "dark": {"ink": "#f0f6fc", "muted": "#9198a1", "grid": "#3d444d", "bad": "#e66767",
             "occam": "#3987e5", "ponytail": "#d95926", "baseline": "#199e70"},
}
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


def bar(x0, x1, y, h, r=3):  # square at the baseline, rounded data end
    if x1 - x0 <= r:
        return f'M{x0},{y}h{max(x1 - x0, 1):.1f}v{h}h{-max(x1 - x0, 1):.1f}z'
    return f'M{x0},{y}H{x1 - r:.1f}Q{x1:.1f},{y} {x1:.1f},{y + r}V{y + h - r}Q{x1:.1f},{y + h} {x1 - r:.1f},{y + h}H{x0}Z'


def svg(data, c):
    W, lw, top, bh, gap, row, xmax = 760, 112, 64, 8, 2, 40, 1.75
    names = sorted(data, key=lambda s: -data[s]["baseline"][0])
    H = top + len(names) * row + 30
    sx = lambda v: lw + v / xmax * (W - lw - 70)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">',
         f'<text x="0" y="16" font-size="15" font-weight="600" fill="{c["ink"]}">Median cost per task, Claude Opus 5.5 (effort max), USD at list price</text>']
    x = 0
    for a, label in ARMS:
        o.append(f'<rect x="{x}" y="30" width="11" height="11" rx="2" fill="{c[a]}"/>'
                 f'<text x="{x + 17}" y="40" font-size="13" fill="{c["muted"]}">{label}</text>')
        x += 17 + 7 * len(label) + 22
    for v in (0, 0.5, 1.0, 1.5):
        o.append(f'<line x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{top - 6}" y2="{H - 26}" stroke="{c["grid"]}" stroke-width="1"/>'
                 f'<text x="{sx(v):.1f}" y="{H - 8}" font-size="12" text-anchor="middle" fill="{c["muted"]}">${v:.2f}</text>')
    for i, s in enumerate(names):
        y = top + i * row
        o.append(f'<text x="0" y="{y + 17}" font-size="13" font-weight="600" fill="{c["ink"]}">{s}</text>')
        for j, (a, label) in enumerate(ARMS):
            v, passed = data[s][a]
            yy = y + j * (bh + gap)
            o.append(f'<path d="{bar(sx(0), sx(v), yy, bh)}" fill="{c[a]}"><title>{s}, {label}: ${v:.2f}, tests {passed}/2</title></path>')
            if a == "occam":
                o.append(f'<text x="{sx(v) + 6:.1f}" y="{yy + bh}" font-size="12" font-weight="600" fill="{c["ink"]}">${v:.2f}</text>')
            if passed < 2:
                o.append(f'<text x="{sx(v) + 6:.1f}" y="{yy + bh}" font-size="12" font-weight="600" fill="{c["bad"]}">✗ tests failed {2 - passed}/2</text>')
    return "\n".join(o + ["</svg>"]) + "\n"


def main(src, out):
    rows = [json.loads(l) for l in Path(src).read_text().splitlines() if l.strip()]
    data = {}
    for s in sorted({r["scenario"] for r in rows}):
        data[s] = {a: (st.median(r["cost"] for r in rows if r["scenario"] == s and r["arm"] == a),
                       sum(r["pass"] for r in rows if r["scenario"] == s and r["arm"] == a)) for a, _ in ARMS}
    Path(out).mkdir(parents=True, exist_ok=True)
    for theme, colors in THEMES.items():
        Path(out, f"cost-per-scenario-{theme}.svg").write_text(svg(data, colors))


if __name__ == "__main__":
    main(*sys.argv[1:3])
