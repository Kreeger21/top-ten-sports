# NBA 2K calibration benchmark

Fan-maintained scrape of 2kratings.com; not affiliated with or endorsed by 2K Sports.

80/20 deterministic ridge regression on six transparent category averages derived from granular 2K attributes; badges excluded.

Players: 528

| Position | Test MAE | Test R² | Strongest category | 2K max | 85+ | 90+ |
|---|---:|---:|---|---:|---:|---:|
| G | 1.71 | 0.90 | Outside Scoring | 98 | 25 | 10 |
| F | 1.31 | 0.91 | Outside Scoring | 97 | 21 | 9 |
| C | 1.81 | 0.86 | Defense | 98 | 11 | 4 |

## Direct franchise comparison

Matched players: 359
Mean Overall — ours: 68.53; 2K: 77.92
Mean 2K minus ours: 9.38
Correlation: 0.615

The strong category regressions show that 2K Overall is highly recoverable from its published category ratings. Outside scoring is most influential for guards and forwards, while centers are balanced across defense, outside scoring, inside scoring, and rebounding. The 2K distribution also has a much wider elite range than the current frozen franchise display curve.

This benchmark can guide a later display-curve review, but it cannot reveal 2K's proprietary formula. Its category ratings may themselves be tuned to reach a desired Overall, so coefficients describe correlation rather than causation.