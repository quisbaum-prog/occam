"""Render the README charts as light and dark SVG. Stdlib only.

    python3 chart.py results/opus-r1.jsonl ../assets   # median cost per scenario and arm
    python3 chart.py compare ../assets                 # paired change vs. no plugin, per model
"""
import json, statistics as st, sys
from pathlib import Path

import bench as B

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


def load(src):
    return [json.loads(l) for l in Path(src).read_text().splitlines() if l.strip()]


def codex_total(r):  # incomplete usage (interrupted subagent) is excluded, as in report_codex.py
    return r["all_usage"].get("total") if r.get("usage_complete") and r.get("valid_run") else None


# (label, metric, result file relative to this script, value per run)
SETUPS = [
    ("Claude Opus 5.5, effort max", "cost", "results/opus-r1.jsonl", lambda r: r["cost"]),
    ("Claude Opus 5.5, effort medium", "cost", "results/opus-medium.jsonl", lambda r: r["cost"]),
    ("Claude Haiku 4.5", "cost", "results/haiku-v1.jsonl", lambda r: r["cost"]),
    ("GPT-6 Astra in Codex, effort ultra", "total tokens", "results/2026-09-27-astra-ultra.jsonl", codex_total),
]


def paired(rows, arm, get):
    by = {}
    for r in rows:
        by.setdefault((r["scenario"], r["seed"], r["rep"]), {})[r["arm"]] = r
    ratios = [get(g[arm]) / get(g["baseline"]) for g in by.values()
              if arm in g and "baseline" in g and get(g[arm]) and get(g["baseline"])]
    return (*B.gmean_ci(ratios), len(ratios))


def pct(v):  # typographic minus, as in the README
    return f"{v:+.0f}%".replace("-", "\u2212")


def compare_svg(data, c):
    W, lw, top, row, lo, hi = 760, 230, 70, 64, -60, 60
    arms = ARMS[:2]
    H = top + len(data) * row + 34
    sx = lambda pct: lw + (pct - lo) / (hi - lo) * (W - lw - 50)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">',
         f'<text x="0" y="16" font-size="15" font-weight="600" fill="{c["ink"]}">Change vs. no plugin, geometric mean of paired tasks with 95% interval</text>']
    x = 0
    for a, label in arms:
        o.append(f'<circle cx="{x + 5}" cy="36" r="5" fill="{c[a]}"/>'
                 f'<text x="{x + 17}" y="40" font-size="13" fill="{c["muted"]}">{label}</text>')
        x += 17 + 7 * len(label) + 22
    for v in range(lo, hi + 1, 20):
        o.append(f'<line x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{top - 8}" y2="{H - 26}" stroke="{c["grid"]}" '
                 f'stroke-width="{2 if v == 0 else 1}"/>'
                 f'<text x="{sx(v):.1f}" y="{H - 8}" font-size="12" text-anchor="middle" fill="{c["muted"]}">{pct(v) if v else "0%"}</text>')
    for i, (label, metric, res) in enumerate(data):
        y = top + i * row
        o.append(f'<text x="0" y="{y + 16}" font-size="13" font-weight="600" fill="{c["ink"]}">{label}</text>'
                 f'<text x="0" y="{y + 33}" font-size="12" fill="{c["muted"]}">{metric}, {res["occam"][3]} task pairs</text>')
        for j, (a, name) in enumerate(arms):
            m, l, h, n = (v if k == 3 else (v - 1) * 100 for k, v in enumerate(res[a]))
            yy = y + 10 + j * 18
            o.append(f'<g><title>{label}, {name}: {pct(m)} [{pct(l)[:-1]} … {pct(h)[:-1]}], {n} pairs</title>'
                     f'<line x1="{sx(l):.1f}" x2="{sx(h):.1f}" y1="{yy}" y2="{yy}" stroke="{c[a]}" stroke-width="2"/>'
                     f'<circle cx="{sx(m):.1f}" cy="{yy}" r="5" fill="{c[a]}"/></g>'
                     f'<text x="{sx(h) + 8:.1f}" y="{yy + 4}" font-size="12" font-weight="600" fill="{c["ink"]}">{pct(m)}</text>')
    return "\n".join(o + ["</svg>"]) + "\n"


def compare(out):
    here = Path(__file__).parent
    data = [(label, metric, {a: paired(load(here / src), a, get) for a, _ in ARMS[:2]})
            for label, metric, src, get in SETUPS]
    Path(out).mkdir(parents=True, exist_ok=True)
    for theme, colors in THEMES.items():
        Path(out, f"change-by-model-{theme}.svg").write_text(compare_svg(data, colors))


def main(src, out):
    rows = load(src)
    data = {}
    for s in sorted({r["scenario"] for r in rows}):
        data[s] = {a: (st.median(r["cost"] for r in rows if r["scenario"] == s and r["arm"] == a),
                       sum(r["pass"] for r in rows if r["scenario"] == s and r["arm"] == a)) for a, _ in ARMS}
    Path(out).mkdir(parents=True, exist_ok=True)
    for theme, colors in THEMES.items():
        Path(out, f"cost-per-scenario-{theme}.svg").write_text(svg(data, colors))


if __name__ == "__main__":
    compare(sys.argv[2]) if sys.argv[1] == "compare" else main(*sys.argv[1:3])
