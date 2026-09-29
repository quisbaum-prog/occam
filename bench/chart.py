"""Render the README charts as light and dark SVG and print the README overview table. Stdlib only.

    python3 chart.py ../assets
"""
import json, math, statistics as st, sys
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


def svg(data, c, title, fmt, tfmt, ticks, xmax):  # median per scenario and arm; fmt labels values, tfmt ticks
    W, lw, top, bh, gap, row = 760, 112, 64, 8, 2, 40
    names = sorted(data, key=lambda s: -data[s]["baseline"][0])
    H = top + len(names) * row + 30
    sx = lambda v: lw + v / xmax * (W - lw - 70)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">',
         f'<text x="0" y="16" font-size="15" font-weight="600" fill="{c["ink"]}">{title}</text>']
    x = 0
    for a, label in ARMS:
        o.append(f'<rect x="{x}" y="30" width="11" height="11" rx="2" fill="{c[a]}"/>'
                 f'<text x="{x + 17}" y="40" font-size="13" fill="{c["muted"]}">{label}</text>')
        x += 17 + 7 * len(label) + 22
    for v in ticks:
        o.append(f'<line x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{top - 6}" y2="{H - 26}" stroke="{c["grid"]}" stroke-width="1"/>'
                 f'<text x="{sx(v):.1f}" y="{H - 8}" font-size="12" text-anchor="middle" fill="{c["muted"]}">{tfmt(v)}</text>')
    for i, s in enumerate(names):
        y = top + i * row
        o.append(f'<text x="0" y="{y + 17}" font-size="13" font-weight="600" fill="{c["ink"]}">{s}</text>')
        for j, (a, label) in enumerate(ARMS):
            v, passed = data[s][a]
            yy = y + j * (bh + gap)
            o.append(f'<path d="{bar(sx(0), sx(v), yy, bh)}" fill="{c[a]}"><title>{s}, {label}: {fmt(v)}, tests {passed}/2</title></path>')
            lx = sx(v) + 6
            if a == "occam":
                o.append(f'<text x="{lx:.1f}" y="{yy + bh}" font-size="12" font-weight="600" fill="{c["ink"]}">{fmt(v)}</text>')
                lx += 7 * len(fmt(v)) + 6
            if passed < 2:
                o.append(f'<text x="{lx:.1f}" y="{yy + bh}" font-size="12" font-weight="600" fill="{c["bad"]}">✗ tests failed {2 - passed}/2</text>')
    return "\n".join(o + ["</svg>"]) + "\n"


def load(src):
    return [json.loads(l) for l in Path(src).read_text(encoding="utf-8").splitlines() if l.strip()]


def reviewed_pass(r):  # the documented source review where one exists, else the verifier
    return r.get("adjudication", {}).get("reviewed_pass", r["pass"])


def usd(v):
    return f"${v:.2f}"


# (file, result file relative to this script, title, value per run, pass per run, value format, tick format, ticks, x max)
PER_SCENARIO = [
    ("cost-per-scenario", "results/opus-r1.jsonl", "Median cost per task, Claude Opus 5.5 (effort max), USD at list price",
     lambda r: r["cost"], lambda r: r["pass"], usd, usd, (0, 0.5, 1.0, 1.5), 1.75),
    ("cost-per-scenario-medium", "results/opus-medium.jsonl",
     "Median cost per task, Claude Opus 5.5 (effort medium), USD at list price",
     lambda r: r["cost"], lambda r: r["pass"], lambda v: f"${v:.3f}", usd, (0, 0.05, 0.1, 0.15, 0.2), 0.25),
    ("cost-per-scenario-sonnet-max", "results/sonnet-max.jsonl",
     "Median cost per task, Claude Sonnet 5.5 (effort max), USD at list price",
     lambda r: r["cost"], lambda r: r["pass"], usd, usd, (0, 0.25, 0.5, 0.75, 1.0), 1.15),
    ("cost-per-scenario-sonnet-medium", "results/sonnet-medium.jsonl",
     "Median cost per task, Claude Sonnet 5.5 (effort medium), USD at list price",
     lambda r: r["cost"], lambda r: r["pass"], lambda v: f"${v:.3f}", usd, (0, 0.02, 0.04, 0.06, 0.08, 0.1), 0.12),
    ("cost-per-scenario-haiku", "results/haiku-v1.jsonl", "Median cost per task, Claude Haiku 4.5, USD at list price",
     lambda r: r["cost"], lambda r: r["pass"], lambda v: f"${v:.3f}", usd, (0, 0.05, 0.1, 0.15, 0.2), 0.25),
]


# (label, metric, result file relative to this script, value per run)
SETUPS = [
    ("Claude Opus 5.5, effort max", "cost", "results/opus-r1.jsonl", lambda r: r["cost"]),
    ("Claude Opus 5.5, effort medium", "cost", "results/opus-medium.jsonl", lambda r: r["cost"]),
    ("Claude Sonnet 5.5, effort max", "cost", "results/sonnet-max.jsonl", lambda r: r["cost"]),
    ("Claude Sonnet 5.5, effort medium", "cost", "results/sonnet-medium.jsonl", lambda r: r["cost"]),
    ("Claude Haiku 4.5", "cost", "results/haiku-v1.jsonl", lambda r: r["cost"]),
]


def paired(rows, arm, get, ref="baseline"):
    by = {}
    for r in rows:
        by.setdefault((r["scenario"], r["seed"], r["rep"]), {})[r["arm"]] = r
    ratios = [get(g[arm]) / get(g[ref]) for g in by.values() if arm in g and ref in g and get(g[arm]) and get(g[ref])]
    return (*B.gmean_ci(ratios), len(ratios))


def pct(v):  # typographic minus, as in the README
    return f"{v:+.0f}%".replace("-", "\u2212")


def change(res):  # paired() result -> "−51% [−58 … −42]"
    m, l, h = ((v - 1) * 100 for v in res[:3])
    return f"{pct(m)} [{pct(l)[:-1]} … {pct(h)[:-1]}]"


def compare_svg(data, c):
    arms = ARMS[:2]
    ends = [(v - 1) * 100 for _, _, res in data for a, _ in arms for v in res[a][1:3]]
    W, lw, top, row = 760, 230, 76, 64
    lo, hi = min(-60, 20 * math.floor(min(ends) / 20)), max(60, 20 * math.ceil(max(ends) / 20))
    H = top + len(data) * row + 34
    sx = lambda pct: lw + (pct - lo) / (hi - lo) * (W - lw - 50)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">',
         f'<text x="0" y="16" font-size="15" font-weight="600" fill="{c["ink"]}">Change vs. no plugin, by model and effort</text>',
         f'<text x="0" y="35" font-size="12" fill="{c["muted"]}">Dot: typical task (geometric mean of paired tasks). '
         f'Line: 95% interval. Not crossing 0% = a clear difference.</text>',
         f'<text x="{sx(0) - 8:.1f}" y="{top - 16}" font-size="12" text-anchor="end" fill="{c["muted"]}">← cheaper</text>'
         f'<text x="{sx(0) + 8:.1f}" y="{top - 16}" font-size="12" fill="{c["muted"]}">more expensive →</text>']
    x = 0
    for a, label in arms:
        o.append(f'<circle cx="{x + 5}" cy="{top - 20}" r="5" fill="{c[a]}"/>'
                 f'<text x="{x + 17}" y="{top - 16}" font-size="13" fill="{c["muted"]}">{label}</text>')
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
            m, l, h = ((v - 1) * 100 for v in res[a][:3])
            yy = y + 10 + j * 18
            o.append(f'<g><title>{label}, {name}: {change(res[a])}, {res[a][3]} pairs</title>'
                     f'<line x1="{sx(l):.1f}" x2="{sx(h):.1f}" y1="{yy}" y2="{yy}" stroke="{c[a]}" stroke-width="2"/>'
                     f'<circle cx="{sx(m):.1f}" cy="{yy}" r="5" fill="{c[a]}"/></g>'
                     f'<text x="{sx(h) + 8:.1f}" y="{yy + 4}" font-size="12" font-weight="600" fill="{c["ink"]}">{pct(m)}</text>')
    return "\n".join(o + ["</svg>"]) + "\n"


def per_scenario(rows, get, passed):  # {scenario: {arm: (median value, passed runs)}}
    cells = lambda s, a: [r for r in rows if r["scenario"] == s and r["arm"] == a]
    return {s: {a: (st.median(v for r in cells(s, a) if (v := get(r)) is not None), sum(passed(r) for r in cells(s, a)))
                for a, _ in ARMS} for s in sorted({r["scenario"] for r in rows})}


def write(out, name, render):
    Path(out).mkdir(parents=True, exist_ok=True)
    for theme, colors in THEMES.items():
        Path(out, f"{name}-{theme}.svg").write_text(render(colors), encoding="utf-8")


def main(out):
    here = Path(__file__).parent
    for name, src, title, get, passed, fmt, tfmt, ticks, xmax in PER_SCENARIO:
        data = per_scenario(load(here / src), get, passed)
        write(out, name, lambda c: svg(data, c, title, fmt, tfmt, ticks, xmax))
    rounds = [(label, metric, {a: paired(load(here / src), a, get) for a, _ in ARMS[:2]})
              for label, metric, src, get in SETUPS]
    write(out, "change-by-model", lambda c: compare_svg(rounds, c))
    print("| Round | Measured | Occam vs. no plugin | Ponytail vs. no plugin | Occam vs. Ponytail | "
          "Tests passed: no plugin / Occam / Ponytail |\n|---|---|---|---|---|---|")
    for label, metric, src, get in SETUPS:
        rows = load(here / src)
        passed = lambda f: " / ".join(str(sum(f(r) for r in rows if r["arm"] == a)) for a in ("baseline", "occam", "ponytail"))
        raw, reviewed = passed(lambda r: r["pass"]), passed(reviewed_pass)
        tests = raw if raw == reviewed else f"{raw} (reviewed: {reviewed})"
        print(f"| {label} | {metric} | {change(paired(rows, 'occam', get))} | {change(paired(rows, 'ponytail', get))} | "
              f"{change(paired(rows, 'occam', get, 'ponytail'))} | {tests} |")


if __name__ == "__main__":
    main(sys.argv[1])
