# Occam

[Deutsch](README.de.md)

**Occam's razor for Claude Code:** do not multiply entities beyond necessity.

Left to itself, a coding agent multiplies all of them: files, dependencies, tool calls, turns, context, words. You pay for each one in tokens, and for most of them again on every later turn. Occam is a 30-line rule set (about 650 tokens) that loads at every session start and tells Claude Code to build less, work lean and talk less.

On Claude Opus 5.5 and Sonnet 5.5 at effort max it cut the cost per task in half and passed at least as many tests as running without it. Without it, both models failed the same job: asked to clean up four copy-pasted exporters, they made the file longer.

## Results at a glance

Six benchmark rounds on four models. Each round gives the same 18 coding tasks to three setups: no plugin, Occam, and [Ponytail](https://github.com/DietrichGebert/ponytail) 4.10, the plugin that inspired Occam. A hidden test suite checks every result.

| Model | Effort | Cost with Occam | Cost with Ponytail | Tests passed (of 18)<br>no plugin · Occam · Ponytail |
|---|---|--:|--:|:-:|
| Claude Opus 5.5 | max | **−51%** | −26% | 16 · **18** · **18** |
| Claude Opus 5.5 | medium | **−11%** | +11% | 17 · **18** · **18** |
| Claude Sonnet 5.5 | max | **−55%** | −9% (not significant) | 16 · **17** · **17** |
| Claude Sonnet 5.5 | medium | **−3%** (not significant) | +26% | 16 · **18** · **18** |
| Claude Haiku 4.5 | – | **−2%** (not significant) | +30% | 10 · **13** · 10 |
| GPT-6 Astra in Codex ¹ | ultra | **−23%** | +20% (not significant) | 14 · **16** · 15 ² |

**How to read it:**
- **Cost:** change per task compared with the same task without a plugin. Minus means cheaper: −51% is about half the price.
- **Not significant:** the 95% confidence interval includes zero, so the difference may be chance. The intervals are in [Results in detail](#results-in-detail).
- **Bold:** best value in the row.
- **Effort:** how much the model may think before it acts (low … max). Thinking is billed as output, so more effort costs more.

¹ Codex reports tokens, not cost: the numbers are total tokens. ² 16 · 18 · 17 after the documented source review: the verifier of the question task rejects a correct `3.5%`.

**In short:** Occam was the cheapest setup in every round and passed at least as many tests as the other two. How much it saves depends on how much the model thinks. At effort max, where thinking is almost half of the bill, it halved the cost on Opus 5.5 and Sonnet 5.5 alike. At effort medium and on Haiku 4.5 the models hardly think: Occam then saves little or nothing (−11% to −2%), but it still passed more tests, for example 18 instead of 16 of 18 on Sonnet 5.5. Ponytail saved money only at effort max and cost more than no plugin in the other rounds.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/change-by-model-dark.svg">
  <img alt="Change vs. no plugin: Occam −51% cost on Opus 5.5 at effort max, −11% at effort medium, −55% on Sonnet 5.5 at effort max, −3% at effort medium, −2% on Haiku 4.5 and −23% tokens on GPT-6 Astra; Ponytail −26%, +11%, −9%, +26%, +30% and +20%" src="assets/change-by-model-light.svg">
</picture>

## Install

In Claude Code:

```
/plugin marketplace add quisbaum-prog/occam
/plugin install occam@occam
```

If Ponytail is installed, remove it first (`/plugin uninstall ponytail@ponytail`). Otherwise every session loads both rule sets.

To try it without installing, from a clone: `claude --plugin-dir ./plugin`

The plugin uses two hooks: `SessionStart` loads the rules (also after `/clear` and compaction) and `SubagentStart` gives subagents a ~100-token version. Both run a 14-line POSIX `sh` script that needs only `sh`, `cat` and `awk` (Git Bash on Windows, which Claude Code uses anyway). No Node, no Python, and nothing runs on each prompt; Ponytail uses three Node.js hooks, one of them on every prompt.

**Claude desktop app, Cowork and chat:**

- **Desktop app, Code tab:** this is Claude Code, so the plugin and its hooks work exactly as in the terminal. Use the same `/plugin` commands in the prompt box, or add the marketplace `quisbaum-prog/occam` in the app's plugin settings.
- **Cowork:** Cowork plugins support `SessionStart` hooks as well, so the same plugin should work there (not benchmarked).
- **Plain chat (claude.ai, mobile):** no plugins, so no hooks. Paste [`app/preferences.txt`](app/preferences.txt) (129 words) into your personal preferences to have it always on, or upload [`app/occam/`](app/occam) as a skill for on-demand use. Skills only load when the model decides they fit; JetBrains measured zero activations in ten sessions for Ponytail as a plain skill, so the preferences text is the reliable route.

## Use

| | |
|---|---|
| `/occam:occam lite` | only "Work lean" and "Talk less", builds as usual |
| `/occam:occam full` | everything (default) |
| `/occam:occam off` | off for this session |
| `"env": {"OCCAM_LEVEL": "lite"}` in `~/.claude/settings.json` | default level for new sessions (`full`, `lite`, `off`) |
| `/occam:audit 7` | where your tokens went in the last 7 days |

The audit also runs straight from a terminal: `python3 plugin/tools/audit.py --days 30`. It reads your transcripts under `~/.claude/projects` and shows cost by token type, the **context tax** per tool (what a tool output costs because every later turn re-reads it), the most expensive single outputs, and common patterns such as whole large files read, noisy installs and files read twice. Run it before and after installing to see the effect on your own sessions.

## How it works

An agent session pays three times:

1. **Output, mostly thinking.** On Opus 5.5 at effort max, thinking alone was 45–48% of the bill in every setup.
2. **Cache writes.** Every new piece of context (tool output, messages, thinking blocks) is written once to the 1-hour prompt cache at twice the input price (31–37%).
3. **Cache reads.** After that, *every later turn* reads all of it again (5–7%).

Ponytail targets the code the agent writes. Occam also targets how the agent works: fewer turns, targeted reads instead of whole files, quiet tool output, no second opinions during verification, one generator instead of thirty hand-written files. Most of the savings come from less thinking and fewer turns.

That is also why the saving depends on effort. At effort medium the models hardly think, and cache writes make up 57–66% of the bill; a rule set can then only trim output and tool noise. Everything a plugin loads costs context, too: Occam's rules and its two skill descriptions add about 900 tokens to every session, Ponytail's rules and six skills about 3,100 (measured on Sonnet 5.5), and every later turn reads them again.

**The rules.** [`plugin/skills/occam/rules.md`](plugin/skills/occam/rules.md) is the whole thing, 30 lines:

- **Build less:** a ladder (not needed now → already in the codebase → stdlib → native platform feature → installed dependency → minimum code), no unrequested abstractions or files, generate repeated structure with a loop or seeded generator, fix bugs at the root including copied logic, leave one small runnable check.
- **Work lean:** batch independent tool calls, locate before reading, never dump large files, logs or data, quiet command output, edit instead of rewrite, verify once and stop, think hard only where it changes the outcome.
- **Talk less:** no preamble, no narration, no recap; end with the result, what was skipped, real caveats.
- **Never cut:** understanding the problem, validation at trust boundaries, data-loss handling, security, accessibility, anything explicitly requested.

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
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-dark.svg">
  <img alt="Median cost per task on Claude Opus 5.5 at effort max: Occam is cheapest in all nine scenarios" src="assets/cost-per-scenario-light.svg">
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
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-medium-dark.svg">
  <img alt="Median cost per task on Claude Opus 5.5 at effort medium: Occam is cheapest in eight of nine scenarios" src="assets/cost-per-scenario-medium-light.svg">
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
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-sonnet-max-dark.svg">
  <img alt="Median cost per task on Claude Sonnet 5.5 at effort max: Occam is cheapest in all nine scenarios" src="assets/cost-per-scenario-sonnet-max-light.svg">
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
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-sonnet-medium-dark.svg">
  <img alt="Median cost per task on Claude Sonnet 5.5 at effort medium: Occam and no plugin are close, Ponytail is the most expensive in eight of nine scenarios" src="assets/cost-per-scenario-sonnet-medium-light.svg">
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
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-haiku-dark.svg">
  <img alt="Median cost per task on Claude Haiku 4.5: Occam and no plugin are close, Ponytail is the most expensive in six of nine scenarios, and every setup fails tests" src="assets/cost-per-scenario-haiku-light.svg">
</picture>
</details>

### GPT-6 Astra in Codex, effort ultra

54 sessions in Codex CLI 0.153.4. Codex has no Claude Code plugins, so each setup got the full-mode rule text as developer instructions; this tests the rules, not the plugin hooks. Total tokens are input + output across the root session and its subagents.

| | Total tokens vs. no plugin | Reasoning tokens | Tool calls | Tests passed |
|---|---|--:|--:|--:|
| no plugin | – | 539 | 9 | 14/18 (16) |
| **Occam** | **−23%** [−34 … −10] | 682 | 6 | 16/18 (**18**) |
| Ponytail 4.10 | +20% [−2 … +51] | 927 | 10 | 15/18 (17) |

- Occam vs. Ponytail directly: **−36%** total tokens [−44 … −27], 18 pairs. Wall time did not change (Occam ×1.01 [0.85–1.22]).
- Reasoning tokens and tool calls are medians per task, tool calls in the root session only. In parentheses: tests passed after the documented source review. The question verifier expects `3.500%` and rejected all six correct `3.5%` answers; the raw verdicts stay, the review is recorded separately.
- Failed after that review: without a plugin, both refactor runs kept behavior but missed the 20% shrink gate (77 → 75 and 76 lines). Ponytail missed two currency formats in one root-cause run.
- One interrupted subagent left a no-plugin run with incomplete token counts; it is excluded from the token ratios (17 pairs).
- [Full report](bench/results/2026-09-27-astra-ultra.md) · [reproduce](bench/CODEX.md)

<details>
<summary>Total tokens per task in all nine scenarios</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/tokens-per-scenario-astra-dark.svg">
  <img alt="Median total tokens per task on GPT-6 Astra in Codex: Occam uses the fewest in seven of nine scenarios" src="assets/tokens-per-scenario-astra-light.svg">
</picture>
</details>

### Other experiments

- **Variant v2** with an extra "verify in proportion" rule, on Opus 5.5 at effort max: ×0.99 [0.89–1.12] vs. v1, no difference. Only its sharper root-cause rule ("copied logic") was kept. It lives in `bench/variants/v2`.

## Check it yourself

### Raw data

Every claim above comes from one of these files. Each holds one line per session: every metric (tokens by type, cost, turns, tool calls, tool output size), the verifier result, the agent's final answer and its full code diff.

| Round | File | Sessions | Cost at list price |
|---|---|--:|--:|
| Opus 5.5, effort max | [`opus-r1.jsonl`](bench/results/opus-r1.jsonl) | 72 (18 of them variant v2) | $43.63 |
| Opus 5.5, held-out seed 3 | [`opus-val.jsonl`](bench/results/opus-val.jsonl) | 18 | $13.82 |
| Opus 5.5, effort medium | [`opus-medium.jsonl`](bench/results/opus-medium.jsonl) | 54 | $7.26 |
| Sonnet 5.5, effort max | [`sonnet-max.jsonl`](bench/results/sonnet-max.jsonl) | 54 | $25.76 |
| Sonnet 5.5, effort medium | [`sonnet-medium.jsonl`](bench/results/sonnet-medium.jsonl) | 54 | $3.39 |
| Haiku 4.5 | [`haiku-v1.jsonl`](bench/results/haiku-v1.jsonl) | 54 | $4.00 |
| GPT-6 Astra in Codex, effort ultra | [`2026-09-27-astra-ultra.jsonl`](bench/results/2026-09-27-astra-ultra.jsonl) | 54 | tokens only |
| Sonnet 5, calibration without plugin | [`cal-sonnet.jsonl`](bench/results/cal-sonnet.jsonl) | 9 | $2.42 |

Rebuild the numbers without any API calls:

```
# all charts, and the overview table with intervals
python3 bench/chart.py assets
# one round: medians, cost by token type, cost per scenario, failures
python3 bench/bench.py report bench/results/sonnet-max.jsonl
# the Codex round
python3 bench/report_codex.py bench/results/2026-09-27-astra-ultra.jsonl --out /tmp/astra
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

- Single-prompt tasks. The effect per turn is the same in long sessions, but whether the rules hold up over hours of work is not measured here. That is what `/occam:audit` is for.
- Nine scenarios, mostly Python. Frontend tasks, where Ponytail shines with native HTML elements, are missing.
- Two seeds per round, one run per task: 18 pairs. Small effects (a few percent) are within the noise.
- Measured with Claude Code 2.1.283 (Sonnet 5.5: 2.1.284; GPT-6 Astra: Codex CLI 0.153.4). Thinking content is not visible, only its length.
- Costs are list-price estimates from session metadata.

## What's inside

```
plugin/
  hooks/hooks.json         SessionStart (startup|resume|clear|compact) + SubagentStart
  hooks/occam.sh           POSIX sh, prints the rules for the current OCCAM_LEVEL
  hooks/subagent.json      short version for subagents (~100 tokens)
  skills/occam/rules.md    the rules
  skills/occam/SKILL.md    /occam:occam full|lite|off
  skills/audit/SKILL.md    /occam:audit [days]
  tools/audit.py           transcript audit, stdlib only
app/                       preferences text and skill for the plain chat
bench/                     the benchmark, stdlib only; results/ holds the raw data
assets/                    README charts (generated by bench/chart.py), social preview image
```

## Credits

- [Ponytail](https://github.com/DietrichGebert/ponytail) by Dietrich Gebert: the "lazy senior dev" ladder and the pattern of injecting rules through a SessionStart hook. Occam borrows the idea, not the code.
- [JetBrains' independent Ponytail benchmark](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/), which showed that re-reading context dominates an agent's bill.

## Support

Occam is free. If it saves you tokens, you can [sponsor the project on GitHub](https://github.com/sponsors/quisbaum-prog); it pays for benchmark runs on new models.

## License

[MIT](LICENSE)
