"""Export a Codex run as public JSONL and a Markdown report (stdlib only).

    python3 bench/report_codex.py bench/runs/RUN --out bench/results/REPORT
"""
import argparse
import json
import math
from pathlib import Path
import re
import statistics as st

import bench as B


TOKENS = {"input": "input_tokens", "cached": "cached_input_tokens",
          "output": "output_tokens", "reasoning": "reasoning_output_tokens"}
ARMS = ("baseline", "ponytail", "occam")
SOURCE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".sh", ".c", ".h", ".cpp", ".rs", ".go"}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def usage(raw):
    raw = raw or {}
    return {key: raw.get(field) if number(raw.get(field)) else None for key, field in TOKENS.items()}


def sessions(cell, result):
    """First metadata identifies a rollout; only its last cumulative usage counts."""
    found = {}
    paths = sorted((cell / "sessions").rglob("*.jsonl"))
    for path in paths:
        meta, last, stamp, completed = None, None, "", False
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get("payload") or {}
            if event.get("type") == "session_meta" and meta is None:
                meta = payload
            elif event.get("type") == "event_msg":
                if payload.get("type") == "token_count" and payload.get("info"):
                    candidate = payload["info"].get("total_token_usage")
                    if candidate is not None:
                        last, stamp = candidate, event.get("timestamp", "")
                completed |= payload.get("type") == "task_complete"
        if meta and meta.get("id"):
            item = {"id": meta["id"], "source": meta.get("source"), "usage": last,
                    "completed": completed, "stamp": stamp}
            prior = found.get(meta["id"])
            if prior is None or (last is not None and stamp >= prior.get("stamp", "")):
                found[meta["id"]] = item
    if not paths:
        for item in result.get("sessions", []):
            if item.get("id"):
                # Result metadata already contains the last usage per rollout.
                found[item["id"]] = item
    return list(found.values())


def source_loc(patch):
    """Count changed code lines in the recorded patch, excluding test sources."""
    added = removed = 0
    source = in_hunk = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            source = in_hunk = False
        elif line.startswith("+++ "):
            name = line[4:].strip('"')
            if name != "/dev/null":
                source = is_source(name.removeprefix("b/"))
        elif line.startswith("--- "):
            source = is_source(line[4:].strip('"').removeprefix("a/"))
        elif line.startswith("@@"):
            in_hunk = True
        elif source and in_hunk:
            added += line.startswith("+")
            removed += line.startswith("-")
    return {"source_loc_added": added, "source_loc_removed": removed}


def is_source(name):
    p = Path(name)
    return (p.suffix in SOURCE_EXTS and not any(x in {"tests", "test", "__pycache__", ".venv", "venv", "node_modules"} for x in p.parts)
            and not p.name.startswith("test_") and not p.stem.endswith(("_test", ".test", ".spec")))


def scrub(text, private):
    """Keep complete textual evidence while removing runtime identifiers/paths."""
    replacements = private if isinstance(private, dict) else dict.fromkeys(private, '<private>')
    for token in sorted(replacements, key=len, reverse=True):
        if token:
            text = text.replace(token, replacements[token])
    text = re.sub(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|private|tmp|var/folders|Volumes)/)[^\s`\"'<>\]\)]*", "<private-path>", text)
    text = re.sub(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", "<session-id>", text, flags=re.I)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "<redacted-key>", text)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+", r"\1<redacted>", text)
    return text


def scrub_values(value, private):
    if isinstance(value, str):
        return scrub(value, private)
    if isinstance(value, dict):
        return {k: scrub_values(v, private) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_values(v, private) for v in value]
    return value


def public_row(cell, adjudications=None):
    result = json.loads((cell / "result.json").read_text())
    logs = sessions(cell, result)
    private = {str(cell.resolve()): '<cell>'}
    private.update({s["id"]: '<session-id>' for s in logs})
    invocation = cell / "invocation.json"
    if invocation.exists():
        inv = json.loads(invocation.read_text())
        scratch = inv.get('scratch')
        if scratch:
            for base in {scratch, str(Path(scratch).resolve())}:
                private.update({base + '/ws': '<workspace>', base + '/user': '<runtime-user>', base: '<runtime>'})
        command = inv.get('command') or []
        if command and command[0].startswith('/'):
            private[command[0]] = '<codex-executable>'
    normalized = [usage(s.get("usage")) for s in logs]
    coverage = {key: sum(v[key] is not None for v in normalized) for key in TOKENS}
    totals = {key: sum(v[key] for v in normalized) if logs and coverage[key] == len(logs) else None for key in TOKENS}
    if totals["input"] is not None and totals["output"] is not None:
        totals["total"] = totals["input"] + totals["output"]
    else:
        totals["total"] = None
    usage_complete = bool(logs) and all(s.get('completed') is True for s in logs) and all(v is not None for v in totals.values())
    observed = totals.copy()
    if not usage_complete:
        totals = dict.fromkeys(totals)
    keys = ("scenario", "seed", "arm", "rep", "model", "effort", "backend", "exit_code", "timed_out",
            "valid_run", "wall_s", "pass", "score", "notes", "rules_sha256", "fixture_sha256",
            "model_effort_verified", "rules_verified", "active_rules", "loc_added", "loc_removed",
            "py_added", "files_changed")
    row = {key: result.get(key) for key in keys}
    row.update(cost=None, root_usage=usage(result.get("root_usage")), all_usage=totals,
               observed_usage=observed, usage_complete=usage_complete,
               session_count=len(logs), sessions_completed=sum(s.get("completed") is True for s in logs),
               usage_coverage=coverage, root_tool_calls=result.get("tool_calls"),
               root_tools=result.get("tools"), root_tool_result_chars=result.get("tool_result_chars"),
               final=result.get("final"))
    patch_file = cell / "diff.patch"
    row["diff"] = patch_file.read_text(errors="replace") if patch_file.exists() else None
    row.update(source_loc(row["diff"]) if row["diff"] is not None else {"source_loc_added": None, "source_loc_removed": None})
    prompt = cell / "prompt.txt"
    row["prompt"] = prompt.read_text() if prompt.exists() else None
    reviewed = (adjudications or {}).get(cell.name)
    if reviewed:
        row["adjudication"] = {k: reviewed.get(k) for k in ('reviewed_pass', 'reason', 'evidence')}
    # Redact string values before serialization to preserve quotes, escapes and newlines.
    return scrub_values(row, private)


def value(row, metric):
    return row["all_usage"].get(metric[4:]) if metric.startswith("all_") else row.get(metric)


def fmt(n, decimals=0):
    return f"{n:,.{decimals}f}" if number(n) else "N/A"


def median(rows, metric, decimals=0):
    vals = [value(r, metric) for r in rows if number(value(r, metric))]
    answer = fmt(st.median(vals), decimals) if vals else "N/A"
    return answer + (f" (n={len(vals)}/{len(rows)})" if vals and len(vals) != len(rows) else "")


def count(rows, key):
    known = [r for r in rows if isinstance(r.get(key), bool)]
    return f"{sum(r[key] for r in known)}/{len(known)}" if known else "N/A"


def table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers),
            *("| " + " | ".join(map(str, row)) + " |" for row in rows), ""]


def paired(rows, numerator, denominator, metric):
    cells = {}
    for row in rows:
        key = row["scenario"], row["seed"], row["rep"]
        if row.get("valid_run") is True:
            cells.setdefault(key, {})[row["arm"]] = row
    ratios = []
    for pair in cells.values():
        if numerator not in pair or denominator not in pair:
            continue
        a, b = pair[numerator], pair[denominator]
        if a.get("fixture_sha256") and b.get("fixture_sha256") and a["fixture_sha256"] != b["fixture_sha256"]:
            continue
        x, y = value(a, metric), value(b, metric)
        # No pseudocounts: undefined/zero ratios are omitted and n is explicit.
        if number(x) and number(y) and x > 0 and y > 0:
            ratios.append(x / y)
    point, low, high = B.gmean_ci(ratios)
    return [numerator + " / " + denominator, metric, len(ratios),
            f"{point:.3f} [{low:.3f}, {high:.3f}]" if point is not None else "N/A"]


def report(rows, config):
    arms = [a for a in ARMS if any(r["arm"] == a for r in rows)]
    arms += sorted({r["arm"] for r in rows} - set(arms))
    valid = [r for r in rows if r.get("valid_run") is True]
    scens = sorted({r["scenario"] for r in rows})
    seeds = sorted({r["seed"] for r in rows})
    lines = ["# GPT-6 Astra Ultra: baseline, Ponytail and Occam", "",
             f"Observed: **{len(rows)} completed result files**, **{len(valid)} valid runs**, "
             f"{len(scens)} scenarios and seeds {', '.join(map(str, seeds)) or 'N/A'}. "
             f"Planned cells: {config.get('planned_cells', 'N/A')}. Costs are unavailable (`cost: null`).", "",
             "## Method", "",
             "The target design is the repository's nine original scenarios, seeds 1 and 2, one run per "
             "scenario/seed/arm: 54 cells, 18 per arm. The observed counts above and below govern incomplete exports. "
             f"Recorded CLI: **{config.get('cli', 'N/A')}**; configured model: "
             f"**{config.get('model', 'N/A')}**, effort **{config.get('effort', 'N/A')}** "
             "(target: Codex 0.153.4, GPT-6 Astra, Ultra).", "",
             "The Codex adapter preserves the original task prompts and hidden verifiers. Each cell starts in an "
             "isolated workspace and Python environment. Fixtures are generated with `PYTHONHASHSEED=1`, frozen once "
             "per scenario/seed, and copied to each arm. Cells are interleaved in a fixed shuffled order (seed 0), "
             "with three concurrent cells. The baseline adds no skill rules. Ponytail and Occam receive "
             "the exact full-mode rules produced by their SessionStart rule generators through `developer_instructions`. "
             "This does **not** reproduce Claude's native plugin lifecycle. Ultra's automatic delegation remains enabled. "
             "Global personal skills, memories, user configuration and plugins are excluded; standard Codex built-in "
             "skills are the same across arms. Model/effort and injected rules are checked from session evidence.", "",
             "Token totals use the last cumulative usage for each unique session ID, including delegated sessions. "
             "The first `session_meta` identifies each raw rollout; duplicate IDs count once. A missing session metric "
             "makes that aggregate unavailable rather than zero. Cached input is a subset of input; reasoning output "
             "is a subset of output. Total tokens are input + output, without adding either subset again. "
             "The CLI root-session usage is reported separately and is not added to the session aggregate. "
             "Tool calls/output characters cover the root CLI stream only. Wall time includes the session, not verification.", "",
             "If a delegated session is interrupted without a completion event, its recorded counters may omit "
             "in-flight work. Such cells retain their functional verdict and observed counters, but all-session "
             "token metrics are N/A and excluded from token ratios. `observed_usage` in the JSONL preserves "
             "the available counters, while `usage_complete` identifies measurements eligible for those ratios.", "",
             "All medians and ratios use valid runs, including valid runs that fail the task verifier. "
             "Source LOC is a code-file diff-line proxy, including blank lines and comments, with conventional "
             "test file/directory names and generated data excluded; "
             "the JSONL separately retains the runner's all-text LOC totals. The untruncated captured textual diff and "
             "final answer are exported after privacy redaction. The runner's patch excludes JSON and PNG files, "
             "so it is not a complete workspace archive. Missing values are `null`/N/A.", "",
             "## Completion and correctness", ""]
    lines += table(["Arm", "Results", "Valid", "Complete usage", "Verifier pass (all results)", "Verifier pass (valid)", "Mean score (valid)"],
                   [[a, len(rs := [r for r in rows if r['arm'] == a]), count(rs, 'valid_run'), count(rs, 'usage_complete'), count(rs, 'pass'),
                     count(vs := [r for r in rs if r.get('valid_run') is True], 'pass'),
                     fmt(st.mean(scores), 3) if (scores := [r['score'] for r in vs if number(r.get('score'))]) else 'N/A'] for a in arms])
    reviewed = [r for r in rows if r.get('adjudication')]
    if reviewed:
        lines += ["### Separate source review", "",
                  "The original verifier verdict and score above remain unchanged. These recorded source reviews "
                  "are separate adjudications, not additional model runs or edits to the original verifier.", ""]
        lines += table(["Scenario", "Seed", "Arm", "Raw pass", "Reviewed pass", "Reason and evidence"],
                       [[r['scenario'], r['seed'], r['arm'], r['pass'], r['adjudication'].get('reviewed_pass'),
                         (str(r['adjudication'].get('reason') or '') + ' ' + str(r['adjudication'].get('evidence') or '')).replace('|', '\\|').replace('\n', ' ')] for r in reviewed])
        lines += table(["Arm", "Original verifier pass (valid)", "Pass after documented adjudications (valid)"],
                       [[a, count(rs := [r for r in valid if r['arm'] == a], 'pass'),
                         f"{sum(r.get('adjudication', {}).get('reviewed_pass', r['pass']) is True for r in rs)}/{len(rs)}"]
                        for a in arms])
    lines += ["## Median measurements (valid runs)", ""]
    lines += table(["Arm", "n", "All-session input", "Cached input", "Output", "Reasoning output", "Total tokens", "Wall s"],
                   [[a, len(rs := [r for r in valid if r['arm'] == a]), *(median(rs, 'all_' + k) for k in (*TOKENS, 'total')), median(rs, 'wall_s', 1)] for a in arms])
    lines += table(["Arm", "Root input", "Root cached", "Root output", "Root reasoning", "Root tool calls", "Root tool-output chars", "Source LOC +", "Source LOC −"],
                   [[a, *(fmt(st.median(vs)) if (vs := [r['root_usage'][k] for r in valid if r['arm'] == a and number(r['root_usage'][k])]) else 'N/A' for k in TOKENS),
                     *(median([r for r in valid if r['arm'] == a], k) for k in ('root_tool_calls', 'root_tool_result_chars', 'source_loc_added', 'source_loc_removed'))] for a in arms])
    lines += ["## Paired ratios", "",
              "Geometric mean of within-scenario/seed/repetition ratios, with the repository's `bench.gmean_ci` "
              "95% bootstrap interval (4,000 resamples, fixed bootstrap seed 1). Ratios below 1 mean a smaller "
              "measurement, not necessarily better work. Pairs with conflicting fixture hashes are excluded. "
              "Both measurements must be available and strictly positive; zero-valued pairs are omitted without "
              "smoothing, so n can differ by metric. These are not dollar ratios.", ""]
    comparisons = [(a, 'baseline') for a in ('ponytail', 'occam') if a in arms and 'baseline' in arms]
    if 'occam' in arms and 'ponytail' in arms:
        comparisons.append(('occam', 'ponytail'))
    lines += table(["Comparison", "Metric", "Pairs", "Ratio [95% interval]"],
                   [paired(rows, a, b, k) for a, b in comparisons for k in
                    ('all_input', 'all_cached', 'all_output', 'all_reasoning', 'all_total', 'wall_s', 'root_tool_calls', 'source_loc_added', 'source_loc_removed')])
    lines += ["## Per scenario", "", "Cells show valid verifier passes / valid runs; median all-session total tokens; median wall seconds.", ""]
    grid = []
    for scenario in scens:
        cells = []
        for arm in arms:
            rs = [r for r in valid if r['scenario'] == scenario and r['arm'] == arm]
            cells.append(f"{count(rs, 'pass')}; {median(rs, 'all_total')} tok; {median(rs, 'wall_s', 1)} s")
        grid.append([scenario, *cells])
    lines += table(["Scenario", *arms], grid)
    failures = [r for r in rows if r.get('pass') is not True or r.get('valid_run') is not True]
    if failures:
        lines += ["## Failed or invalid cells", ""]
        lines += table(["Scenario", "Seed", "Arm", "Valid", "Pass", "Notes"],
                       [[r['scenario'], r['seed'], r['arm'], r['valid_run'], r['pass'],
                         str(r.get('notes') or 'N/A').replace('|', '\\|').replace('\n', ' ')] for r in failures])
    lines += ["## Limitations", "",
              "This is an exploratory comparison with two seeds, not 18 independent task families per arm. "
              "The bootstrap resamples task pairs, not scenario clusters; its intervals do not establish "
              "general performance or isolate run-to-run variance. The texture task is the same task repeated "
              "across seeds. Automatic delegation can change the number of sessions and is included where usage "
              "is recorded. Token counts, wall time and LOC require correctness context. The deterministic "
              "verifiers cover selected behaviors and are not a production-readiness guarantee. "
              "The original question verifier may reject a numerically correct percentage with different decimal "
              "formatting (for example, 3.5% versus its expected 3.500%). Raw verdicts are preserved; any source-reviewed "
              "adjudication is explicitly separate. "
              "The refactor verdict includes a size gate: the main file must lose at least 20% of its nonblank "
              "lines. Failing that gate does not by itself mean a behavioral regression. "
              "No dollar estimate or monetary-savings claim is made, and these measurements are not compared "
              "with Claude costs or native Claude plugin runs.", "",
              "## Provenance", ""]
    lines += table(["Item", "Recorded value"], [[k, config.get(k, 'N/A')] for k in
                   ('repo_commit', 'ponytail_commit', 'scenario_sha256', 'runner_sha256', 'python')])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path, help='raw run directory or previously exported JSONL file')
    parser.add_argument('--out', required=True, type=Path, help='output prefix (.jsonl and .md are appended)')
    args = parser.parse_args()
    if args.run_dir.is_file():
        rows = [json.loads(line) for line in args.run_dir.read_text().splitlines() if line.strip()]
        config_file = args.run_dir.with_name(args.run_dir.stem + '-config.json')
    elif args.run_dir.is_dir():
        files = sorted(args.run_dir.glob('*/result.json'))
        review_file = args.run_dir / 'adjudications.json'
        adjudications = json.loads(review_file.read_text()) if review_file.exists() else {}
        rows = [public_row(p.parent, adjudications) for p in files]
        config_file = args.run_dir / 'run_config.json'
    else:
        parser.error('input must be an existing run directory or exported JSONL file')
    keys = [(r['scenario'], r['seed'], r['arm'], r['rep']) for r in rows]
    if len(set(keys)) != len(keys):
        parser.error('Duplicate scenario/seed/arm/repetition cells; do not silently double-count them.')
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    config = {k: v for k, v in config.items() if k in {
        'model', 'effort', 'cli', 'python', 'seeds', 'jobs', 'scenario_sha256',
        'repo_commit', 'ponytail_commit', 'runner_sha256', 'planned_cells', 'schedule'}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    Path(str(args.out) + '.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    Path(str(args.out) + '-config.json').write_text(json.dumps(config, indent=2) + '\n')
    text = report(rows, config)
    Path(str(args.out) + '.md').write_text(scrub(text, {str(args.run_dir.resolve())}))
    print(f'Exported {len(rows)} cells to {args.out}.jsonl and {args.out}.md')


if __name__ == '__main__':
    main()
