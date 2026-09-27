# Run the Occam scenarios with GPT-6 Astra Ultra

This adapter runs the existing `scenarios.py` tasks and verifiers through the
Codex CLI. It compares baseline, Ponytail full, and Occam full. **Ultra is the
model effort; it is not Ponytail's ultra mode.**

The September 27, 2026 run uses:

- Occam source: `31215e9c72c6be174f145931c86af0b688ee2f8c`, the value recorded in the run files.
  The repository history was rewritten before publication; the same tree is
  published as `a56e65c770708ba8eb1e54c4616a23ac65824109`.
- Ponytail 4.10.0: `e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156`.
- Codex CLI 0.153.4, model `gpt-6-astra`, effort `ultra`.
- Python 3.14.7, seeds 1 and 2, one attempt per cell, three concurrent cells.
- Nine scenarios, three arms: 54 measured sessions, plus delegated sessions.

## Reproduce

Requires an authenticated Codex CLI, Python, Node (to read Ponytail's existing
rule generator), Git, and a checkout of the pinned Ponytail revision. Model
calls consume the authenticated account's Codex allowance. No API dollar cost
is inferred from subscription usage.

From the repository root:

```sh
python3 bench/selftest.py 1 2 3 4 5 6
python3 bench/test_codex_bench.py
PYTHONHASHSEED=1 python3 bench/codex_bench.py \
  --ponytail /path/to/ponytail \
  --seeds 1 2 --arms baseline,ponytail,occam --jobs 3 \
  --out bench/runs/astra-ultra-new-run
python3 bench/report_codex.py bench/runs/astra-ultra-new-run \
  --out bench/results/astra-ultra-new-run
```

The published report can also be rebuilt without model calls or private logs:

```sh
python3 bench/report_codex.py bench/results/2026-09-27-astra-ultra.jsonl \
  --out /tmp/astra-ultra-rebuilt
```

Keep the adjacent `2026-09-27-astra-ultra-config.json` file for provenance.

The runner uses a fresh temporary workspace, Python venv, and Codex runtime for
each cell. It links the existing auth file only for the duration of the call;
it does not copy credentials into the report. The normal user configuration,
personal skills, plugins, hooks, and memories are excluded. Standard built-in
Codex skills and Ultra delegation remain available equally in all arms.
Sessions use `workspace-write` with network access and no interactive approvals.

All arms receive byte-identical fixture files and the original prompt. Fixtures
are generated once and copied. `PYTHONHASHSEED=1` also stabilizes set ordering in
the original `fixtures` and `bigfile` generators. The recorded fixture hashes
allow pairwise verification.

## What is compared

The full-mode text produced by each plugin's **SessionStart rule generator** is
passed as Codex `developer_instructions`. Baseline uses an empty value. Actual
session logs verify model, effort, and rule presence in the root and children.
This is a **Codex rule-text comparison**, not a reproduction of Claude Code's
plugin hooks, per-prompt reinjection, or specialized SubagentStart lifecycle.

The public JSONL retains task-level metrics, original verdicts, final answers,
and captured textual diffs with private runtime paths removed. Token totals
include every unique root and child session. Reasoning tokens are already part
of output tokens; cached tokens are already part of input tokens. Root-only
tool metrics are labeled separately. Raw session transcripts remain local in
the gitignored run directory and are not suitable for unreviewed publication.
When a child session is interrupted, its last recorded counters may omit
in-flight work. The public data retains these as `observed_usage`, marks
`usage_complete=false`, and excludes that cell from all-session token ratios.
Its task verdict and measured wall time remain available.

The original question verifier can reject `3.5%` when its regex expects
`3.500%`. The original verdict is never replaced. Optional source adjudications
are stored separately in `RUN/adjudications.json`, keyed by cell directory:

```json
{"question-s1-baseline-r0": {"reviewed_pass": true,
  "reason": "A documented verifier false negative",
  "evidence": "Exact source and final-answer evidence goes here"}}
```

Two seeds provide an exploratory comparison. They do not establish general
performance, and the texture task is identical across seeds. Reports preserve
failed tasks and list-price dollar savings are not claimed.

## Configuration references

- [Original benchmark](https://github.com/quisbaum-prog/occam/tree/a56e65c770708ba8eb1e54c4616a23ac65824109/bench)
- [Ponytail rule generator](https://github.com/DietrichGebert/ponytail/blob/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156/hooks/ponytail-instructions.js)
- [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode)
