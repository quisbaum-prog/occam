"""A/B benchmark for Claude Code token-economy plugins. Stdlib only.

    python3 bench.py run --model sonnet --arms baseline,occam=../plugin,ponytail=/path/to/ponytail \
                         --seeds 1 2 --jobs 4 --out runs/sonnet
    python3 bench.py report runs/sonnet [more dirs...]
    python3 bench.py export runs/sonnet results/sonnet.jsonl

Every run is a real headless Claude Code session in a fresh workspace, with a fresh HOME/config dir and a
clean venv, so nothing leaks between arms: `baseline` loads no plugin, every other arm exactly one (--plugin-dir).

WARNING: sessions run with --permission-mode bypassPermissions. Use a disposable VM or container.
Auth: ANTHROPIC_API_KEY, or a subscription token from `claude setup-token` exported as CLAUDE_CODE_OAUTH_TOKEN.
"""
import argparse, concurrent.futures as cf, json, math, os, random, shutil, signal, statistics as st, subprocess, sys, time
from pathlib import Path

import scenarios as S

# Passed through to every session (HOME is replaced, so a local login is not visible; use a key or token).
# Add more with BENCH_KEEP_ENV=NAME1,NAME2.
KEEP_ENV = ["HTTPS_PROXY", "NO_PROXY", "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "ANTHROPIC_BASE_URL",
            "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", *filter(None, os.environ.get("BENCH_KEEP_ENV", "").split(","))]
# Price multipliers relative to the model's input price (list pricing) -> cost shares by token type.
MULT = {"input": 1, "output": 5, "cache_read": 0.1, "cache_write_5m": 1.25, "cache_write_1h": 2}
MULT_BY_MODEL = {"claude-opus-5-5": {**MULT, "cache_read": 0.05}}  # $4 in / $20 out / $0.20 cache read


def mult_for(r):
    return MULT_BY_MODEL.get(max(r.get("models") or {"": 0}, key=(r.get("models") or {"": 0}).get), MULT)


def sh(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)


def parse_stream(path):
    """Totals from the final result event plus tool usage from the event stream."""
    tools, result_chars, result = {}, 0, None
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    tools[c["name"]] = tools.get(c["name"], 0) + 1
        elif e.get("type") == "user" and isinstance(e["message"].get("content"), list):
            for c in e["message"]["content"]:
                if c.get("type") == "tool_result":
                    body = c.get("content")
                    result_chars += len(body) if isinstance(body, str) else sum(len(x.get("text", "")) for x in body or [])
        elif e.get("type") == "result":
            result = e
    if not result:
        return {"error": "no result event"}
    u = result.get("usage", {})
    cc = u.get("cache_creation") or {}
    return {
        "cost": result.get("total_cost_usd", 0), "turns": result.get("num_turns", 0),
        "duration_s": round(result.get("duration_ms", 0) / 1000, 1), "is_error": result.get("is_error"),
        "subtype": result.get("subtype"), "final": result.get("result") or "",
        "input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
        "thinking": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
        "cache_read": u.get("cache_read_input_tokens", 0),
        "cache_write_5m": cc.get("ephemeral_5m_input_tokens", 0), "cache_write_1h": cc.get("ephemeral_1h_input_tokens", 0),
        "models": {m: round(v.get("costUSD", 0), 4) for m, v in (result.get("modelUsage") or {}).items()},
        "subagents": (result.get("subagent_stats") or {}).get("spawned", 0),
        "tools": tools, "tool_calls": sum(tools.values()), "tool_result_chars": result_chars,
    }


def diff_stats(ws):
    sh(["git", "add", "-A"], ws)
    added = removed = py_added = files = 0
    for line in sh(["git", "diff", "--cached", "--numstat", "HEAD"], ws).stdout.splitlines():
        a, r, name = line.split("\t", 2)
        if a == "-":
            continue
        files += 1
        added, removed = added + int(a), removed + int(r)
        py_added += int(a) if name.endswith(".py") else 0
    patch = sh(["git", "diff", "--cached", "HEAD", "--", ".", ":(exclude)*.json", ":(exclude)*.png"], ws).stdout
    return {"loc_added": added, "loc_removed": removed, "py_added": py_added, "files_changed": files}, patch


def one_run(job, args):
    scen, seed, arm, plugin, rep = job
    rd = Path(args.out).resolve() / f"{scen}-s{seed}-{arm}-r{rep}"
    if (rd / "result.json").exists():
        return json.loads((rd / "result.json").read_text())
    shutil.rmtree(rd, ignore_errors=True)
    ws, home, venv = rd / "ws", rd / "home", rd / "venv"
    ws.mkdir(parents=True)
    task = S.SCENARIOS[scen](seed, ws)
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.name=bench", "-c", "user.email=bench@localhost", "commit", "-qm", "start"]):
        sh(cmd, ws)
    sh([sys.executable, "-m", "venv", str(venv)], rd)
    (home / ".claude").mkdir(parents=True)
    env = {k: os.environ[k] for k in KEEP_ENV if k in os.environ}
    env.update(PATH=f"{venv}/bin:{os.environ['PATH']}", VIRTUAL_ENV=str(venv), HOME=str(home), LANG="C.UTF-8",
               CLAUDE_CONFIG_DIR=str(home / ".claude"), IS_SANDBOX="1", GIT_AUTHOR_NAME="bench", GIT_AUTHOR_EMAIL="b@l",
               GIT_COMMITTER_NAME="bench", GIT_COMMITTER_EMAIL="b@l")
    cmd = ["claude", "-p", task.prompt, "--model", args.model, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "bypassPermissions", "--strict-mcp-config", "--max-budget-usd", str(args.budget_usd)]
    cmd += ["--effort", args.effort] if args.effort else []
    cmd += ["--plugin-dir", plugin] if plugin else []
    t0 = time.time()
    with open(rd / "stream.jsonl", "w") as out, open(rd / "stderr.txt", "w") as err:
        p = subprocess.Popen(cmd, cwd=ws, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
        try:
            p.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
    m = parse_stream(rd / "stream.jsonl")
    m["wall_s"] = round(time.time() - t0, 1)
    try:
        v = task.verify(ws, m.get("final", ""), str(venv / "bin" / "python"))
    except Exception as e:  # a verifier crash must not kill the batch
        v = {"pass": False, "score": 0, "notes": f"verifier crashed: {e!r}"[:300]}
    d, patch = diff_stats(ws)
    (rd / "diff.patch").write_text(patch)
    res = {"scenario": scen, "seed": seed, "arm": arm, "rep": rep, "model": args.model, "effort": args.effort, **m, **d,
           **{k: v[k] for k in v}}
    (rd / "result.json").write_text(json.dumps(res, indent=1))
    if not args.keep:
        for p in (venv, home, ws):
            shutil.rmtree(p, ignore_errors=True)
    return res


def cmd_rescore(args):
    """Re-run verifiers on kept workspaces (after fixing a verifier); no API calls."""
    import tempfile
    for rf in sorted(Path(args.dir).resolve().glob("*/result.json")):
        r, rd = json.loads(rf.read_text()), rf.parent
        if not (rd / "ws").exists():
            continue
        task = S.SCENARIOS[r["scenario"]](r["seed"], tempfile.mkdtemp())
        py = rd / "venv" / "bin" / "python"
        v = task.verify(rd / "ws", r.get("final", ""), str(py) if py.exists() else sys.executable)
        r.update(v)
        rf.write_text(json.dumps(r, indent=1))
        print(f"{r['scenario']:9} s{r['seed']} {r['arm']:10} {'PASS' if v['pass'] else 'fail'} {v['score']} {v['notes'][:120]}")


def cmd_export(args):
    """One JSON line per session (result plus code diff), the format of results/*.jsonl."""
    rows = [{**json.loads(rf.read_text()), "diff": (rf.parent / "diff.patch").read_text()}
            for rf in Path(args.dir).glob("*/result.json")]
    rows.sort(key=lambda r: (r["scenario"], r["seed"], r["arm"], r["rep"]))
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def cmd_run(args):
    arms = []
    for a in args.arms.split(","):
        name, _, path = a.partition("=")
        arms.append((name, str(Path(path).resolve()) if path else None))
    scens = list(S.SCENARIOS) if args.scenarios == "all" else args.scenarios.split(",")
    jobs = [(s, seed, arm, plugin, rep) for s in scens for seed in args.seeds for rep in range(args.reps) for arm, plugin in arms]
    random.Random(0).shuffle(jobs)  # interleave arms so API drift hits them equally
    Path(args.out).mkdir(parents=True, exist_ok=True)
    spent, done = 0.0, 0
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        for fut in cf.as_completed([ex.submit(one_run, j, args) for j in jobs]):
            r = fut.result()
            done += 1
            spent += r.get("cost", 0)
            print(f"[{done}/{len(jobs)}] ${spent:7.2f}  {r['scenario']:9} s{r['seed']} {r['arm']:10} "
                  f"{'PASS' if r.get('pass') else 'fail'} ${r.get('cost', 0):.3f} turns={r.get('turns')} "
                  f"out={r.get('output')} think={r.get('thinking')} {r.get('notes', '')[:80]}", flush=True)


# ------------------------------------------------------------------------------------------------ report

def load(paths):
    """Run directories (runs/x) or exported result files (results/x.jsonl)."""
    rows = []
    for d in map(Path, paths):
        rows += ([json.loads(l) for l in d.read_text().splitlines() if l.strip()] if d.is_file()
                 else [json.loads(p.read_text()) for p in d.glob("*/result.json")])
    return rows


def shares(r):
    m = mult_for(r)
    parts = {k: r.get(k, 0) * m[k] for k in m}
    total = sum(parts.values()) or 1
    return {k: v / total for k, v in parts.items()}


def gmean_ci(ratios, n_boot=4000):
    logs = [math.log(x) for x in ratios if x > 0]
    if not logs:
        return None, None, None
    rng = random.Random(1)
    boots = sorted(math.exp(st.mean(rng.choices(logs, k=len(logs)))) for _ in range(n_boot))
    return math.exp(st.mean(logs)), boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot)]


def cmd_report(args):
    rows = [r for r in load(args.dirs) if "cost" in r]
    arms = sorted({r["arm"] for r in rows}, key=lambda a: (a != "baseline", a))
    by = {}
    for r in rows:
        by.setdefault((r["scenario"], r["seed"], r["rep"]), {})[r["arm"]] = r
    med = lambda xs: st.median(xs) if xs else float("nan")
    out = {"arms": {}, "paired": {}, "scenarios": {}}
    print(f"\n{len(rows)} runs, total ${sum(r['cost'] for r in rows):.2f}\n")
    print("| arm | n | pass | score | Σ cost | median cost | turns | output tok | thinking | cache read | tool output chars | LOC + |")
    print("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for a in arms:
        rs = [r for r in rows if r["arm"] == a]
        s = {"n": len(rs), "pass": sum(r["pass"] for r in rs) / len(rs), "score": st.mean(r["score"] for r in rs),
             "cost_sum": sum(r["cost"] for r in rs), **{k: med([r[k] for r in rs]) for k in
             ("cost", "turns", "output", "thinking", "cache_read", "tool_result_chars", "loc_added")},
             "shares": {k: st.mean(shares(r)[k] for r in rs) for k in MULT}}
        out["arms"][a] = s
        print(f"| {a} | {s['n']} | {s['pass']:.0%} | {s['score']:.2f} | ${s['cost_sum']:.2f} | ${s['cost']:.3f} | {s['turns']:.0f} | "
              f"{s['output']:,.0f} | {s['thinking']:,.0f} | {s['cache_read']:,.0f} | {s['tool_result_chars']:,.0f} | {s['loc_added']:.0f} |")
    print("\nCost share by token type (mean over runs):")
    for a in arms:
        print(f"  {a:12} " + "  ".join(f"{k}={v:.0%}" for k, v in out["arms"][a]["shares"].items()))
    print("\nPaired vs baseline (geometric mean of per-task ratios, 95% bootstrap CI; <1 = cheaper):")
    for a in arms[1:]:
        pairs = [by[k] for k in sorted(by) if "baseline" in by[k] and a in by[k]]  # fixed order: same CI from runs/ or results/
        out["paired"][a] = {"pairs": len(pairs)}
        line = f"  {a:12} pairs={len(pairs):3}"
        for k in ("cost", "output", "cache_read", "turns", "tool_result_chars"):
            eps = 1e-4 if k == "cost" else 1  # smoothing on the metric's own scale
            m, lo, hi = gmean_ci([(g[a][k] + eps) / (g["baseline"][k] + eps) for g in pairs])
            if m:
                out["paired"][a][k] = [m, lo, hi]
                line += f"  {k}={m:.2f} [{lo:.2f}-{hi:.2f}]"
        print(line)
    print("\nPer scenario (median cost $ / pass rate):")
    print("| scenario | " + " | ".join(arms) + " |\n|---|" + "--:|" * len(arms))
    for sc in sorted({r["scenario"] for r in rows}):
        cells = []
        for a in arms:
            rs = [r for r in rows if r["scenario"] == sc and r["arm"] == a]
            out["scenarios"].setdefault(sc, {})[a] = {"cost": med([r["cost"] for r in rs]), "pass": sum(r["pass"] for r in rs) / max(1, len(rs)),
                                                      "output": med([r["output"] for r in rs]), "turns": med([r["turns"] for r in rs])}
            cells.append(f"${med([r['cost'] for r in rs]):.3f} / {sum(r['pass'] for r in rs)}/{len(rs)}" if rs else "–")
        print(f"| {sc} | " + " | ".join(cells) + " |")
    fails = [r for r in rows if not r["pass"]]
    if fails:
        print("\nFailures:")
        for r in sorted(fails, key=lambda r: (r["scenario"], r["arm"])):
            print(f"  {r['scenario']:9} s{r['seed']} {r['arm']:10} score={r['score']} {r.get('notes', '')[:150]}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", default="sonnet")
    r.add_argument("--effort", default=None)
    r.add_argument("--arms", default="baseline,occam=../plugin")
    r.add_argument("--scenarios", default="all")
    r.add_argument("--seeds", type=int, nargs="+", default=[1])
    r.add_argument("--reps", type=int, default=1)
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--budget-usd", type=float, default=10)
    r.add_argument("--timeout", type=int, default=1800)
    r.add_argument("--out", required=True)
    r.add_argument("--keep", action="store_true", help="keep workspaces, venvs and homes")
    p = sub.add_parser("report")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--json")
    sub.add_parser("rescore").add_argument("dir")
    e = sub.add_parser("export")
    e.add_argument("dir")
    e.add_argument("out")
    a = ap.parse_args()
    {"run": cmd_run, "report": cmd_report, "rescore": cmd_rescore, "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    main()
