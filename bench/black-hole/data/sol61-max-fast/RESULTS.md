# Sol 6.1 max · Fast: black-hole pilot

[Back to Occam](../../../../README.md) · [Method and reproduction](../../README.md) · [Machine-readable measurements](pilot.json)

Measured on 2026-09-30 (Europe/Berlin). One attempt per arm, three fresh independent containers. Model, effort, full rules, complete usage, response counters, and speed request are verified. Fast is configured and supported; the served server tier is not exposed by CLI JSON.

| Setup | Input | Cached input (subset) | Output | Reasoning (subset) | Total | Generation seconds | Sessions |
|---|--:|--:|--:|--:|--:|--:|--:|
| base | 991,116 | 925,824 | 33,796 | 15,977 | 1,024,912 | 693.322 | 1 |
| occam | 913,411 | 864,256 | 26,548 | 14,295 | 939,959 | 529.113 | 1 |
| ponytail | 937,412 | 877,440 | 25,560 | 11,596 | 962,972 | 497.184 | 1 |

Occam vs. Base: **8.3% fewer tokens**, a difference of 84,953. Occam vs. Ponytail: **2.4% fewer tokens**.

Savings = (reference total − Occam total) / reference total. Cached input and reasoning are already part of input/output; they are not added again. Totals include all unique completed sessions. No dollar price is inferred from subscription usage. One run per setup supplies no confidence interval.

## Browser evidence

| Check | Base | Occam | Ponytail |
|---|:--:|:--:|:--:|
| offline_load | True | True | True |
| motion_detected | True | True | True |
| pause_stable | True | True | True |
| resume_moves | True | True | True |
| restart_reproducible | True | True | True |
| fits_viewport | True | True | True |

Script errors and external requests are retained in the JSON. Pixel motion does not prove rotation or visual quality. Independent visual scores remain pending; no objective visual winner is claimed.

## Original artifacts

[Base HTML](base.html) · [Occam HTML](occam.html) · [Ponytail HTML](ponytail.html)

[Comparison video](../../../../assets/black-hole/sol61-max-fast.mp4) · [Still at five seconds](../../../../assets/black-hole/sol61-max-fast.png)

## Provenance

The JSON records image IDs, source hashes, unique container IDs, rule revisions, effective speed settings, and live model capabilities. All generation cells use 2 CPUs, 4 GiB RAM, 256 processes, the same image, and no writable host mount.

Captures use Chromium 153.0.8010.12 with SwiftShader, 1280 × 800, a clock starting at zero, and 300 frames at 30 fps. The comparison is H.264, 1920 × 490, exactly ten seconds. Rendering is separate from generation time.

The exact default configuration present during measurement is retained as [measurement-config.json](measurement-config.json); the run explicitly selected Sol 6.1 max/Fast using CLI arguments. The current runner defaults have been changed to max/Fast for convenience. Personal paths, account metadata, auth, and raw sessions are not in this export.
