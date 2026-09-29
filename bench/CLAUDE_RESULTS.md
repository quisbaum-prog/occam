# Claude coding benchmarks

[Back to Occam](../README.md) · [Deutsch](CLAUDE_RESULTS.de.md)

## Results in detail

### How it was measured

`bench/` generates nine scenarios **procedurally from a seed**. Every setup gets byte-identical tasks, and every session runs headless with its own HOME, its own config directory and a fresh virtualenv, so no plugin leaks into the baseline and no preinstalled package skews a result. The plugins are loaded with `--plugin-dir`; the session logs confirm that each setup sees only its own rules.

| Scenario | Task | Trap |
|---|---|---|
| rootcause | invoices fail after an import; the bug sits in a shared helper with four callers and one copied implementation | 3 MB log, 18 filler modules |
| question | which function applies the late fee, at what rate? | over-research |
| feature | CLI feature: due dates with `--overdue` and JSON output, or tags with a filter and CSV | over-engineering, missing date validation |
| data | revenue by region and top products from 60k CSV rows with broken rows and duplicates | dumping the CSV into context |
| fixtures | 20–30 valid orders plus one per validation error code, with a test | writing each file by hand |
| texture | seamless value or Perlin noise as PNG, deterministic per seed | numpy/Pillow instead of stdlib |
| security | download endpoint for a small file-share server | path traversal (10 attacks) |
| refactor | merge four copy-pasted CSV exporters without changing behavior | changing behavior, or not shrinking |
| bigfile | cap one rule in a 2,500-line module | reading or rewriting the whole file |

A hidden verifier scores each run. Every verifier is tested itself: it must fail on the untouched workspace and pass with a reference solution (54/54 on seeds 1–6: `python3 bench/selftest.py 1 2 3 4 5 6`).

Each round runs the nine scenarios on seeds 1 and 2, so every setup solves 18 tasks. In the tables below:

- **Cost vs. no plugin:** for each task, the cost with the plugin divided by the cost without it; the geometric mean of these 18 ratios, with a 95% bootstrap confidence interval in brackets.
- **Cost** is the list price Claude Code reports for the session, including thinking and cache.
- **Thinking tokens** and **turns** are medians per task.

### Claude Opus 5.5, effort max

54 sessions, $36 at list price.

| | Cost vs. no plugin | Thinking tokens | Turns | Tests passed |
|---|---|--:|--:|--:|
| no plugin | – | 21.8k | 13 | 16/18 |
| **Occam** | **−51%** [−58 … −42] | 11.9k | 6 | **18/18** |
| Ponytail 4.10 | −26% [−35 … −14] | 15.0k | 10 | 18/18 |

- Occam vs. Ponytail directly: **−34%** [−41 … −25].
- Where the money goes (sum over 18 tasks, no plugin → Occam): thinking $8.03 → $3.58, cache writes $5.23 → $2.83, other output $2.16 → $0.88, cache reads $1.19 → $0.36. The breakdown from token counts reproduces the reported costs to the cent.
- Without a plugin, Opus failed the refactor task twice: it made the exporter file *longer* while "cleaning it up" (77 → 83 and 88 lines).
- Confirmed on **held-out tasks** (seed 3, 9 pairs): −45% [−54 … −34], turns 14 → 6, 9/9 passed. Without a plugin 8/9: the refactor shrank only to 65 lines.

<details>
<summary>Cost per task in all nine scenarios</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/cost-per-scenario-dark.svg">
  <img alt="Median cost per task on Claude Opus 5.5 at effort max: Occam is cheapest in all nine scenarios" src="../assets/cost-per-scenario-light.svg">
</picture>
</details>

### Claude Opus 5.5, effort medium

54 sessions, $7.26 at list price.

| | Cost vs. no plugin | Thinking tokens | Turns | Tests passed |
|---|---|--:|--:|--:|
| no plugin | – | 186 | 4 | 17/18 |
| **Occam** | **−11%** [−17 … −5] | 138 | 4 | **18/18** |
| Ponytail 4.10 | +11% [+2 … +20] | 202 | 4 | 18/18 |

- Occam vs. Ponytail directly: **−20%** [−23 … −17]. Occam also cut output by 27% and tool output by 37%.
- At medium the model hardly thinks, so the biggest lever is gone: cache writes make up 58–66% of the bill.
- Without a plugin the refactor trap struck again (77 → 75 lines).

<details>
<summary>Cost per task in all nine scenarios</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/cost-per-scenario-medium-dark.svg">
  <img alt="Median cost per task on Claude Opus 5.5 at effort medium: Occam is cheapest in eight of nine scenarios" src="../assets/cost-per-scenario-medium-light.svg">
</picture>
</details>

### Claude Sonnet 5.5, effort max

54 sessions, $25.76 at list price, measured on 2026-09-28 with Claude Code 2.1.284.

| | Cost vs. no plugin | Thinking tokens | Turns | Tests passed |
|---|---|--:|--:|--:|
| no plugin | – | 29.8k | 16.5 | 16/18 |
| **Occam** | **−55%** [−62 … −46] | 13.1k | 8 | **17/18** |
| Ponytail 4.10 | −9% [−19 … +3] | 27.0k | 13 | 17/18 |

- Occam vs. Ponytail directly: **−50%** [−57 … −43]. Occam was the cheapest setup in all nine scenarios and needed half as many turns as no plugin.
- Where the money goes (sum over 18 tasks, no plugin → Occam): thinking $4.80 → $2.07, cache writes $3.33 → $1.65, other output $1.51 → $0.52, cache reads $1.67 → $0.52. Thinking alone was 42–44% of the bill in every setup.
- All four failures are in the refactor task, and all four are real refactors that kept the behavior but missed the verifier's 20% cut (61 lines): Occam and Ponytail once each with 66 lines, no plugin twice, with 67 lines and with 89, longer than the original 77.
- The Ponytail sessions started a few minutes after the other two setups and ran alongside them.

<details>
<summary>Cost per task in all nine scenarios</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/cost-per-scenario-sonnet-max-dark.svg">
  <img alt="Median cost per task on Claude Sonnet 5.5 at effort max: Occam is cheapest in all nine scenarios" src="../assets/cost-per-scenario-sonnet-max-light.svg">
</picture>
</details>

### Claude Sonnet 5.5, effort medium

54 sessions, $3.39 at list price, measured on 2026-09-28 with Claude Code 2.1.284.

| | Cost vs. no plugin | Thinking tokens | Turns | Tests passed |
|---|---|--:|--:|--:|
| no plugin | – | 36 | 4 | 16/18 |
| **Occam** | **−3%** [−11 … +4] | 79 | 3 | **18/18** |
| Ponytail 4.10 | +26% [+16 … +36] | 98 | 4.5 | 18/18 |

- Occam vs. Ponytail directly: **−23%** [−25 … −21]. Occam cut output by 20% and tool output by 32%; the cost difference to no plugin is not significant.
- Without a plugin Sonnet failed the refactor task twice: the exporter file stayed at 77 lines on one seed and shrank only to 63 on the other (the verifier wants a cut of at least 20%, to 61 lines).
- Ponytail was more expensive than no plugin in eight of nine scenarios, and its extra cost is almost exactly the price of what it loads: about 3,100 tokens in every session, and writing them to the cache and re-reading them each turn costs about 25% of a typical session at this effort. Occam loads about 900 tokens (about 7%), which its leaner work pays back.
- The Ponytail sessions ran after the other two setups had finished, with the same model, harness and tasks.

<details>
<summary>Cost per task in all nine scenarios</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/cost-per-scenario-sonnet-medium-dark.svg">
  <img alt="Median cost per task on Claude Sonnet 5.5 at effort medium: Occam and no plugin are close, Ponytail is the most expensive in eight of nine scenarios" src="../assets/cost-per-scenario-sonnet-medium-light.svg">
</picture>
</details>

### Claude Haiku 4.5

54 sessions, $4.00 at list price. Haiku 4.5 has no effort setting.

| | Cost vs. no plugin | Thinking tokens | Turns | Tests passed |
|---|---|--:|--:|--:|
| no plugin | – | 632 | 6 | 10/18 |
| **Occam** | **−2%** [−9 … +4] | 666 | 5.5 | **13/18** |
| Ponytail 4.10 | +30% [+7 … +56] | 1,047 | 7 | 10/18 |

- Occam vs. Ponytail directly: **−24%** [−37 … −8]. Occam cut output by 10% and tool output by 28%; the cost difference to no plugin is not significant.
- Haiku failed tasks in every setup; none of the six refactor runs passed.

<details>
<summary>Cost per task in all nine scenarios</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/cost-per-scenario-haiku-dark.svg">
  <img alt="Median cost per task on Claude Haiku 4.5: Occam and no plugin are close, Ponytail is the most expensive in six of nine scenarios, and every setup fails tests" src="../assets/cost-per-scenario-haiku-light.svg">
</picture>
</details>

### Other experiments

- **Variant v2** with an extra "verify in proportion" rule, on Opus 5.5 at effort max: ×0.99 [0.89–1.12] vs. v1, no difference. Only its sharper root-cause rule ("copied logic") was kept. It lives in `bench/variants/v2`.

## Check it yourself

### Raw data

Every claim above comes from one of these files. Each holds one line per session: every metric (tokens by type, cost, turns, tool calls, tool output size), the verifier result, the agent's final answer and its full code diff.

| Round | File | Sessions | Cost at list price |
|---|---|--:|--:|
| Opus 5.5, effort max | [`opus-r1.jsonl`](results/opus-r1.jsonl) | 72 (18 of them variant v2) | $43.63 |
| Opus 5.5, held-out seed 3 | [`opus-val.jsonl`](results/opus-val.jsonl) | 18 | $13.82 |
| Opus 5.5, effort medium | [`opus-medium.jsonl`](results/opus-medium.jsonl) | 54 | $7.26 |
| Sonnet 5.5, effort max | [`sonnet-max.jsonl`](results/sonnet-max.jsonl) | 54 | $25.76 |
| Sonnet 5.5, effort medium | [`sonnet-medium.jsonl`](results/sonnet-medium.jsonl) | 54 | $3.39 |
| Haiku 4.5 | [`haiku-v1.jsonl`](results/haiku-v1.jsonl) | 54 | $4.00 |
| Sonnet 5, calibration without plugin | [`cal-sonnet.jsonl`](results/cal-sonnet.jsonl) | 9 | $2.42 |

Rebuild the numbers without any API calls:

```
# all charts, and the overview table with intervals
python3 bench/chart.py assets
# one round: medians, cost by token type, cost per scenario, failures
python3 bench/bench.py report bench/results/sonnet-max.jsonl
```

Full session transcripts are not published because they contain account-specific data; run the benchmark to get your own.

### Run the benchmark

> **Warning:** the benchmark runs Claude Code with `--permission-mode bypassPermissions` inside temporary workspaces. Run it in a disposable VM or container.

Each session gets a fresh HOME, so your normal Claude Code login is not visible to it. Export `ANTHROPIC_API_KEY`, or create a subscription token with `claude setup-token` and export it as `CLAUDE_CODE_OAUTH_TOKEN`.

```
cd bench
python3 selftest.py
python3 bench.py run --model claude-sonnet-5-5 --effort max \
  --arms baseline,occam=../plugin,ponytail=/path/to/ponytail --seeds 1 2 --jobs 5 --out runs/mine
python3 bench.py report runs/mine
python3 bench.py export runs/mine results/mine.jsonl
```

One Sonnet 5.5 session at effort max costs about $0.05–1.10 at list price, the full three-setup matrix on two seeds about $26 (at effort medium about $3.40; Opus 5.5 at effort max about $36). On a subscription this counts against your usage limits instead.

## Limits

- Measured with Claude Code 2.1.283 (Sonnet 5.5: 2.1.284). Thinking content is not visible, only its length.
- Single-prompt tasks. Sessions spanning hours of work were not measured. Use `/occam:audit` to inspect your own longer sessions.
- Nine scenarios, mostly Python. These coding rounds contain no frontend task. The separate black-hole pilot is documented in [black-hole/](black-hole/README.md).
- Two seeds per round, one run per task: 18 pairs. Small effects (a few percent) are within the noise.
- Costs are list-price estimates from session metadata.

