# Occam

[Deutsch](README.de.md) · [Video comparison](#black-hole-benchmark-sol-61-max) · [Install](#install) · [Reproduce](bench/black-hole/README.md)

**Build less. Work lean. Talk less.**

Occam is a 30-line rule set for coding agents: prefer existing code and standard tools, read only what matters, and keep output concise. It ships as a Claude Code plugin; the rules are also tested in Codex.

**Sol 6.1 max, Fast: 8.3% fewer total tokens with Occam on the black-hole task.** All three animations pass the browser checks. In the separate Claude coding benchmarks, Occam reduced task cost by **51% on Opus 5.5 max** and **55% on Sonnet 5.5 max**, while passing at least as many tests.

## Black-hole benchmark: Sol 6.1 max

One prompt, three fresh Docker containers. Each setup creates one offline HTML animation with a black shadow, glowing accretion disk, curved light above and below it, visible motion, and Pause/Resume/Restart controls. The model is **`gpt-6.1-sol`**, reasoning **`max`**, with **Fast explicitly requested in every arm**.

**Base → Occam → Ponytail 4.10**, left to right. Ten seconds at 30 fps; the same browser, viewport, software renderer, and animation clock.

[![Black-hole comparison](assets/black-hole/sol61-max-fast.png)](assets/black-hole/sol61-max-fast.mp4)

[Watch/download the original MP4](assets/black-hole/sol61-max-fast.mp4) · [Still image at 5 seconds](assets/black-hole/sol61-max-fast.png)

In the still, Occam's disk forms a broad raised arc above the shadow and a curved band below it. Compare the shape, texture, and motion of all three results in the video.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/black-hole/sol61-max-fast-tokens-dark.svg">
  <img alt="Total tokens in the Sol 6.1 max Fast black-hole pilot: Base 1,024,912, Occam 939,959, Ponytail 962,972" src="assets/black-hole/sol61-max-fast-tokens-light.svg">
</picture>

| Setup | Total tokens | Change vs. Base | Generation time | Browser checks |
|---|--:|--:|--:|:--|
| Base | 1,024,912 | — | 11.56 min | Pass |
| **Occam full** | 939,959 | −8.3% | 8.82 min | Pass |
| Ponytail 4.10 full | 962,972 | −6.0% | 8.29 min | Pass |

Occam uses **84,953 fewer tokens than Base** and **2.4% fewer than Ponytail**. [Original HTML files and full measurements](bench/black-hole/data/sol61-max-fast/RESULTS.md) · [Prompt, scoring, and reproduction](bench/black-hole/README.md).

**How to interpret this:** one attempt per setup on one visual task, with no confidence interval. Tokens are input + output; cached input and reasoning are included once. This is a token comparison, not a dollar-cost estimate. Fast is verified in the invocation and model catalog; the CLI does not expose the server's served tier. Visual quality can be compared in the video; an independent visual score is still pending.

## Claude coding benchmarks

Five rounds, three models, 18 tasks per setup in each round. Claude loads the actual plugins; hidden tests check the resulting code. Cost changes are geometric means of matched task ratios.

| Model | Effort | Occam vs. no plugin | Ponytail vs. no plugin | Tests passed / 18<br>Base · Occam · Ponytail |
|---|---|--:|--:|:--:|
| Opus 5.5 | max | **−51%** | −26% | 16 · **18** · 18 |
| Sonnet 5.5 | max | **−55%** | −9% ¹ | 16 · **17** · 17 |
| Opus 5.5 | medium | **−11%** | +11% | 17 · **18** · 18 |
| Sonnet 5.5 | medium | −3% ¹ | +26% | 16 · **18** · 18 |
| Haiku 4.5 | — | −2% ¹ | +30% | 10 · **13** · 10 |

¹ The 95% confidence interval includes zero. Small changes are not established savings. Cost here is the list-price estimate reported by Claude Code, including thinking and cache. These tasks differ from the visual Codex pilot.

<details>
<summary>Cost chart, methods, confidence intervals, and raw data</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/change-by-model-dark.svg">
  <img alt="Claude task cost changes with 95% confidence intervals: Occam saves 51% on Opus max and 55% on Sonnet max; smaller effects at medium and on Haiku" src="assets/change-by-model-light.svg">
</picture>

[Detailed results and all raw data](bench/CLAUDE_RESULTS.md). The nine seeded scenarios cover root-cause repair, a code question, a CLI feature, CSV analysis, fixture generation, a procedural texture, path-traversal security, refactoring, and a targeted large-file edit. Every arm receives the same fixtures in an isolated workspace. Verifier reference checks and held-out Opus tasks are documented in the report.

Rebuild the chart without model calls:

```shell
python bench/chart.py assets
```

</details>

## Install

In Claude Code:

```text
/plugin marketplace add quisbaum-prog/occam
/plugin install occam@occam
```

If Ponytail is already installed, remove it first with `/plugin uninstall ponytail@ponytail` so both rule sets do not load into the same session. To try a local clone: `claude --plugin-dir ./plugin`.

The plugin uses POSIX `sh` hooks. `SessionStart` supplies the full rules; `SubagentStart` supplies a short version. No Node or Python is needed for these hooks. The [Codex benchmark](bench/black-hole/README.md) passes the frozen full rule text as developer instructions.

For plain chat, use [preferences.txt](app/preferences.txt) in your preferences, or [the chat skill](app/occam/) for on-demand use.

## Use

| Command | Effect |
|---|---|
| `/occam:occam full` | All rules; default |
| `/occam:occam lite` | Work lean and talk less; build as usual |
| `/occam:occam off` | Disable Occam for this session |
| `/occam:audit 7` | Review the last seven days of Claude Code token usage |

Set the default for new Claude sessions in `~/.claude/settings.json`: `"env": {"OCCAM_LEVEL": "lite"}` (`full`, `lite`, or `off`). The audit also runs directly: `python plugin/tools/audit.py --days 30`. It reads local Claude transcripts and reports token costs, repeated context, and large tool outputs.

## The rules

The complete text lives in [rules.md](plugin/skills/occam/rules.md).

- **Build less:** prefer what already exists, standard tools, and minimal code; generate repeated structures; fix shared causes.
- **Work lean:** locate before reading, batch independent calls, keep tool output small, and verify the change.
- **Talk less:** concise, useful results without routine narration.
- **Never cut:** understanding, security, accessibility, validation, data-loss handling, or anything explicitly requested.

The benchmarks support savings on these tasks. They do not establish that every model, project, long conversation, or aesthetic result improves. Use the audit and repeated tests to measure your own work.

## Reproduce the visual benchmark

With Docker running and Codex signed in:

```shell
cd bench/black-hole
python bench.py build
python bench.py run --model gpt-6.1-sol --effort max --service-tier fast --repetitions 1
```

This starts three independent model runs. Use `--dry-run` to inspect the plan, or `--repetitions 3` for nine runs. [Full setup and evaluation guide](bench/black-hole/README.md).

## Credits and support

[Ponytail](https://github.com/DietrichGebert/ponytail) by Dietrich Gebert inspired the rule-injection approach and the preference for existing tools. The comparison includes its frozen 4.10 rules.

Occam is free under the [MIT license](LICENSE). [Sponsor the project](https://github.com/sponsors/quisbaum-prog) to support further benchmark runs.
