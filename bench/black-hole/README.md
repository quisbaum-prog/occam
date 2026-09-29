# Black-hole benchmark

[Back to Occam](../../README.md) · [Full task prompt](prompt.txt)

The same model creates an animated, offline Gargantua-style black hole as a single `index.html`. Compare **Base**, **Occam full**, and **Ponytail 4.10 full** with identical inputs and one fresh Docker container per attempt. This measures Codex rule text supplied as developer instructions. It does not measure Claude plugin hooks.

The current configuration is **`gpt-6.1-sol`, effort `max`, Fast mode**, with three repetitions per arm by default. Published pilot results use **one repetition per arm**. A pilot is an example of this task, not a general model ranking.

## Run it

Docker Desktop, Python 3, and a signed-in Codex CLI are required. The Docker login is separate from the Codex login. From the repository root:

```powershell
cd bench/black-hole
python tests/selftest.py
python tests/ultra_accounting.py
python tests/fast_mode.py
python bench.py build
python bench.py doctor
python bench.py smoke

# Inspect the plan; no model calls.
python bench.py run --model gpt-6.1-sol --effort max --service-tier fast --repetitions 1 --dry-run

# Three model calls: one fresh container per arm.
python bench.py run --model gpt-6.1-sol --effort max --service-tier fast --repetitions 1

# Nine model calls: three repetitions per arm.
python bench.py run --model gpt-6.1-sol --effort max --service-tier fast --repetitions 3
```

`run` is the only command that invokes a model. It consumes usage from the Codex account. `build`, `doctor`, `smoke`, tests, rendering, and chart generation make no model calls. The model is never silently replaced. Each output directory is new; existing results are never overwritten by a new run.

## Equal conditions

| Item | Setting |
|---|---|
| Agent runtime | Codex CLI 0.159.0, same pinned image ID in all arms |
| Speed | Explicit `service_tier="fast"`, `features.fast_mode=true` in every arm |
| Resources | 2 CPUs, 4 GiB RAM, 256-process limit |
| Task | Byte-identical [prompt](prompt.txt), SHA-256 recorded |
| Extra rules | Empty for Base; full frozen rule-generator text for Occam and Ponytail |
| Generation | Fixed shuffled order, sequential, one attempt per cell |
| Isolation | Empty workspace and fresh HOME/CODEX_HOME; non-root container |
| Host access | One read-only job and one read-only Codex auth file; no writable host mount or Docker socket |
| Personal context | User config, project instructions, memories, plugins, hooks, and additional apps excluded |
| Browser | Playwright 1.63.0, Chromium software rendering, network disabled |
| Recording | 1280 × 800, controlled clock from zero, 10 seconds at 30 fps; still at 5 seconds |

The temporary auth copy is removed before export. Raw session logs remain under gitignored `runs/`; they can contain account-specific information and should not be published without review.

Images are built once and recorded in `runtime-lock.json`. The runner verifies source hashes and image IDs before use. A new build can update system packages; compare the recorded runtime before combining batches. [sources.lock.json](sources.lock.json) pins both rule revisions and hashes. Updating the surrounding Occam checkout does not alter those frozen rules.

Fast is a speed setting separate from reasoning effort. The invocation and live model catalog are retained to verify the request and model support. This CLI's JSON usage does not expose the server's served tier; `service_tier_served` is therefore `null`. We do not infer it from elapsed time. [Official Fast configuration](https://learn.chatgpt.com/docs/agent-configuration/speed).

Max is evaluated as a single session with optional delegation disabled. Ultra, when explicitly selected, permits the model's automatic delegation; all descendants must retain the same model, effort, and arm rules. [Official model controls](https://learn.chatgpt.com/docs/models).

## Scoring

The [original prompt](prompt.txt) is unchanged. These evaluation criteria are separate from the model's task instructions.

| Requirement | Review criterion |
|---|---|
| Shadow | Circular, centered within ±5% of viewport width/height; aspect ratio 0.9–1.1 |
| Size | About 30% of viewport height: 200–280 px at 800 px, allowing for disk occlusion |
| Disk | Bright horizontal accretion disk seen nearly edge-on |
| Lensing | Thin bright rim plus visible curved light above and below the shadow |
| Color | White/gold interior and orange outer regions |
| Motion | Fixed camera and recognizable rotation of disk structures within 5 seconds |
| Controls | Autostart, offline load, Pause/Resume, deterministic Restart |

Each requirement is reviewed as met, partial, or unmet, with a reason. Visual quality is a separate 0–10 rubric: shadow/geometry, disk/lensing, color/structure, rotation, and overall effect each score 0–2. Zero means absent/unconvincing, one recognizable with weaknesses, two clear and coherent. A score requires an explanation.

The browser checks offline load, script errors and external requests, motion, pause stability, resumption, repeatable restart, and viewport fit. Pixel changes demonstrate motion but do not prove rotation, gravitational lensing, or aesthetic quality. Raw checks remain unchanged; any manual correction must be recorded separately. Unscored visual criteria remain `null`.

`comparison/blind/` contains anonymous clips, images, and blank scorecards for independent review. Share only this folder with reviewers; the identity mapping remains in the manifest. The published pilot has no independent visual score, so no objective visual winner is claimed.

## Tokens and timing

Total tokens = input + output across all unique, completed sessions. Cached input is already part of input; reasoning is already part of output. Neither subset is added twice. The first session metadata record owns the session ID. In child logs, `subagent_history_start_ordinal` excludes inherited parent usage. Unique response counters are checked against each session's final cumulative totals. Missing or conflicting usage invalidates that measurement instead of becoming zero.

Savings against Base = `(Base total − arm total) / Base total`. A single three-arm pilot has no confidence interval. More repetitions and independent visual reviews are needed before broad quality or efficiency claims.

Generation time covers the CLI task. Container setup/export and video rendering are separate. Subscription tokens are not converted to dollars, and token savings do not equal a billing reduction. No speed comparison between Fast and Standard is made by this pilot.

## Outputs

Each cell retains the original HTML, metrics, invocation, container configuration, browser checks, still image, and H.264 video. `gallery.html` shows the clips and originals; `comparison/comparison-r1.mp4` places Base, Occam, and Ponytail side by side without selecting a best attempt. Labels stay outside the scenes.

```powershell
python bench.py render runs/YOUR-RUN
python bench.py report runs/YOUR-RUN
```

Software rendering can take longer than the ten-second video. The host allows 1,800 seconds per capture and the browser 300 seconds per screenshot. Rendering retries must reuse the same original HTML and be documented; they are not additional model attempts.

The public `data/` directory contains reviewed metrics, runtime provenance, controls evidence, and the original HTML files. It excludes account metadata and raw sessions. README charts can be rebuilt without model calls:

```powershell
python chart.py
```

## Sources

- [Frozen Occam revision](https://github.com/quisbaum-prog/occam/tree/244c2fc502209167116c9b72dbb0d95a4e0d6df9) and [Ponytail 4.10 rule generator](https://github.com/DietrichGebert/ponytail/blob/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156/hooks/ponytail-instructions.js).
- [Codex 0.159.0 response usage and child-history protocol](https://github.com/openai/codex/blob/rust-v0.159.0/codex-rs/protocol/src/protocol.rs).
- [Playwright controlled clock](https://playwright.dev/python/docs/clock) and [Docker version matching](https://playwright.dev/python/docs/docker).
