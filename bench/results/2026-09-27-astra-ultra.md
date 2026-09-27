# GPT-6 Astra Ultra: baseline, Ponytail and Occam

Observed: **54 completed result files**, **54 valid runs**, 9 scenarios and seeds 1, 2. Planned cells: 54. Costs are unavailable (`cost: null`).

## Method

The target design is the repository's nine original scenarios, seeds 1 and 2, one run per scenario/seed/arm: 54 cells, 18 per arm. The observed counts above and below govern incomplete exports. Recorded CLI: **codex-cli 0.153.4**; configured model: **gpt-6-astra**, effort **ultra** (target: Codex 0.153.4, GPT-6 Astra, Ultra).

The Codex adapter preserves the original task prompts and hidden verifiers. Each cell starts in an isolated workspace and Python environment. Fixtures are generated with `PYTHONHASHSEED=1`, frozen once per scenario/seed, and copied to each arm. Cells are interleaved in a fixed shuffled order (seed 0), with three concurrent cells. The baseline adds no skill rules. Ponytail and Occam receive the exact full-mode rules produced by their SessionStart rule generators through `developer_instructions`. This does **not** reproduce Claude's native plugin lifecycle. Ultra's automatic delegation remains enabled. Global personal skills, memories, user configuration and plugins are excluded; standard Codex built-in skills are the same across arms. Model/effort and injected rules are checked from session evidence.

Token totals use the last cumulative usage for each unique session ID, including delegated sessions. The first `session_meta` identifies each raw rollout; duplicate IDs count once. A missing session metric makes that aggregate unavailable rather than zero. Cached input is a subset of input; reasoning output is a subset of output. Total tokens are input + output, without adding either subset again. The CLI root-session usage is reported separately and is not added to the session aggregate. Tool calls/output characters cover the root CLI stream only. Wall time includes the session, not verification.

If a delegated session is interrupted without a completion event, its recorded counters may omit in-flight work. Such cells retain their functional verdict and observed counters, but all-session token metrics are N/A and excluded from token ratios. `observed_usage` in the JSONL preserves the available counters, while `usage_complete` identifies measurements eligible for those ratios.

All medians and ratios use valid runs, including valid runs that fail the task verifier. Source LOC is a code-file diff-line proxy, including blank lines and comments, with conventional test file/directory names and generated data excluded; the JSONL separately retains the runner's all-text LOC totals. The untruncated captured textual diff and final answer are exported after privacy redaction. The runner's patch excludes JSON and PNG files, so it is not a complete workspace archive. Missing values are `null`/N/A.

## Completion and correctness

| Arm | Results | Valid | Complete usage | Verifier pass (all results) | Verifier pass (valid) | Mean score (valid) |
|---|---|---|---|---|---|---|
| baseline | 18 | 18/18 | 17/18 | 14/18 | 14/18 | 0.922 |
| ponytail | 18 | 18/18 | 18/18 | 15/18 | 15/18 | 0.933 |
| occam | 18 | 18/18 | 18/18 | 16/18 | 16/18 | 0.944 |

### Separate source review

The original verifier verdict and score above remain unchanged. These recorded source reviews are separate adjudications, not additional model runs or edits to the original verifier.

| Scenario | Seed | Arm | Raw pass | Reviewed pass | Reason and evidence |
|---|---|---|---|---|---|
| question | 1 | baseline | False | True | Original verifier false negative caused by percentage formatting; the answer is numerically and semantically correct. billing/overdue.py:4 defines LATE_FEE_RATE = Decimal("0.035"); line 8 defines apply_late_fee. The final answer correctly states 3.5% per started 30-day period after seven grace days. scenarios.py:422 formats Decimal("0.035") * 100 as "3.500", and line 425 rejects "3.5%". |
| question | 1 | occam | False | True | Original verifier false negative caused by percentage formatting; the answer is numerically and semantically correct. billing/overdue.py:4 defines LATE_FEE_RATE = Decimal("0.035"); line 8 defines apply_late_fee. The final answer correctly states 3.5% per started 30-day period after seven grace days. scenarios.py:422 formats Decimal("0.035") * 100 as "3.500", and line 425 rejects "3.5%". |
| question | 1 | ponytail | False | True | Original verifier false negative caused by percentage formatting; the answer is numerically and semantically correct. billing/overdue.py:4 defines LATE_FEE_RATE = Decimal("0.035"); line 8 defines apply_late_fee. The final answer correctly states 3.5% per started 30-day period after seven grace days. scenarios.py:422 formats Decimal("0.035") * 100 as "3.500", and line 425 rejects "3.5%". |
| question | 2 | baseline | False | True | Original verifier false negative caused by percentage formatting; the answer is numerically and semantically correct. ledger/fees.py:4 defines LATE_FEE_RATE = Decimal("0.035"); line 8 defines apply_late_fee. The final answer correctly states 3.5% per started 30-day period after seven grace days. scenarios.py:422 formats Decimal("0.035") * 100 as "3.500", and line 425 rejects "3.5%". |
| question | 2 | occam | False | True | Original verifier false negative caused by percentage formatting; the answer is numerically and semantically correct. ledger/fees.py:4 defines LATE_FEE_RATE = Decimal("0.035"); line 8 defines apply_late_fee. The final answer correctly states 3.5% per started 30-day period after seven grace days. scenarios.py:422 formats Decimal("0.035") * 100 as "3.500", and line 425 rejects "3.5%". |
| question | 2 | ponytail | False | True | Original verifier false negative caused by percentage formatting; the answer is numerically and semantically correct. ledger/fees.py:4 defines LATE_FEE_RATE = Decimal("0.035"); line 8 defines apply_late_fee. The final answer correctly states 3.5% per started 30-day period after seven grace days. scenarios.py:422 formats Decimal("0.035") * 100 as "3.500", and line 425 rejects "3.5%". |
| refactor | 1 | baseline | False | False | The original size gate fails; behavioral checks passed. This is not evidence of a behavioral regression. Original nonblank LOC 77; final nonblank LOC 75. The benchmark requires at most 80% of the original (61.6 lines). The only verifier failure is duplication removed. |
| refactor | 2 | baseline | False | False | The original size gate fails; behavioral checks passed. This is not evidence of a behavioral regression. Original nonblank LOC 77; final nonblank LOC 76. The benchmark requires at most 80% of the original (61.6 lines). The only verifier failure is duplication removed. |
| rootcause | 1 | ponytail | False | False | Confirmed parser limitation, not a formatting-only verifier issue. The patch accepts leading euro/dollar symbols and trailing EUR only. The hidden checks for "EUR 5,50" and "12.50 €" raise Decimal ConversionSyntax, and category_totals also fails. |

| Arm | Original verifier pass (valid) | Pass after documented adjudications (valid) |
|---|---|---|
| baseline | 14/18 | 16/18 |
| ponytail | 15/18 | 17/18 |
| occam | 16/18 | 18/18 |

## Median measurements (valid runs)

| Arm | n | All-session input | Cached input | Output | Reasoning output | Total tokens | Wall s |
|---|---|---|---|---|---|---|---|
| baseline | 18 | 214,581 (n=17/18) | 172,928 (n=17/18) | 4,287 (n=17/18) | 539 (n=17/18) | 218,868 (n=17/18) | 123.2 |
| ponytail | 18 | 257,005 | 206,784 | 4,622 | 927 | 261,053 | 130.8 |
| occam | 18 | 155,454 | 125,120 | 3,532 | 682 | 157,908 | 116.5 |

| Arm | Root input | Root cached | Root output | Root reasoning | Root tool calls | Root tool-output chars | Source LOC + | Source LOC − |
|---|---|---|---|---|---|---|---|---|
| baseline | 105,976 | 91,072 | 2,846 | 295 | 9 | 5,618 | 20 | 0 |
| ponytail | 141,398 | 119,552 | 2,740 | 607 | 10 | 6,818 | 13 | 0 |
| occam | 100,723 | 82,432 | 2,604 | 554 | 6 | 2,462 | 13 | 1 |

## Paired ratios

Geometric mean of within-scenario/seed/repetition ratios, with the repository's `bench.gmean_ci` 95% bootstrap interval (4,000 resamples, fixed bootstrap seed 1). Ratios below 1 mean a smaller measurement, not necessarily better work. Pairs with conflicting fixture hashes are excluded. Both measurements must be available and strictly positive; zero-valued pairs are omitted without smoothing, so n can differ by metric. These are not dollar ratios.

| Comparison | Metric | Pairs | Ratio [95% interval] |
|---|---|---|---|
| ponytail / baseline | all_input | 17 | 1.205 [0.982, 1.519] |
| ponytail / baseline | all_cached | 17 | 1.163 [0.908, 1.547] |
| ponytail / baseline | all_output | 17 | 1.016 [0.866, 1.206] |
| ponytail / baseline | all_reasoning | 17 | 1.414 [1.024, 2.075] |
| ponytail / baseline | all_total | 17 | 1.200 [0.980, 1.510] |
| ponytail / baseline | wall_s | 18 | 1.035 [0.887, 1.222] |
| ponytail / baseline | root_tool_calls | 18 | 1.129 [1.008, 1.283] |
| ponytail / baseline | source_loc_added | 14 | 0.665 [0.563, 0.770] |
| ponytail / baseline | source_loc_removed | 8 | 1.054 [1.000, 1.133] |
| occam / baseline | all_input | 17 | 0.773 [0.655, 0.899] |
| occam / baseline | all_cached | 17 | 0.726 [0.609, 0.862] |
| occam / baseline | all_output | 17 | 0.821 [0.701, 0.969] |
| occam / baseline | all_reasoning | 16 | 0.984 [0.700, 1.417] |
| occam / baseline | all_total | 17 | 0.774 [0.657, 0.901] |
| occam / baseline | wall_s | 18 | 1.008 [0.845, 1.217] |
| occam / baseline | root_tool_calls | 18 | 0.751 [0.671, 0.834] |
| occam / baseline | source_loc_added | 14 | 0.775 [0.700, 0.856] |
| occam / baseline | source_loc_removed | 8 | 1.115 [1.000, 1.291] |
| occam / ponytail | all_input | 18 | 0.640 [0.556, 0.731] |
| occam / ponytail | all_cached | 18 | 0.623 [0.521, 0.745] |
| occam / ponytail | all_output | 18 | 0.807 [0.730, 0.885] |
| occam / ponytail | all_reasoning | 17 | 0.698 [0.519, 0.934] |
| occam / ponytail | all_total | 18 | 0.644 [0.562, 0.734] |
| occam / ponytail | wall_s | 18 | 0.974 [0.896, 1.068] |
| occam / ponytail | root_tool_calls | 18 | 0.665 [0.599, 0.732] |
| occam / ponytail | source_loc_added | 14 | 1.166 [1.042, 1.305] |
| occam / ponytail | source_loc_removed | 8 | 1.057 [1.000, 1.150] |

## Per scenario

Cells show valid verifier passes / valid runs; median all-session total tokens; median wall seconds.

| Scenario | baseline | ponytail | occam |
|---|---|---|---|
| bigfile | 2/2; 167,893 (n=1/2) tok; 82.0 s | 2/2; 248,749 tok; 69.2 s | 2/2; 163,348 tok; 63.5 s |
| data | 2/2; 219,184 tok; 121.7 s | 2/2; 245,748 tok; 165.1 s | 2/2; 177,340 tok; 168.3 s |
| feature | 2/2; 309,532 tok; 162.0 s | 2/2; 287,688 tok; 113.8 s | 2/2; 228,925 tok; 104.3 s |
| fixtures | 2/2; 226,942 tok; 147.1 s | 2/2; 237,108 tok; 125.0 s | 2/2; 162,129 tok; 127.6 s |
| question | 0/2; 33,859 tok; 17.6 s | 0/2; 37,951 tok; 18.4 s | 0/2; 35,492 tok; 16.8 s |
| refactor | 0/2; 246,427 tok; 154.0 s | 2/2; 281,215 tok; 166.9 s | 2/2; 146,586 tok; 144.0 s |
| rootcause | 2/2; 611,136 tok; 151.7 s | 1/2; 370,929 tok; 124.5 s | 2/2; 235,896 tok; 105.8 s |
| security | 2/2; 140,396 tok; 73.1 s | 2/2; 229,238 tok; 121.9 s | 2/2; 137,530 tok; 129.2 s |
| texture | 2/2; 101,552 tok; 128.5 s | 2/2; 290,376 tok; 143.2 s | 2/2; 107,078 tok; 182.3 s |

## Failed or invalid cells

| Scenario | Seed | Arm | Valid | Pass | Notes |
|---|---|---|---|---|---|
| question | 1 | baseline | True | False | FAIL rate stated |
| question | 1 | occam | True | False | FAIL rate stated |
| question | 1 | ponytail | True | False | FAIL rate stated |
| question | 2 | baseline | True | False | FAIL rate stated |
| question | 2 | occam | True | False | FAIL rate stated |
| question | 2 | ponytail | True | False | FAIL rate stated |
| refactor | 1 | baseline | True | False | FAIL duplication removed; loc 77->75 |
| refactor | 2 | baseline | True | False | FAIL duplication removed; loc 77->76 |
| rootcause | 1 | ponytail | True | False | FAIL parse EUR 5,50 InvalidOperation([<class 'decimal.ConversionSyntax'>]); FAIL parse 12.50 € InvalidOperation([<class 'decimal.ConversionSyntax'>]); FAIL report InvalidOperation([<class 'decimal.ConversionSyntax'>]) |

## Limitations

This is an exploratory comparison with two seeds, not 18 independent task families per arm. The bootstrap resamples task pairs, not scenario clusters; its intervals do not establish general performance or isolate run-to-run variance. The texture task is the same task repeated across seeds. Automatic delegation can change the number of sessions and is included where usage is recorded. Token counts, wall time and LOC require correctness context. The deterministic verifiers cover selected behaviors and are not a production-readiness guarantee. The original question verifier may reject a numerically correct percentage with different decimal formatting (for example, 3.5% versus its expected 3.500%). Raw verdicts are preserved; any source-reviewed adjudication is explicitly separate. The refactor verdict includes a size gate: the main file must lose at least 20% of its nonblank lines. Failing that gate does not by itself mean a behavioral regression. No dollar estimate or monetary-savings claim is made, and these measurements are not compared with Claude costs or native Claude plugin runs.

## Provenance

| Item | Recorded value |
|---|---|
| repo_commit | 31215e9c72c6be174f145931c86af0b688ee2f8c |
| ponytail_commit | e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156 |
| scenario_sha256 | 5c3396b420d5bc56f73c410decfc29a6112e19492227cd7535f3e4f6a97be98e |
| runner_sha256 | 43462abba1775a882676e5e9be47eb04b8c1ddd38a679f6bd46926c4bd390a24 |
| python | 3.14.7 (main, Aug  5 2026, 10:29:49) [Clang 21.0.0 (clang-2100.1.1.101)] |
