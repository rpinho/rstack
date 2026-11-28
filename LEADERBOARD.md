# Model leaderboard

Ricardo's own rank (2026-11-28): just use Opus 5.5 or Gemini 4 Neon. Opus 5.5 and Neon tied #1, Astra #2, Fable 5.2 #3, Sol #4, Sonnet 5.5 #5, Argon and Carbon #6-7; the rest are unranked.

Everyday work over 30 days: 2026-10-29 through 2026-11-28 (UTC). The window uses run start time when available and grade time or date for historical grades. This table uses eligible grades from the scorer's grade ledgers, including mirrors. The weighted score uses pass=1, partial=half and fail=0. The daily grades-feed tally uses observation dates and reports each verdict separately. Routing positions below may use inherited evidence. Each weighted score here uses grades for the displayed model version.

Runs includes ungraded work. The score denominator n counts eligible pass, partial and fail grades, including historical grades without a run record, so n can exceed Runs. Within-role ranks use the Wilson lower bound and require n>=20. Owner ranks retain taste + cost. The intervals describe these observations. Task mix, correlated jobs and subjective grades limit comparisons.

Cost per passed task is a model-wide estimate. Cells give median / mean and the number of estimates over the number of passes. API-equivalent dollars use documented token rates. Plan dollars allocate the subscription by estimated weekly usage. Plan calibration date(s) 2026-11-27.

| Model | Rank (Ricardo: taste + cost) | Runs | Overall weighted score (Wilson 95%) | Role | Role weighted score (Wilson 95%) | Within-role rank | API-$ per pass (estimate) | Plan-$ per pass (estimate) |
|---|---:|---:|---|---|---|---|---|---|
| gpt-6.2-sol | 4 | 53 | 92.1% [85.1%, 95.9%] (n=101) | batch | 93.6% [83.9%, 97.6%] (n=55) | 1 | $1.408 / $3.425 (37/88) | unknown |
| gemini-4-neon-high | 1 | 261 | 90.4% [85.8%, 93.5%] (n=228) | batch | 88.3% [82.7%, 92.2%] (n=175) | 2 | $2.169 / $2.278 (17/191) | unknown |
| gpt-6.2-astra | 2 | 52 | 96.8% [91.0%, 98.9%] (n=94) | batch | 95.8% [79.8%, 99.3%] (n=24) | 3 | $2.304 / $3.107 (43/89) | unknown |
| gemini-4-carbon-high | 6-7 | 42 | 75.0% [57.9%, 86.7%] (n=32) | batch | 83.3% [62.6%, 93.7%] (n=21) | 4 | $1.938 / $2.544 (8/21) | unknown |
| claude-sonnet-5-5 | 5 | 13 | 84.4% [60.4%, 95.0%] (n=16) | batch | 87.5% [39.6%, 98.7%] (n=4) | n<20, unranked | unknown | unknown |
| gemini-4-argon-medium | 6-7 | 0 | 100.0% [67.6%, 100.0%] (n=8) | batch | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | unknown | unknown |
| gemini-4-hydrogen-high | — | 4 | 100.0% [34.2%, 100.0%] (n=2) | batch | 100.0% [34.2%, 100.0%] (n=2) | n<20, unranked | unknown | unknown |
| gemini-4-hydrogen-medium | — | 0 | 80.0% [37.6%, 96.4%] (n=5) | batch | 75.0% [30.1%, 95.4%] (n=4) | n<20, unranked | unknown | unknown |
| gpt-6.1-sol | - | 20 | 91.7% [51.7%, 99.1%] (n=6) | batch | 91.7% [51.7%, 99.1%] (n=6) | n<20, unranked | $1.408 / $2.106 (3/5) | unknown |
| gemini-4-neon-high | 1 | 261 | 90.4% [85.8%, 93.5%] (n=228) | builder | 96.3% [85.6%, 99.2%] (n=41) | 1 | $2.169 / $2.278 (17/191) | unknown |
| gpt-6.2-sol | 4 | 53 | 92.1% [85.1%, 95.9%] (n=101) | builder | 90.2% [78.3%, 95.9%] (n=46) | 2 | $1.408 / $3.425 (37/88) | unknown |
| claude-opus-5-5 | 1 | 26 | 93.0% [81.4%, 97.6%] (n=43) | builder | 93.1% [78.0%, 98.1%] (n=29) | 3 | $1.755 / $1.778 (9/37) | unknown |
| claude-sonnet-5-5 | 5 | 13 | 84.4% [60.4%, 95.0%] (n=16) | builder | 75.0% [30.1%, 95.4%] (n=4) | n<20, unranked | unknown | unknown |
| gemini-4-argon-medium | 6-7 | 0 | 100.0% [67.6%, 100.0%] (n=8) | builder | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | unknown | unknown |
| gemini-4-hydrogen-low | — | 0 | 50.0% [9.5%, 90.5%] (n=2) | builder | 50.0% [9.5%, 90.5%] (n=2) | n<20, unranked | unknown | unknown |
| gemini-4-neon-medium | 1 | 1 | 100.0% [77.2%, 100.0%] (n=13) | builder | 100.0% [75.7%, 100.0%] (n=12) | n<20, unranked | unknown | unknown |
| gpt-6.2-astra | 2 | 52 | 96.8% [91.0%, 98.9%] (n=94) | builder | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | $2.304 / $3.107 (43/89) | unknown |
| gemini-4-neon-high | 1 | 261 | 90.4% [85.8%, 93.5%] (n=228) | driver | 100.0% [34.2%, 100.0%] (n=2) | n<20, unranked | $2.169 / $2.278 (17/191) | unknown |
| gpt-6.2-astra | 2 | 52 | 96.8% [91.0%, 98.9%] (n=94) | judge | 100.0% [75.7%, 100.0%] (n=12) | n<20, unranked | $2.304 / $3.107 (43/89) | unknown |
| gpt-6.2-astra | 2 | 52 | 96.8% [91.0%, 98.9%] (n=94) | proof | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | $2.304 / $3.107 (43/89) | unknown |
| gpt-6.2-astra | 2 | 52 | 96.8% [91.0%, 98.9%] (n=94) | review | 96.4% [87.9%, 99.0%] (n=56) | 1 | $2.304 / $3.107 (43/89) | unknown |
| claude-opus-5-5 | 1 | 26 | 93.0% [81.4%, 97.6%] (n=43) | review | 92.9% [68.5%, 98.7%] (n=14) | n<20, unranked | $1.755 / $1.778 (9/37) | unknown |
| claude-sonnet-5-5 | 5 | 13 | 84.4% [60.4%, 95.0%] (n=16) | review | 87.5% [52.9%, 97.8%] (n=8) | n<20, unranked | unknown | unknown |
| gemini-3.8-flash-high | - | 0 | 100.0% [20.7%, 100.0%] (n=1) | review | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | unknown | unknown |
| gemini-3.8-flash-low | - | 0 | 100.0% [20.7%, 100.0%] (n=1) | review | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | unknown | unknown |
| gemini-3.8-flash-medium | - | 0 | 100.0% [20.7%, 100.0%] (n=1) | review | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | unknown | unknown |
| gemini-4-argon-low | 6-7 | 0 | 100.0% [20.7%, 100.0%] (n=1) | review | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | unknown | unknown |
| gemini-4-argon-medium | 6-7 | 0 | 100.0% [67.6%, 100.0%] (n=8) | review | 100.0% [61.0%, 100.0%] (n=6) | n<20, unranked | unknown | unknown |
| gemini-4-carbon-high | 6-7 | 42 | 75.0% [57.9%, 86.7%] (n=32) | review | 59.1% [31.6%, 81.9%] (n=11) | n<20, unranked | $1.938 / $2.544 (8/21) | unknown |
| gemini-4-hydrogen-medium | — | 0 | 80.0% [37.6%, 96.4%] (n=5) | review | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | unknown | unknown |
| gemini-4-neon-high | 1 | 261 | 90.4% [85.8%, 93.5%] (n=228) | review | 100.0% [72.2%, 100.0%] (n=10) | n<20, unranked | $2.169 / $2.278 (17/191) | unknown |
| gemini-4-neon-medium | 1 | 1 | 100.0% [77.2%, 100.0%] (n=13) | review | 100.0% [20.7%, 100.0%] (n=1) | n<20, unranked | unknown | unknown |
| google/gemini-4-hydrogen | — | 0 | 100.0% [34.2%, 100.0%] (n=2) | review | 100.0% [34.2%, 100.0%] (n=2) | n<20, unranked | unknown | unknown |
| moonshotai/kimi-k3.1-pro | — | 1 | 0.0% [0.0%, 79.3%] (n=1) | review | 0.0% [0.0%, 79.3%] (n=1) | n<20, unranked | unknown | unknown |

Dropped 200 grade rows: harness failure=1, probe=68, quota=21, remote controller grade=1, void=76, workdir incomplete=33. Ungraded runs remain in Runs; probes and bench runs are omitted.

Driver-session work (most Gemini Neon use) is ungraded until driver outputs are scored; 175/211 driver outputs have a grade.

Everyday work ranks models, never synthetic. Bench (saturated): claude-opus-5-5 / review 1.0 (n=5); gemini-3.8-flash-high / review 1.0 (n=1); gemini-3.8-flash-low / review 1.0 (n=1); gemini-3.8-flash-medium / review 1.0 (n=1); gemini-4-argon-medium / review 1.0 (n=1); gemini-4-hydrogen-medium / review 1.0 (n=1); gemini-4-neon-medium / review 1.0 (n=1); google/gemini-4-argon / review 1.0 (n=1); google/gemini-4-hydrogen / review 0.5 (n=2); gpt-5.6-sol / review 0.667 (n=3); moonshotai/kimi-k3.1-pro / review 1.0 (n=2).

Carbon (10-28) replaced Argon; model versions and effort tiers keep their own records.

<details>
<summary>Routing snapshots (positions are routing preferences)</summary>

| Role | Model | Routing order | Cost per pass | Date |
|---|---|---:|---:|---|
| taste | claude-opus-5-5 | 1 | - | 2026-11-03 |
| taste | claude-fable-5-1 | 2 | - | 2026-11-03 |
| taste | deepseek/deepseek-v4.1-flash-1017 | - | - | 2026-11-03 |
| taste | gpt-6.1-sol | - | - | 2026-11-03 |
| review | claude-opus-5-5 | 1 | - | 2026-11-03 |
| review | gpt-6-astra | 2 | - | 2026-11-03 |
| review | claude-fable-5-1 | 3 | - | 2026-11-03 |
| review | gpt-6.1-sol | 4 | - | 2026-11-03 |
| mechanical | gpt-6.1-sol | 1 | - | 2026-11-03 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-03 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-03 |
| builder | gpt-6.1-sol | 2 | - | 2026-11-03 |
| builder | deepseek/deepseek-v4.1-flash-1017 | - | - | 2026-11-03 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | 2026-11-03 |
| cheap | z-ai/glm-5.3-flash | 2 | - | 2026-11-03 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | 2026-11-03 |
| batch | gpt-6.1-sol | 1 | - | 2026-11-03 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-03 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-03 |
| ideation | claude-opus-5-5 | 1 | - | 2026-11-03 |
| ideation | gpt-6-astra | 2 | - | 2026-11-03 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | 2026-11-03 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-14 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-14 |
| review | claude-opus-5-5 | 1 | - | 2026-11-14 |
| review | gpt-6-astra | 2 | - | 2026-11-14 |
| review | claude-fable-5-2 | 3 | - | 2026-11-14 |
| review | gpt-6.1-sol | 4 | - | 2026-11-14 |
| review | gpt-5.6-sol | 5 | - | 2026-11-14 |
| review | moonshotai/kimi-k3.1-pro | 6 | - | 2026-11-14 |
| review | google/gemini-4-argon | 7 | - | 2026-11-14 |
| review | claude-sonnet-5-5 | 8 | - | 2026-11-14 |
| mechanical | gpt-6.1-sol | 1 | - | 2026-11-14 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-14 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-14 |
| builder | gpt-6.1-sol | 2 | - | 2026-11-14 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | 2026-11-14 |
| cheap | z-ai/glm-5.3-flash | 2 | - | 2026-11-14 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | 2026-11-14 |
| batch | gpt-6.1-sol | 1 | - | 2026-11-14 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-14 |
| batch | gpt-6-astra | 3 | - | 2026-11-14 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-14 |
| ideation | claude-opus-5-5 | 1 | - | 2026-11-14 |
| ideation | gpt-6-astra | 2 | - | 2026-11-14 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | 2026-11-14 |
| ideation | claude-fable-5-2 | 4 | - | 2026-11-14 |
| ideation | gpt-6.1-sol | 5 | - | 2026-11-14 |
| design | claude-opus-5-5 | 1 | - | 2026-11-14 |
| design | claude-fable-5-2 | 2 | - | 2026-11-14 |
| design | gpt-6.1-sol | 3 | - | 2026-11-14 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-14 |
| judge | gpt-6-astra | 2 | - | 2026-11-14 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-14 |
| judge | gpt-6.1-sol | 4 | - | 2026-11-14 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-15 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-15 |
| review | claude-opus-5-5 | 1 | - | 2026-11-15 |
| review | gpt-6-astra | 2 | - | 2026-11-15 |
| review | claude-fable-5-2 | 3 | - | 2026-11-15 |
| review | gpt-6.1-sol | 4 | - | 2026-11-15 |
| review | gpt-5.6-sol | 5 | - | 2026-11-15 |
| review | moonshotai/kimi-k3.1-pro | 6 | - | 2026-11-15 |
| review | google/gemini-4-argon | 7 | - | 2026-11-15 |
| review | claude-sonnet-5-5 | 8 | - | 2026-11-15 |
| mechanical | gpt-6.1-sol | 1 | - | 2026-11-15 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-15 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-15 |
| builder | gpt-6.1-sol | 2 | - | 2026-11-15 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | 2026-11-15 |
| cheap | z-ai/glm-5.3-flash | 2 | - | 2026-11-15 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | 2026-11-15 |
| batch | gpt-6.1-sol | 1 | - | 2026-11-15 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-15 |
| batch | gpt-6-astra | 3 | - | 2026-11-15 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-15 |
| ideation | claude-opus-5-5 | 1 | - | 2026-11-15 |
| ideation | gpt-6-astra | 2 | - | 2026-11-15 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | 2026-11-15 |
| ideation | claude-fable-5-2 | 4 | - | 2026-11-15 |
| ideation | gpt-6.1-sol | 5 | - | 2026-11-15 |
| design | claude-opus-5-5 | 1 | - | 2026-11-15 |
| design | claude-fable-5-2 | 2 | - | 2026-11-15 |
| design | gpt-6.1-sol | 3 | - | 2026-11-15 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-15 |
| judge | gpt-6-astra | 2 | - | 2026-11-15 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-15 |
| judge | gpt-6.1-sol | 4 | - | 2026-11-15 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-16 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-16 |
| taste | gpt-6-astra | 3 | - | 2026-11-16 |
| review | claude-opus-5-5 | 1 | - | 2026-11-16 |
| review | gpt-6-astra | 2 | - | 2026-11-16 |
| review | claude-fable-5-2 | 3 | - | 2026-11-16 |
| review | gpt-6.1-sol | 4 | - | 2026-11-16 |
| review | google/gemini-4-carbon | 5 | - | 2026-11-16 |
| review | google/gemini-4-hydrogen | 6 | - | 2026-11-16 |
| review | gpt-5.6-sol | 7 | - | 2026-11-16 |
| review | moonshotai/kimi-k3.1-pro | 8 | - | 2026-11-16 |
| review | google/gemini-4-argon | 9 | - | 2026-11-16 |
| review | claude-sonnet-5-5 | 10 | - | 2026-11-16 |
| mechanical | gpt-6.1-sol | 1 | - | 2026-11-16 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-16 |
| mechanical | google/gemini-4-carbon | 3 | - | 2026-11-16 |
| mechanical | google/gemini-4-hydrogen | 4 | - | 2026-11-16 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-16 |
| builder | gpt-6.1-sol | 2 | - | 2026-11-16 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | 2026-11-16 |
| cheap | z-ai/glm-5.3-flash | 2 | - | 2026-11-16 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | 2026-11-16 |
| batch | gpt-6.1-sol | 1 | - | 2026-11-16 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-16 |
| batch | google/gemini-4-carbon | 3 | - | 2026-11-16 |
| batch | google/gemini-4-hydrogen | 4 | - | 2026-11-16 |
| batch | gpt-6-astra | 5 | - | 2026-11-16 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-16 |
| ideation | claude-opus-5-5 | 1 | - | 2026-11-16 |
| ideation | gpt-6-astra | 2 | - | 2026-11-16 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | 2026-11-16 |
| ideation | google/gemini-4-carbon | 4 | - | 2026-11-16 |
| ideation | google/gemini-4-hydrogen | 5 | - | 2026-11-16 |
| ideation | claude-fable-5-2 | 6 | - | 2026-11-16 |
| ideation | gpt-6.1-sol | 7 | - | 2026-11-16 |
| design | claude-opus-5-5 | 1 | - | 2026-11-16 |
| design | claude-fable-5-2 | 2 | - | 2026-11-16 |
| design | google/gemini-4-carbon | 3 | - | 2026-11-16 |
| design | google/gemini-4-hydrogen | 4 | - | 2026-11-16 |
| design | gpt-6.1-sol | 5 | - | 2026-11-16 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-16 |
| judge | gpt-6-astra | 2 | - | 2026-11-16 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-16 |
| judge | gpt-6.1-sol | 4 | - | 2026-11-16 |
| judge | google/gemini-4-carbon | 5 | - | 2026-11-16 |
| judge | google/gemini-4-hydrogen | 6 | - | 2026-11-16 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-17 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-17 |
| taste | gpt-6-astra | 3 | - | 2026-11-17 |
| review | claude-opus-5-5 | 1 | - | 2026-11-17 |
| review | gpt-6-astra | 2 | - | 2026-11-17 |
| review | claude-fable-5-2 | 3 | - | 2026-11-17 |
| review | gpt-6.1-sol | 4 | - | 2026-11-17 |
| review | google/gemini-4-carbon | 5 | - | 2026-11-17 |
| review | google/gemini-4-hydrogen | 6 | - | 2026-11-17 |
| review | gpt-5.6-sol | 7 | - | 2026-11-17 |
| review | moonshotai/kimi-k3.1-pro | 8 | - | 2026-11-17 |
| review | google/gemini-4-argon | 9 | - | 2026-11-17 |
| review | gpt-6.2-astra | 10 | - | 2026-11-17 |
| review | claude-sonnet-5-5 | 11 | - | 2026-11-17 |
| mechanical | gpt-6.1-sol | 1 | - | 2026-11-17 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-17 |
| mechanical | google/gemini-4-carbon | 3 | - | 2026-11-17 |
| mechanical | google/gemini-4-hydrogen | 4 | - | 2026-11-17 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-17 |
| builder | gpt-6.1-sol | 2 | - | 2026-11-17 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | 2026-11-17 |
| cheap | z-ai/glm-5.3-flash | 2 | - | 2026-11-17 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | 2026-11-17 |
| batch | gpt-6.1-sol | 1 | - | 2026-11-17 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-17 |
| batch | google/gemini-4-carbon | 3 | - | 2026-11-17 |
| batch | google/gemini-4-hydrogen | 4 | - | 2026-11-17 |
| batch | gpt-6-astra | 5 | - | 2026-11-17 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-17 |
| ideation | claude-opus-5-5 | 1 | - | 2026-11-17 |
| ideation | gpt-6-astra | 2 | - | 2026-11-17 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | 2026-11-17 |
| ideation | google/gemini-4-carbon | 4 | - | 2026-11-17 |
| ideation | google/gemini-4-hydrogen | 5 | - | 2026-11-17 |
| ideation | claude-fable-5-2 | 6 | - | 2026-11-17 |
| ideation | gpt-6.1-sol | 7 | - | 2026-11-17 |
| design | claude-opus-5-5 | 1 | - | 2026-11-17 |
| design | claude-fable-5-2 | 2 | - | 2026-11-17 |
| design | google/gemini-4-carbon | 3 | - | 2026-11-17 |
| design | google/gemini-4-hydrogen | 4 | - | 2026-11-17 |
| design | gpt-6.1-sol | 5 | - | 2026-11-17 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-17 |
| judge | gpt-6-astra | 2 | - | 2026-11-17 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-17 |
| judge | gpt-6.1-sol | 4 | - | 2026-11-17 |
| judge | google/gemini-4-carbon | 5 | - | 2026-11-17 |
| judge | google/gemini-4-hydrogen | 6 | - | 2026-11-17 |
| judge | gpt-6.2-astra | 7 | - | 2026-11-17 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-18 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-18 |
| review | claude-opus-5-5 | 1 | - | 2026-11-18 |
| review | gpt-6.2-astra | 2 | - | 2026-11-18 |
| review | claude-fable-5-2 | 3 | - | 2026-11-18 |
| review | gpt-6.2-sol | 4 | - | 2026-11-18 |
| review | gpt-5.6-sol | 5 | - | 2026-11-18 |
| review | moonshotai/kimi-k3.1-pro | 6 | - | 2026-11-18 |
| review | claude-sonnet-5-5 | 7 | - | 2026-11-18 |
| review | gpt-6-astra | 8 | - | 2026-11-18 |
| review | gpt-6.1-sol | 9 | - | 2026-11-18 |
| review | google/gemini-4-argon | - | - | 2026-11-18 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-18 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-18 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-18 |
| mechanical | gpt-6.1-sol | 3 | - | 2026-11-18 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-18 |
| builder | gpt-6.2-sol | 2 | - | 2026-11-18 |
| builder | gpt-6.1-sol | 3 | - | 2026-11-18 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | 2026-11-18 |
| cheap | z-ai/glm-5.3-flash | 2 | - | 2026-11-18 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | 2026-11-18 |
| batch | gpt-6.2-sol | 1 | - | 2026-11-18 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-18 |
| batch | gpt-6.1-sol | 3 | - | 2026-11-18 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-18 |
| ideation | claude-opus-5-5 | 1 | - | 2026-11-18 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-18 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | 2026-11-18 |
| ideation | claude-fable-5-2 | 4 | - | 2026-11-18 |
| ideation | gpt-6-astra | 5 | - | 2026-11-18 |
| design | claude-opus-5-5 | 1 | - | 2026-11-18 |
| design | claude-fable-5-2 | 2 | - | 2026-11-18 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-18 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-18 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-18 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-18 |
| judge | gpt-6-astra | 5 | - | 2026-11-18 |
| judge | gpt-6.1-sol | 6 | - | 2026-11-18 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-19 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-19 |
| review | claude-opus-5-5 | 1 | - | 2026-11-19 |
| review | gpt-6.2-astra | 2 | - | 2026-11-19 |
| review | claude-fable-5-2 | 3 | - | 2026-11-19 |
| review | gpt-6.2-sol | 4 | - | 2026-11-19 |
| review | gpt-5.6-sol | 5 | - | 2026-11-19 |
| review | moonshotai/kimi-k3.1-pro | 6 | - | 2026-11-19 |
| review | claude-sonnet-5-5 | 7 | - | 2026-11-19 |
| review | gpt-6-astra | 8 | - | 2026-11-19 |
| review | gpt-6.1-sol | 9 | - | 2026-11-19 |
| review | google/gemini-4-argon | - | - | 2026-11-19 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-19 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-19 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-19 |
| mechanical | gpt-6.1-sol | 3 | - | 2026-11-19 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-19 |
| builder | gpt-6.2-sol | 2 | - | 2026-11-19 |
| builder | gpt-6.1-sol | 3 | - | 2026-11-19 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | 2026-11-19 |
| cheap | z-ai/glm-5.3-flash | 2 | - | 2026-11-19 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | 2026-11-19 |
| batch | gpt-6.2-sol | 1 | - | 2026-11-19 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | 2026-11-19 |
| batch | gpt-6.1-sol | 3 | - | 2026-11-19 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-19 |
| ideation | claude-opus-5-5 | 1 | - | 2026-11-19 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-19 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | 2026-11-19 |
| ideation | claude-fable-5-2 | 4 | - | 2026-11-19 |
| ideation | gpt-6-astra | 5 | - | 2026-11-19 |
| design | claude-opus-5-5 | 1 | - | 2026-11-19 |
| design | claude-fable-5-2 | 2 | - | 2026-11-19 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-19 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-19 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-19 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-19 |
| judge | gpt-6-astra | 5 | - | 2026-11-19 |
| judge | gpt-6.1-sol | 6 | - | 2026-11-19 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-19 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-19 |
| taste | gemini-3.8-flash-low | 5 | - | 2026-11-19 |
| taste | gemini-4-neon-low | 6 | - | 2026-11-19 |
| taste | gemini-4-neon-medium | 7 | - | 2026-11-19 |
| taste | gemini-4-argon-low | 8 | - | 2026-11-19 |
| taste | gemini-4-argon-medium | 9 | - | 2026-11-19 |
| taste | gemini-4-hydrogen-low | 10 | - | 2026-11-19 |
| taste | gemini-4-hydrogen-medium | 11 | - | 2026-11-19 |
| review | gemini-3.8-flash-high | 5 | - | 2026-11-19 |
| review | gemini-3.8-flash-medium | 6 | - | 2026-11-19 |
| review | gemini-3.8-flash-low | 7 | - | 2026-11-19 |
| review | gemini-4-neon-low | 8 | - | 2026-11-19 |
| review | gemini-4-neon-medium | 9 | - | 2026-11-19 |
| review | gemini-4-argon-low | 10 | - | 2026-11-19 |
| review | gemini-4-argon-medium | 11 | - | 2026-11-19 |
| review | gemini-4-hydrogen-low | 12 | - | 2026-11-19 |
| review | gemini-4-hydrogen-medium | 13 | - | 2026-11-19 |
| review | gpt-5.6-sol | 14 | - | 2026-11-19 |
| review | claude-sonnet-5-5 | 15 | - | 2026-11-19 |
| review | moonshotai/kimi-k3.1-pro | - | - | 2026-11-19 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-19 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-19 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-19 |
| mechanical | gemini-3.8-flash-low | 5 | - | 2026-11-19 |
| mechanical | gemini-4-neon-low | 6 | - | 2026-11-19 |
| mechanical | gemini-4-neon-medium | 7 | - | 2026-11-19 |
| mechanical | gemini-4-argon-low | 8 | - | 2026-11-19 |
| mechanical | gemini-4-argon-medium | 9 | - | 2026-11-19 |
| mechanical | gemini-4-hydrogen-low | 10 | - | 2026-11-19 |
| mechanical | gemini-4-hydrogen-medium | 11 | - | 2026-11-19 |
| builder | gemini-3.8-flash-high | 3 | - | 2026-11-19 |
| builder | gemini-3.8-flash-medium | 4 | - | 2026-11-19 |
| builder | gemini-3.8-flash-low | 5 | - | 2026-11-19 |
| builder | gemini-4-neon-low | 6 | - | 2026-11-19 |
| builder | gemini-4-neon-medium | 7 | - | 2026-11-19 |
| builder | gemini-4-argon-low | 8 | - | 2026-11-19 |
| builder | gemini-4-argon-medium | 9 | - | 2026-11-19 |
| builder | gemini-4-hydrogen-low | 10 | - | 2026-11-19 |
| builder | gemini-4-hydrogen-medium | 11 | - | 2026-11-19 |
| cheap | gpt-6-luna | 1 | - | 2026-11-19 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-19 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-19 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-19 |
| cheap | gemini-3.8-flash-low | 5 | - | 2026-11-19 |
| cheap | gemini-4-neon-low | 6 | - | 2026-11-19 |
| cheap | gemini-4-neon-medium | 7 | - | 2026-11-19 |
| cheap | gemini-4-argon-low | 8 | - | 2026-11-19 |
| cheap | gemini-4-argon-medium | 9 | - | 2026-11-19 |
| cheap | gemini-4-hydrogen-low | 10 | - | 2026-11-19 |
| cheap | gemini-4-hydrogen-medium | 11 | - | 2026-11-19 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-19 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-19 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-19 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-19 |
| biology | gemini-3.8-flash-low | 5 | - | 2026-11-19 |
| biology | gemini-4-neon-low | 6 | - | 2026-11-19 |
| biology | gemini-4-neon-medium | 7 | - | 2026-11-19 |
| biology | gemini-4-argon-low | 8 | - | 2026-11-19 |
| biology | gemini-4-argon-medium | 9 | - | 2026-11-19 |
| biology | gemini-4-hydrogen-low | 10 | - | 2026-11-19 |
| biology | gemini-4-hydrogen-medium | 11 | - | 2026-11-19 |
| batch | claude-sonnet-5-5 | 2 | - | 2026-11-19 |
| batch | gemini-3.8-flash-high | 3 | - | 2026-11-19 |
| batch | gemini-3.8-flash-medium | 4 | - | 2026-11-19 |
| batch | gemini-3.8-flash-low | 5 | - | 2026-11-19 |
| batch | gemini-4-neon-low | 6 | - | 2026-11-19 |
| batch | gemini-4-neon-medium | 7 | - | 2026-11-19 |
| batch | gemini-4-argon-low | 8 | - | 2026-11-19 |
| batch | gemini-4-argon-medium | 9 | - | 2026-11-19 |
| batch | gemini-4-hydrogen-low | 10 | - | 2026-11-19 |
| batch | gemini-4-hydrogen-medium | 11 | - | 2026-11-19 |
| batch | gpt-6.1-sol | - | - | 2026-11-19 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-19 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-19 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-19 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-19 |
| ideation | gemini-3.8-flash-low | 6 | - | 2026-11-19 |
| ideation | gemini-4-neon-low | 7 | - | 2026-11-19 |
| ideation | gemini-4-neon-medium | 8 | - | 2026-11-19 |
| ideation | gemini-4-argon-low | 9 | - | 2026-11-19 |
| ideation | gemini-4-argon-medium | 10 | - | 2026-11-19 |
| ideation | gemini-4-hydrogen-low | 11 | - | 2026-11-19 |
| ideation | gemini-4-hydrogen-medium | 12 | - | 2026-11-19 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-19 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-19 |
| design | gemini-3.8-flash-low | 5 | - | 2026-11-19 |
| design | gemini-4-neon-low | 6 | - | 2026-11-19 |
| design | gemini-4-neon-medium | 7 | - | 2026-11-19 |
| design | gemini-4-argon-low | 8 | - | 2026-11-19 |
| design | gemini-4-argon-medium | 9 | - | 2026-11-19 |
| design | gemini-4-hydrogen-low | 10 | - | 2026-11-19 |
| design | gemini-4-hydrogen-medium | 11 | - | 2026-11-19 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-19 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-19 |
| judge | gemini-3.8-flash-low | 7 | - | 2026-11-19 |
| judge | gemini-4-neon-low | 8 | - | 2026-11-19 |
| judge | gemini-4-neon-medium | 9 | - | 2026-11-19 |
| judge | gemini-4-argon-low | 10 | - | 2026-11-19 |
| judge | gemini-4-argon-medium | 11 | - | 2026-11-19 |
| judge | gemini-4-hydrogen-low | 12 | - | 2026-11-19 |
| judge | gemini-4-hydrogen-medium | 13 | - | 2026-11-19 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-20 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-20 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-20 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-20 |
| taste | gemini-3.8-flash-low | 5 | - | 2026-11-20 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-20 |
| review | claude-sonnet-5-5 | 1 | - | 2026-11-20 |
| review | claude-opus-5-5 | 2 | - | 2026-11-20 |
| review | gpt-6.2-astra | 3 | - | 2026-11-20 |
| review | claude-fable-5-2 | 4 | - | 2026-11-20 |
| review | gpt-6.2-sol | 5 | - | 2026-11-20 |
| review | gemini-3.8-flash-high | 6 | - | 2026-11-20 |
| review | gemini-3.8-flash-medium | 7 | - | 2026-11-20 |
| review | gemini-3.8-flash-low | 8 | - | 2026-11-20 |
| review | gemini-4-neon-medium | 9 | - | 2026-11-20 |
| review | gemini-4-hydrogen-medium | 10 | - | 2026-11-20 |
| review | gpt-5.6-sol | 11 | - | 2026-11-20 |
| review | gemini-4-argon-low | - | - | 2026-11-20 |
| review | gemini-4-argon-medium | - | - | 2026-11-20 |
| review | google/gemini-4-argon | - | - | 2026-11-20 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-20 |
| review | moonshotai/kimi-k3.1-pro | - | - | 2026-11-20 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-20 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-20 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-20 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-20 |
| mechanical | gemini-3.8-flash-low | 5 | - | 2026-11-20 |
| mechanical | gemini-4-hydrogen-low | 6 | - | 2026-11-20 |
| mechanical | gemini-4-hydrogen-medium | 7 | - | 2026-11-20 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-20 |
| builder | gpt-6.2-sol | 2 | - | 2026-11-20 |
| builder | gemini-3.8-flash-high | 3 | - | 2026-11-20 |
| builder | gemini-3.8-flash-medium | 4 | - | 2026-11-20 |
| builder | gemini-3.8-flash-low | 5 | - | 2026-11-20 |
| builder | gemini-4-neon-medium | 6 | - | 2026-11-20 |
| builder | claude-sonnet-5-5 | 7 | - | 2026-11-20 |
| builder | gemini-4-hydrogen-low | 8 | - | 2026-11-20 |
| builder | gpt-6.2-astra | 9 | - | 2026-11-20 |
| builder | gemini-4-argon-medium | - | - | 2026-11-20 |
| cheap | gpt-6-luna | 1 | - | 2026-11-20 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-20 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-20 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-20 |
| cheap | gemini-3.8-flash-low | 5 | - | 2026-11-20 |
| cheap | gemini-4-hydrogen-low | 6 | - | 2026-11-20 |
| cheap | gemini-4-hydrogen-medium | 7 | - | 2026-11-20 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-20 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-20 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-20 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-20 |
| biology | gemini-3.8-flash-low | 5 | - | 2026-11-20 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-20 |
| batch | gpt-6.2-sol | 1 | - | 2026-11-20 |
| batch | gpt-6.2-astra | 2 | - | 2026-11-20 |
| batch | claude-sonnet-5-5 | 3 | - | 2026-11-20 |
| batch | gemini-3.8-flash-high | 4 | - | 2026-11-20 |
| batch | gemini-3.8-flash-medium | 5 | - | 2026-11-20 |
| batch | gemini-3.8-flash-low | 6 | - | 2026-11-20 |
| batch | gemini-4-hydrogen-low | 7 | - | 2026-11-20 |
| batch | gemini-4-hydrogen-medium | 8 | - | 2026-11-20 |
| batch | gemini-4-argon-medium | - | - | 2026-11-20 |
| batch | gpt-6.1-sol | - | - | 2026-11-20 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-20 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-20 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-20 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-20 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-20 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-20 |
| ideation | gemini-3.8-flash-low | 6 | - | 2026-11-20 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-20 |
| design | claude-opus-5-5 | 1 | - | 2026-11-20 |
| design | claude-fable-5-2 | 2 | - | 2026-11-20 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-20 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-20 |
| design | gemini-3.8-flash-low | 5 | - | 2026-11-20 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-20 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-20 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-20 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-20 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-20 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-20 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-20 |
| judge | gemini-3.8-flash-low | 7 | - | 2026-11-20 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-20 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-21 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-21 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-21 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-21 |
| taste | gemini-3.8-flash-low | 5 | - | 2026-11-21 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-21 |
| review | gpt-6.2-astra | 1 | - | 2026-11-21 |
| review | claude-sonnet-5-5 | 2 | - | 2026-11-21 |
| review | claude-opus-5-5 | 3 | - | 2026-11-21 |
| review | claude-fable-5-2 | 4 | - | 2026-11-21 |
| review | gpt-6.2-sol | 5 | - | 2026-11-21 |
| review | gemini-3.8-flash-high | 6 | - | 2026-11-21 |
| review | gemini-3.8-flash-medium | 7 | - | 2026-11-21 |
| review | gemini-3.8-flash-low | 8 | - | 2026-11-21 |
| review | gemini-4-neon-medium | 9 | - | 2026-11-21 |
| review | gemini-4-hydrogen-medium | 10 | - | 2026-11-21 |
| review | gpt-5.6-sol | 11 | - | 2026-11-21 |
| review | gemini-4-argon-low | - | - | 2026-11-21 |
| review | gemini-4-argon-medium | - | - | 2026-11-21 |
| review | google/gemini-4-argon | - | - | 2026-11-21 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-21 |
| review | moonshotai/kimi-k3.1-pro | - | - | 2026-11-21 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-21 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-21 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-21 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-21 |
| mechanical | gemini-3.8-flash-low | 5 | - | 2026-11-21 |
| mechanical | gemini-4-hydrogen-low | 6 | - | 2026-11-21 |
| mechanical | gemini-4-hydrogen-medium | 7 | - | 2026-11-21 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-21 |
| builder | gemini-4-neon-medium | 2 | - | 2026-11-21 |
| builder | gpt-6.2-sol | 3 | - | 2026-11-21 |
| builder | gemini-3.8-flash-high | 4 | - | 2026-11-21 |
| builder | gemini-3.8-flash-medium | 5 | - | 2026-11-21 |
| builder | gemini-3.8-flash-low | 6 | - | 2026-11-21 |
| builder | claude-sonnet-5-5 | 7 | - | 2026-11-21 |
| builder | gemini-4-hydrogen-low | 8 | - | 2026-11-21 |
| builder | gpt-6.2-astra | 9 | - | 2026-11-21 |
| builder | gemini-4-argon-medium | - | - | 2026-11-21 |
| cheap | gpt-6-luna | 1 | - | 2026-11-21 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-21 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-21 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-21 |
| cheap | gemini-3.8-flash-low | 5 | - | 2026-11-21 |
| cheap | gemini-4-hydrogen-low | 6 | - | 2026-11-21 |
| cheap | gemini-4-hydrogen-medium | 7 | - | 2026-11-21 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-21 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-21 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-21 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-21 |
| biology | gemini-3.8-flash-low | 5 | - | 2026-11-21 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-21 |
| batch | gpt-6.2-sol | 1 | - | 2026-11-21 |
| batch | gpt-6.2-astra | 2 | - | 2026-11-21 |
| batch | claude-sonnet-5-5 | 3 | - | 2026-11-21 |
| batch | gemini-3.8-flash-high | 4 | - | 2026-11-21 |
| batch | gemini-3.8-flash-medium | 5 | - | 2026-11-21 |
| batch | gemini-3.8-flash-low | 6 | - | 2026-11-21 |
| batch | gemini-4-hydrogen-low | 7 | - | 2026-11-21 |
| batch | gemini-4-hydrogen-medium | 8 | - | 2026-11-21 |
| batch | gemini-4-argon-medium | - | - | 2026-11-21 |
| batch | gpt-6.1-sol | - | - | 2026-11-21 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-21 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-21 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-21 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-21 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-21 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-21 |
| ideation | gemini-3.8-flash-low | 6 | - | 2026-11-21 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-21 |
| design | claude-opus-5-5 | 1 | - | 2026-11-21 |
| design | claude-fable-5-2 | 2 | - | 2026-11-21 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-21 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-21 |
| design | gemini-3.8-flash-low | 5 | - | 2026-11-21 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-21 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-21 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-21 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-21 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-21 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-21 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-21 |
| judge | gemini-3.8-flash-low | 7 | - | 2026-11-21 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-21 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-22 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-22 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-22 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-22 |
| taste | gemini-3.8-flash-low | 5 | - | 2026-11-22 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-22 |
| review | gpt-6.2-astra | 1 | - | 2026-11-22 |
| review | claude-sonnet-5-5 | 2 | - | 2026-11-22 |
| review | claude-opus-5-5 | 3 | - | 2026-11-22 |
| review | claude-fable-5-2 | 4 | - | 2026-11-22 |
| review | gpt-6.2-sol | 5 | - | 2026-11-22 |
| review | gemini-3.8-flash-high | 6 | - | 2026-11-22 |
| review | gemini-3.8-flash-medium | 7 | - | 2026-11-22 |
| review | gemini-3.8-flash-low | 8 | - | 2026-11-22 |
| review | gemini-4-neon-medium | 9 | - | 2026-11-22 |
| review | gemini-4-hydrogen-medium | 10 | - | 2026-11-22 |
| review | gpt-5.6-sol | 11 | - | 2026-11-22 |
| review | gemini-4-argon-low | - | - | 2026-11-22 |
| review | gemini-4-argon-medium | - | - | 2026-11-22 |
| review | google/gemini-4-argon | - | - | 2026-11-22 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-22 |
| review | moonshotai/kimi-k3.1-pro | - | - | 2026-11-22 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-22 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-22 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-22 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-22 |
| mechanical | gemini-3.8-flash-low | 5 | - | 2026-11-22 |
| mechanical | gemini-4-hydrogen-low | 6 | - | 2026-11-22 |
| mechanical | gemini-4-hydrogen-medium | 7 | - | 2026-11-22 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-22 |
| builder | gemini-4-neon-medium | 2 | - | 2026-11-22 |
| builder | gpt-6.2-sol | 3 | - | 2026-11-22 |
| builder | gemini-3.8-flash-high | 4 | - | 2026-11-22 |
| builder | gemini-3.8-flash-medium | 5 | - | 2026-11-22 |
| builder | gemini-3.8-flash-low | 6 | - | 2026-11-22 |
| builder | claude-sonnet-5-5 | 7 | - | 2026-11-22 |
| builder | gemini-4-hydrogen-low | 8 | - | 2026-11-22 |
| builder | gpt-6.2-astra | 9 | - | 2026-11-22 |
| builder | gemini-4-argon-medium | - | - | 2026-11-22 |
| cheap | gpt-6-luna | 1 | - | 2026-11-22 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-22 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-22 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-22 |
| cheap | gemini-3.8-flash-low | 5 | - | 2026-11-22 |
| cheap | gemini-4-hydrogen-low | 6 | - | 2026-11-22 |
| cheap | gemini-4-hydrogen-medium | 7 | - | 2026-11-22 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-22 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-22 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-22 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-22 |
| biology | gemini-3.8-flash-low | 5 | - | 2026-11-22 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-22 |
| batch | gpt-6.2-sol | 1 | - | 2026-11-22 |
| batch | gpt-6.2-astra | 2 | - | 2026-11-22 |
| batch | claude-sonnet-5-5 | 3 | - | 2026-11-22 |
| batch | gemini-3.8-flash-high | 4 | - | 2026-11-22 |
| batch | gemini-3.8-flash-medium | 5 | - | 2026-11-22 |
| batch | gemini-3.8-flash-low | 6 | - | 2026-11-22 |
| batch | gemini-4-hydrogen-low | 7 | - | 2026-11-22 |
| batch | gemini-4-hydrogen-medium | 8 | - | 2026-11-22 |
| batch | gemini-4-argon-medium | - | - | 2026-11-22 |
| batch | gpt-6.1-sol | - | - | 2026-11-22 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-22 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-22 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-22 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-22 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-22 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-22 |
| ideation | gemini-3.8-flash-low | 6 | - | 2026-11-22 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-22 |
| design | claude-opus-5-5 | 1 | - | 2026-11-22 |
| design | claude-fable-5-2 | 2 | - | 2026-11-22 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-22 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-22 |
| design | gemini-3.8-flash-low | 5 | - | 2026-11-22 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-22 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-22 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-22 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-22 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-22 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-22 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-22 |
| judge | gemini-3.8-flash-low | 7 | - | 2026-11-22 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-22 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-23 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-23 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-23 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-23 |
| taste | gemini-4-neon-high | 5 | - | 2026-11-23 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-23 |
| review | gpt-6.2-astra | 1 | - | 2026-11-23 |
| review | claude-sonnet-5-5 | 2 | - | 2026-11-23 |
| review | claude-opus-5-5 | 3 | - | 2026-11-23 |
| review | claude-fable-5-2 | 4 | - | 2026-11-23 |
| review | gpt-6.2-sol | 5 | - | 2026-11-23 |
| review | gemini-3.8-flash-high | 6 | - | 2026-11-23 |
| review | gemini-3.8-flash-medium | 7 | - | 2026-11-23 |
| review | gemini-4-neon-high | 8 | - | 2026-11-23 |
| review | gemini-4-neon-medium | 9 | - | 2026-11-23 |
| review | gemini-4-hydrogen-medium | 10 | - | 2026-11-23 |
| review | gpt-5.6-sol | 11 | - | 2026-11-23 |
| review | gemini-3.8-flash-low | - | - | 2026-11-23 |
| review | gemini-4-argon-low | - | - | 2026-11-23 |
| review | gemini-4-argon-medium | - | - | 2026-11-23 |
| review | google/gemini-4-argon | - | - | 2026-11-23 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-23 |
| review | google/gemini-4-neon | - | - | 2026-11-23 |
| review | gpt-6.1-sol | - | - | 2026-11-23 |
| review | moonshotai/kimi-k3.1-pro | - | - | 2026-11-23 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-23 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-23 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-23 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-23 |
| mechanical | gemini-4-hydrogen-high | 5 | - | 2026-11-23 |
| mechanical | gemini-4-hydrogen-medium | 6 | - | 2026-11-23 |
| mechanical | claude-opus-5-5 | 7 | - | 2026-11-23 |
| mechanical | claude-fable-5-1 | - | - | 2026-11-23 |
| mechanical | claude-fable-5-2 | - | - | 2026-11-23 |
| mechanical | google/gemini-4-argon | - | - | 2026-11-23 |
| mechanical | google/gemini-4-carbon | - | - | 2026-11-23 |
| mechanical | google/gemini-4-hydrogen | - | - | 2026-11-23 |
| mechanical | google/gemini-4-neon | - | - | 2026-11-23 |
| mechanical | gpt-6.1-sol | - | - | 2026-11-23 |
| mechanical | gpt-6.2-astra | - | - | 2026-11-23 |
| mechanical | moonshotai/kimi-k3.1-pro | - | - | 2026-11-23 |
| mechanical | x-ai/grok-4.6 | - | - | 2026-11-23 |
| mechanical | z-ai/glm-5.3-flash | - | - | 2026-11-23 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-23 |
| builder | gemini-4-neon-medium | 2 | - | 2026-11-23 |
| builder | gpt-6.2-sol | 3 | - | 2026-11-23 |
| builder | gemini-3.8-flash-high | 4 | - | 2026-11-23 |
| builder | gemini-3.8-flash-medium | 5 | - | 2026-11-23 |
| builder | gemini-4-neon-high | 6 | - | 2026-11-23 |
| builder | claude-sonnet-5-5 | 7 | - | 2026-11-23 |
| builder | gpt-6.2-astra | 8 | - | 2026-11-23 |
| builder | claude-fable-5-1 | 9 | - | 2026-11-23 |
| builder | claude-fable-5-2 | 10 | - | 2026-11-23 |
| builder | gemini-4-argon-medium | - | - | 2026-11-23 |
| builder | gemini-4-hydrogen-low | - | - | 2026-11-23 |
| builder | google/gemini-4-argon | - | - | 2026-11-23 |
| builder | google/gemini-4-carbon | - | - | 2026-11-23 |
| builder | google/gemini-4-hydrogen | - | - | 2026-11-23 |
| builder | google/gemini-4-neon | - | - | 2026-11-23 |
| builder | gpt-6-astra | - | - | 2026-11-23 |
| builder | gpt-6.1-sol | - | - | 2026-11-23 |
| builder | moonshotai/kimi-k3.1-pro | - | - | 2026-11-23 |
| cheap | gpt-6-luna | 1 | - | 2026-11-23 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-23 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-23 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-23 |
| cheap | gemini-4-hydrogen-high | 5 | - | 2026-11-23 |
| cheap | gemini-4-hydrogen-medium | 6 | - | 2026-11-23 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-23 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-23 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-23 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-23 |
| biology | gemini-4-neon-high | 5 | - | 2026-11-23 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-23 |
| batch | gpt-6.2-sol | 1 | - | 2026-11-23 |
| batch | gpt-6.2-astra | 2 | - | 2026-11-23 |
| batch | gemini-4-hydrogen-medium | 3 | - | 2026-11-23 |
| batch | claude-sonnet-5-5 | 4 | - | 2026-11-23 |
| batch | gemini-3.8-flash-high | 5 | - | 2026-11-23 |
| batch | gemini-3.8-flash-medium | 6 | - | 2026-11-23 |
| batch | gemini-4-hydrogen-high | 7 | - | 2026-11-23 |
| batch | gemini-4-argon-medium | - | - | 2026-11-23 |
| batch | gpt-6.1-sol | - | - | 2026-11-23 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-23 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-23 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-23 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-23 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-23 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-23 |
| ideation | gemini-4-neon-high | 6 | - | 2026-11-23 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-23 |
| design | claude-opus-5-5 | 1 | - | 2026-11-23 |
| design | claude-fable-5-2 | 2 | - | 2026-11-23 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-23 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-23 |
| design | gemini-4-neon-high | 5 | - | 2026-11-23 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-23 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-23 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-23 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-23 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-23 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-23 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-23 |
| judge | gemini-4-neon-high | 7 | - | 2026-11-23 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-23 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-24 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-24 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-24 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-24 |
| taste | gemini-4-neon-high | 5 | - | 2026-11-24 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-24 |
| review | gpt-6.2-astra | 1 | - | 2026-11-24 |
| review | claude-sonnet-5-5 | 2 | - | 2026-11-24 |
| review | claude-opus-5-5 | 3 | - | 2026-11-24 |
| review | claude-fable-5-2 | 4 | - | 2026-11-24 |
| review | gpt-6.2-sol | 5 | - | 2026-11-24 |
| review | gemini-3.8-flash-high | 6 | - | 2026-11-24 |
| review | gemini-3.8-flash-medium | 7 | - | 2026-11-24 |
| review | gemini-4-neon-high | 8 | - | 2026-11-24 |
| review | gemini-4-neon-medium | 9 | - | 2026-11-24 |
| review | gemini-4-hydrogen-medium | 10 | - | 2026-11-24 |
| review | gpt-5.6-sol | 11 | - | 2026-11-24 |
| review | gemini-3.8-flash-low | - | - | 2026-11-24 |
| review | gemini-4-argon-low | - | - | 2026-11-24 |
| review | gemini-4-argon-medium | - | - | 2026-11-24 |
| review | google/gemini-4-argon | - | - | 2026-11-24 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-24 |
| review | google/gemini-4-neon | - | - | 2026-11-24 |
| review | gpt-6.1-sol | - | - | 2026-11-24 |
| review | moonshotai/kimi-k3.1-pro | - | - | 2026-11-24 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-24 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-24 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-24 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-24 |
| mechanical | gemini-4-hydrogen-high | 5 | - | 2026-11-24 |
| mechanical | gemini-4-hydrogen-medium | 6 | - | 2026-11-24 |
| mechanical | claude-opus-5-5 | 7 | - | 2026-11-24 |
| mechanical | claude-fable-5-1 | - | - | 2026-11-24 |
| mechanical | claude-fable-5-2 | - | - | 2026-11-24 |
| mechanical | google/gemini-4-argon | - | - | 2026-11-24 |
| mechanical | google/gemini-4-carbon | - | - | 2026-11-24 |
| mechanical | google/gemini-4-hydrogen | - | - | 2026-11-24 |
| mechanical | google/gemini-4-neon | - | - | 2026-11-24 |
| mechanical | gpt-6.1-sol | - | - | 2026-11-24 |
| mechanical | gpt-6.2-astra | - | - | 2026-11-24 |
| mechanical | moonshotai/kimi-k3.1-pro | - | - | 2026-11-24 |
| mechanical | x-ai/grok-4.6 | - | - | 2026-11-24 |
| mechanical | z-ai/glm-5.3-flash | - | - | 2026-11-24 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-24 |
| builder | gemini-4-neon-medium | 2 | - | 2026-11-24 |
| builder | gemini-4-neon-high | 3 | - | 2026-11-24 |
| builder | gpt-6.2-sol | 4 | - | 2026-11-24 |
| builder | gemini-3.8-flash-high | 5 | - | 2026-11-24 |
| builder | gemini-3.8-flash-medium | 6 | - | 2026-11-24 |
| builder | claude-sonnet-5-5 | 7 | - | 2026-11-24 |
| builder | gpt-6.2-astra | 8 | - | 2026-11-24 |
| builder | claude-fable-5-1 | 9 | - | 2026-11-24 |
| builder | claude-fable-5-2 | 10 | - | 2026-11-24 |
| builder | gemini-4-argon-medium | - | - | 2026-11-24 |
| builder | gemini-4-hydrogen-low | - | - | 2026-11-24 |
| builder | google/gemini-4-argon | - | - | 2026-11-24 |
| builder | google/gemini-4-carbon | - | - | 2026-11-24 |
| builder | google/gemini-4-hydrogen | - | - | 2026-11-24 |
| builder | google/gemini-4-neon | - | - | 2026-11-24 |
| builder | gpt-6-astra | - | - | 2026-11-24 |
| builder | gpt-6.1-sol | - | - | 2026-11-24 |
| builder | moonshotai/kimi-k3.1-pro | - | - | 2026-11-24 |
| cheap | gpt-6-luna | 1 | - | 2026-11-24 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-24 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-24 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-24 |
| cheap | gemini-4-hydrogen-high | 5 | - | 2026-11-24 |
| cheap | gemini-4-hydrogen-medium | 6 | - | 2026-11-24 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-24 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-24 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-24 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-24 |
| biology | gemini-4-neon-high | 5 | - | 2026-11-24 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-24 |
| batch | gpt-6.2-sol | 1 | - | 2026-11-24 |
| batch | gpt-6.2-astra | 2 | - | 2026-11-24 |
| batch | gemini-4-hydrogen-medium | 3 | - | 2026-11-24 |
| batch | gemini-4-hydrogen-high | 4 | - | 2026-11-24 |
| batch | claude-sonnet-5-5 | 5 | - | 2026-11-24 |
| batch | gemini-3.8-flash-high | 6 | - | 2026-11-24 |
| batch | gemini-3.8-flash-medium | 7 | - | 2026-11-24 |
| batch | gemini-4-argon-medium | - | - | 2026-11-24 |
| batch | gpt-6.1-sol | - | - | 2026-11-24 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-24 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-24 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-24 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-24 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-24 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-24 |
| ideation | gemini-4-neon-high | 6 | - | 2026-11-24 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-24 |
| design | claude-opus-5-5 | 1 | - | 2026-11-24 |
| design | claude-fable-5-2 | 2 | - | 2026-11-24 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-24 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-24 |
| design | gemini-4-neon-high | 5 | - | 2026-11-24 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-24 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-24 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-24 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-24 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-24 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-24 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-24 |
| judge | gemini-4-neon-high | 7 | - | 2026-11-24 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-24 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-25 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-25 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-25 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-25 |
| taste | gemini-4-neon-high | 5 | - | 2026-11-25 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-25 |
| review | gpt-6.2-astra | 1 | - | 2026-11-25 |
| review | claude-sonnet-5-5 | 2 | - | 2026-11-25 |
| review | claude-opus-5-5 | 3 | - | 2026-11-25 |
| review | claude-fable-5-2 | 4 | - | 2026-11-25 |
| review | gpt-6.2-sol | 5 | - | 2026-11-25 |
| review | gemini-3.8-flash-high | 6 | - | 2026-11-25 |
| review | gemini-3.8-flash-medium | 7 | - | 2026-11-25 |
| review | gemini-4-neon-high | 8 | - | 2026-11-25 |
| review | gemini-4-neon-medium | 9 | - | 2026-11-25 |
| review | gemini-4-hydrogen-medium | 10 | - | 2026-11-25 |
| review | gpt-5.6-sol | 11 | - | 2026-11-25 |
| review | gemini-3.8-flash-low | - | - | 2026-11-25 |
| review | gemini-4-argon-low | - | - | 2026-11-25 |
| review | gemini-4-argon-medium | - | - | 2026-11-25 |
| review | google/gemini-4-argon | - | - | 2026-11-25 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-25 |
| review | google/gemini-4-neon | - | - | 2026-11-25 |
| review | gpt-6.1-sol | - | - | 2026-11-25 |
| review | moonshotai/kimi-k3.1-pro | - | - | 2026-11-25 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-25 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-25 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-25 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-25 |
| mechanical | gemini-4-hydrogen-high | 5 | - | 2026-11-25 |
| mechanical | gemini-4-hydrogen-medium | 6 | - | 2026-11-25 |
| mechanical | claude-opus-5-5 | 7 | - | 2026-11-25 |
| mechanical | claude-fable-5-1 | - | - | 2026-11-25 |
| mechanical | claude-fable-5-2 | - | - | 2026-11-25 |
| mechanical | google/gemini-4-argon | - | - | 2026-11-25 |
| mechanical | google/gemini-4-carbon | - | - | 2026-11-25 |
| mechanical | google/gemini-4-hydrogen | - | - | 2026-11-25 |
| mechanical | google/gemini-4-neon | - | - | 2026-11-25 |
| mechanical | gpt-6.1-sol | - | - | 2026-11-25 |
| mechanical | gpt-6.2-astra | - | - | 2026-11-25 |
| mechanical | moonshotai/kimi-k3.1-pro | - | - | 2026-11-25 |
| mechanical | x-ai/grok-4.6 | - | - | 2026-11-25 |
| mechanical | z-ai/glm-5.3-flash | - | - | 2026-11-25 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-25 |
| builder | gemini-4-neon-medium | 2 | - | 2026-11-25 |
| builder | gpt-6.2-sol | 3 | - | 2026-11-25 |
| builder | gemini-4-neon-high | 4 | - | 2026-11-25 |
| builder | gemini-3.8-flash-high | 5 | - | 2026-11-25 |
| builder | gemini-3.8-flash-medium | 6 | - | 2026-11-25 |
| builder | claude-sonnet-5-5 | 7 | - | 2026-11-25 |
| builder | gpt-6.2-astra | 8 | - | 2026-11-25 |
| builder | claude-fable-5-1 | 9 | - | 2026-11-25 |
| builder | claude-fable-5-2 | 10 | - | 2026-11-25 |
| builder | gemini-4-argon-medium | - | - | 2026-11-25 |
| builder | gemini-4-hydrogen-low | - | - | 2026-11-25 |
| builder | google/gemini-4-argon | - | - | 2026-11-25 |
| builder | google/gemini-4-carbon | - | - | 2026-11-25 |
| builder | google/gemini-4-hydrogen | - | - | 2026-11-25 |
| builder | google/gemini-4-neon | - | - | 2026-11-25 |
| builder | gpt-6-astra | - | - | 2026-11-25 |
| builder | gpt-6.1-sol | - | - | 2026-11-25 |
| builder | moonshotai/kimi-k3.1-pro | - | - | 2026-11-25 |
| cheap | gpt-6-luna | 1 | - | 2026-11-25 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-25 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-25 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-25 |
| cheap | gemini-4-hydrogen-high | 5 | - | 2026-11-25 |
| cheap | gemini-4-hydrogen-medium | 6 | - | 2026-11-25 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-25 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-25 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-25 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-25 |
| biology | gemini-4-neon-high | 5 | - | 2026-11-25 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-25 |
| batch | gpt-6.2-sol | 1 | - | 2026-11-25 |
| batch | gpt-6.2-astra | 2 | - | 2026-11-25 |
| batch | gemini-4-hydrogen-medium | 3 | - | 2026-11-25 |
| batch | gemini-4-hydrogen-high | 4 | - | 2026-11-25 |
| batch | claude-sonnet-5-5 | 5 | - | 2026-11-25 |
| batch | gemini-3.8-flash-high | 6 | - | 2026-11-25 |
| batch | gemini-3.8-flash-medium | 7 | - | 2026-11-25 |
| batch | gemini-4-argon-medium | - | - | 2026-11-25 |
| batch | gpt-6.1-sol | - | - | 2026-11-25 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-25 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-25 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-25 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-25 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-25 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-25 |
| ideation | gemini-4-neon-high | 6 | - | 2026-11-25 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-25 |
| design | claude-opus-5-5 | 1 | - | 2026-11-25 |
| design | claude-fable-5-2 | 2 | - | 2026-11-25 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-25 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-25 |
| design | gemini-4-neon-high | 5 | - | 2026-11-25 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-25 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-25 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-25 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-25 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-25 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-25 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-25 |
| judge | gemini-4-neon-high | 7 | - | 2026-11-25 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-25 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-26 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-26 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-26 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-26 |
| taste | gemini-4-neon-high | 5 | - | 2026-11-26 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-26 |
| review | gpt-6.2-astra | 1 | - | 2026-11-26 |
| review | gemini-4-neon-high | 2 | - | 2026-11-26 |
| review | claude-sonnet-5-5 | 3 | - | 2026-11-26 |
| review | claude-opus-5-5 | 4 | - | 2026-11-26 |
| review | claude-fable-5-2 | 5 | - | 2026-11-26 |
| review | gpt-6.2-sol | 6 | - | 2026-11-26 |
| review | gemini-3.8-flash-high | 7 | - | 2026-11-26 |
| review | gemini-3.8-flash-medium | 8 | - | 2026-11-26 |
| review | gemini-4-neon-medium | 9 | - | 2026-11-26 |
| review | gemini-4-hydrogen-medium | 10 | - | 2026-11-26 |
| review | gemini-4-carbon-high | 11 | - | 2026-11-26 |
| review | claude-fable-5-1 | 12 | - | 2026-11-26 |
| review | gpt-5.6-sol | 13 | - | 2026-11-26 |
| review | gemini-3.8-flash-low | - | - | 2026-11-26 |
| review | gemini-4-argon-low | - | - | 2026-11-26 |
| review | gemini-4-argon-medium | - | - | 2026-11-26 |
| review | google/gemini-4-argon | - | - | 2026-11-26 |
| review | google/gemini-4-hydrogen | - | - | 2026-11-26 |
| review | google/gemini-4-neon | - | - | 2026-11-26 |
| review | gpt-6.1-sol | - | - | 2026-11-26 |
| review | moonshotai/kimi-k3.1-pro | - | - | 2026-11-26 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-26 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-26 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-26 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-26 |
| mechanical | gemini-4-hydrogen-high | 5 | - | 2026-11-26 |
| mechanical | gemini-4-hydrogen-medium | 6 | - | 2026-11-26 |
| mechanical | claude-opus-5-5 | 7 | - | 2026-11-26 |
| mechanical | claude-fable-5-1 | - | - | 2026-11-26 |
| mechanical | claude-fable-5-2 | - | - | 2026-11-26 |
| mechanical | google/gemini-4-argon | - | - | 2026-11-26 |
| mechanical | google/gemini-4-carbon | - | - | 2026-11-26 |
| mechanical | google/gemini-4-hydrogen | - | - | 2026-11-26 |
| mechanical | google/gemini-4-neon | - | - | 2026-11-26 |
| mechanical | gpt-6.1-sol | - | - | 2026-11-26 |
| mechanical | gpt-6.2-astra | - | - | 2026-11-26 |
| mechanical | moonshotai/kimi-k3.1-pro | - | - | 2026-11-26 |
| mechanical | x-ai/grok-4.6 | - | - | 2026-11-26 |
| mechanical | x-ai/grok-4.7 | - | - | 2026-11-26 |
| mechanical | z-ai/glm-5.3-flash | - | - | 2026-11-26 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-26 |
| builder | gemini-4-neon-high | 2 | - | 2026-11-26 |
| builder | gemini-4-neon-medium | 3 | - | 2026-11-26 |
| builder | gpt-6.2-sol | 4 | - | 2026-11-26 |
| builder | gemini-3.8-flash-high | 5 | - | 2026-11-26 |
| builder | gemini-3.8-flash-medium | 6 | - | 2026-11-26 |
| builder | claude-sonnet-5-5 | 7 | - | 2026-11-26 |
| builder | gpt-6.2-astra | 8 | - | 2026-11-26 |
| builder | claude-fable-5-1 | 9 | - | 2026-11-26 |
| builder | claude-fable-5-2 | 10 | - | 2026-11-26 |
| builder | gemini-4-argon-medium | - | - | 2026-11-26 |
| builder | gemini-4-hydrogen-low | - | - | 2026-11-26 |
| builder | google/gemini-4-argon | - | - | 2026-11-26 |
| builder | google/gemini-4-carbon | - | - | 2026-11-26 |
| builder | google/gemini-4-hydrogen | - | - | 2026-11-26 |
| builder | google/gemini-4-neon | - | - | 2026-11-26 |
| builder | gpt-6-astra | - | - | 2026-11-26 |
| builder | gpt-6.1-sol | - | - | 2026-11-26 |
| builder | moonshotai/kimi-k3.1-pro | - | - | 2026-11-26 |
| builder | x-ai/grok-4.7 | - | - | 2026-11-26 |
| cheap | gpt-6-luna | 1 | - | 2026-11-26 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-26 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-26 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-26 |
| cheap | gemini-4-hydrogen-high | 5 | - | 2026-11-26 |
| cheap | gemini-4-hydrogen-medium | 6 | - | 2026-11-26 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-26 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-26 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-26 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-26 |
| biology | gemini-4-neon-high | 5 | - | 2026-11-26 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-26 |
| batch | gpt-6.2-astra | 1 | - | 2026-11-26 |
| batch | gemini-4-carbon-high | 2 | - | 2026-11-26 |
| batch | gpt-6.2-sol | 3 | - | 2026-11-26 |
| batch | gemini-4-hydrogen-medium | 4 | - | 2026-11-26 |
| batch | gemini-4-hydrogen-high | 5 | - | 2026-11-26 |
| batch | claude-sonnet-5-5 | 6 | - | 2026-11-26 |
| batch | gemini-3.8-flash-high | 7 | - | 2026-11-26 |
| batch | gemini-3.8-flash-medium | 8 | - | 2026-11-26 |
| batch | gemini-4-argon-medium | - | - | 2026-11-26 |
| batch | gpt-6.1-sol | - | - | 2026-11-26 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-26 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-26 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-26 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-26 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-26 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-26 |
| ideation | gemini-4-neon-high | 6 | - | 2026-11-26 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-26 |
| design | claude-opus-5-5 | 1 | - | 2026-11-26 |
| design | claude-fable-5-2 | 2 | - | 2026-11-26 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-26 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-26 |
| design | gemini-4-neon-high | 5 | - | 2026-11-26 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-26 |
| design | gpt-6.2-sol | 7 | - | 2026-11-26 |
| design | gpt-6.2-astra | 8 | - | 2026-11-26 |
| judge | claude-opus-5-5 | 1 | - | 2026-11-26 |
| judge | gpt-6.2-astra | 2 | - | 2026-11-26 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-26 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-26 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-26 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-26 |
| judge | gemini-4-neon-high | 7 | - | 2026-11-26 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-26 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-27 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-27 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-27 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-27 |
| taste | gemini-4-neon-high | 5 | - | 2026-11-27 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-27 |
| review | gpt-6.2-astra | 1 | - | 2026-11-27 |
| review | gemini-4-neon-high | 2 | - | 2026-11-27 |
| review | claude-opus-5-5 | 3 | - | 2026-11-27 |
| review | claude-sonnet-5-5 | 4 | - | 2026-11-27 |
| review | gemini-4-carbon-high | 5 | - | 2026-11-27 |
| review | claude-fable-5-2 | 6 | - | 2026-11-27 |
| review | gpt-6.2-sol | 7 | - | 2026-11-27 |
| review | gemini-3.8-flash-high | 8 | - | 2026-11-27 |
| review | gemini-3.8-flash-medium | 9 | - | 2026-11-27 |
| review | gemini-4-neon-medium | 10 | - | 2026-11-27 |
| review | gemini-4-hydrogen-medium | 11 | - | 2026-11-27 |
| review | claude-fable-5-1 | 12 | - | 2026-11-27 |
| review | gpt-5.6-sol | 13 | - | 2026-11-27 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-27 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-27 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-27 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-27 |
| mechanical | gemini-4-hydrogen-high | 5 | - | 2026-11-27 |
| mechanical | gemini-4-hydrogen-medium | 6 | - | 2026-11-27 |
| mechanical | claude-opus-5-5 | 7 | - | 2026-11-27 |
| mechanical | gemini-4-neon-high | 8 | - | 2026-11-27 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-27 |
| builder | gemini-4-neon-high | 2 | - | 2026-11-27 |
| builder | gpt-6.2-sol | 3 | - | 2026-11-27 |
| builder | gemini-4-neon-medium | 4 | - | 2026-11-27 |
| builder | gemini-3.8-flash-high | 5 | - | 2026-11-27 |
| builder | gemini-3.8-flash-medium | 6 | - | 2026-11-27 |
| builder | claude-sonnet-5-5 | 7 | - | 2026-11-27 |
| builder | gpt-6.2-astra | 8 | - | 2026-11-27 |
| builder | claude-fable-5-1 | 9 | - | 2026-11-27 |
| builder | claude-fable-5-2 | 10 | - | 2026-11-27 |
| cheap | gpt-6-luna | 1 | - | 2026-11-27 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-27 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-27 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-27 |
| cheap | gemini-4-hydrogen-high | 5 | - | 2026-11-27 |
| cheap | gemini-4-hydrogen-medium | 6 | - | 2026-11-27 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-27 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-27 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-27 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-27 |
| biology | gemini-4-neon-high | 5 | - | 2026-11-27 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-27 |
| batch | gemini-4-neon-high | 1 | - | 2026-11-27 |
| batch | gpt-6.2-astra | 2 | - | 2026-11-27 |
| batch | gpt-6.2-sol | 3 | - | 2026-11-27 |
| batch | gemini-4-carbon-high | 4 | - | 2026-11-27 |
| batch | gemini-4-hydrogen-medium | 5 | - | 2026-11-27 |
| batch | gemini-4-hydrogen-high | 6 | - | 2026-11-27 |
| batch | claude-sonnet-5-5 | 7 | - | 2026-11-27 |
| batch | gemini-3.8-flash-high | 8 | - | 2026-11-27 |
| batch | gemini-3.8-flash-medium | 9 | - | 2026-11-27 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-27 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-27 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-27 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-27 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-27 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-27 |
| ideation | gemini-4-neon-high | 6 | - | 2026-11-27 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-27 |
| design | claude-opus-5-5 | 1 | - | 2026-11-27 |
| design | claude-fable-5-2 | 2 | - | 2026-11-27 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-27 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-27 |
| design | gemini-4-neon-high | 5 | - | 2026-11-27 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-27 |
| design | gpt-6.2-astra | 7 | - | 2026-11-27 |
| design | gpt-6.2-sol | 8 | - | 2026-11-27 |
| judge | gpt-6.2-astra | 1 | - | 2026-11-27 |
| judge | claude-opus-5-5 | 2 | - | 2026-11-27 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-27 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-27 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-27 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-27 |
| judge | gemini-4-neon-high | 7 | - | 2026-11-27 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-27 |
| taste | claude-opus-5-5 | 1 | - | 2026-11-28 |
| taste | claude-fable-5-2 | 2 | - | 2026-11-28 |
| taste | gemini-3.8-flash-high | 3 | - | 2026-11-28 |
| taste | gemini-3.8-flash-medium | 4 | - | 2026-11-28 |
| taste | gemini-4-neon-high | 5 | - | 2026-11-28 |
| taste | gemini-4-neon-medium | 6 | - | 2026-11-28 |
| review | gpt-6.2-astra | 1 | - | 2026-11-28 |
| review | claude-opus-5-5 | 2 | - | 2026-11-28 |
| review | gemini-4-neon-high | 3 | - | 2026-11-28 |
| review | claude-sonnet-5-5 | 4 | - | 2026-11-28 |
| review | gemini-4-carbon-high | 5 | - | 2026-11-28 |
| review | claude-fable-5-2 | 6 | - | 2026-11-28 |
| review | gpt-6.2-sol | 7 | - | 2026-11-28 |
| review | gemini-3.8-flash-high | 8 | - | 2026-11-28 |
| review | gemini-3.8-flash-medium | 9 | - | 2026-11-28 |
| review | gemini-4-neon-medium | 10 | - | 2026-11-28 |
| review | gemini-4-hydrogen-medium | 11 | - | 2026-11-28 |
| review | claude-fable-5-1 | 12 | - | 2026-11-28 |
| review | gpt-5.6-sol | 13 | - | 2026-11-28 |
| mechanical | gpt-6.2-sol | 1 | - | 2026-11-28 |
| mechanical | claude-sonnet-5-5 | 2 | - | 2026-11-28 |
| mechanical | gemini-3.8-flash-high | 3 | - | 2026-11-28 |
| mechanical | gemini-3.8-flash-medium | 4 | - | 2026-11-28 |
| mechanical | gemini-4-hydrogen-high | 5 | - | 2026-11-28 |
| mechanical | gemini-4-hydrogen-medium | 6 | - | 2026-11-28 |
| mechanical | claude-opus-5-5 | 7 | - | 2026-11-28 |
| mechanical | gemini-4-neon-high | 8 | - | 2026-11-28 |
| builder | claude-opus-5-5 | 1 | - | 2026-11-28 |
| builder | gemini-4-neon-high | 2 | - | 2026-11-28 |
| builder | gpt-6.2-sol | 3 | - | 2026-11-28 |
| builder | gemini-4-neon-medium | 4 | - | 2026-11-28 |
| builder | claude-sonnet-5-5 | 5 | - | 2026-11-28 |
| builder | gemini-3.8-flash-high | 6 | - | 2026-11-28 |
| builder | gemini-3.8-flash-medium | 7 | - | 2026-11-28 |
| builder | gpt-6.2-astra | 8 | - | 2026-11-28 |
| builder | claude-fable-5-1 | 9 | - | 2026-11-28 |
| builder | claude-fable-5-2 | 10 | - | 2026-11-28 |
| cheap | gpt-6-luna | 1 | - | 2026-11-28 |
| cheap | claude-haiku-5-5 | 2 | - | 2026-11-28 |
| cheap | gemini-3.8-flash-high | 3 | - | 2026-11-28 |
| cheap | gemini-3.8-flash-medium | 4 | - | 2026-11-28 |
| cheap | gemini-4-hydrogen-high | 5 | - | 2026-11-28 |
| cheap | gemini-4-hydrogen-medium | 6 | - | 2026-11-28 |
| biology | claude-opus-5-5 | 1 | - | 2026-11-28 |
| biology | gpt-6.2-astra | 2 | - | 2026-11-28 |
| biology | gemini-3.8-flash-high | 3 | - | 2026-11-28 |
| biology | gemini-3.8-flash-medium | 4 | - | 2026-11-28 |
| biology | gemini-4-neon-high | 5 | - | 2026-11-28 |
| biology | gemini-4-neon-medium | 6 | - | 2026-11-28 |
| batch | gemini-4-neon-high | 1 | - | 2026-11-28 |
| batch | gpt-6.2-astra | 2 | - | 2026-11-28 |
| batch | gpt-6.2-sol | 3 | - | 2026-11-28 |
| batch | gemini-4-carbon-high | 4 | - | 2026-11-28 |
| batch | gemini-4-hydrogen-medium | 5 | - | 2026-11-28 |
| batch | gemini-4-hydrogen-high | 6 | - | 2026-11-28 |
| batch | claude-sonnet-5-5 | 7 | - | 2026-11-28 |
| batch | gemini-3.8-flash-high | 8 | - | 2026-11-28 |
| batch | gemini-3.8-flash-medium | 9 | - | 2026-11-28 |
| writing | claude-opus-5-5 | 1 | - | 2026-11-28 |
| ideation | claude-fable-5-2 | 1 | - | 2026-11-28 |
| ideation | gpt-6.2-astra | 2 | - | 2026-11-28 |
| ideation | claude-opus-5-5 | 3 | - | 2026-11-28 |
| ideation | gemini-3.8-flash-high | 4 | - | 2026-11-28 |
| ideation | gemini-3.8-flash-medium | 5 | - | 2026-11-28 |
| ideation | gemini-4-neon-high | 6 | - | 2026-11-28 |
| ideation | gemini-4-neon-medium | 7 | - | 2026-11-28 |
| design | claude-opus-5-5 | 1 | - | 2026-11-28 |
| design | claude-fable-5-2 | 2 | - | 2026-11-28 |
| design | gemini-3.8-flash-high | 3 | - | 2026-11-28 |
| design | gemini-3.8-flash-medium | 4 | - | 2026-11-28 |
| design | gemini-4-neon-high | 5 | - | 2026-11-28 |
| design | gemini-4-neon-medium | 6 | - | 2026-11-28 |
| design | gpt-6.2-astra | 7 | - | 2026-11-28 |
| design | gpt-6.2-sol | 8 | - | 2026-11-28 |
| judge | gpt-6.2-astra | 1 | - | 2026-11-28 |
| judge | claude-opus-5-5 | 2 | - | 2026-11-28 |
| judge | claude-fable-5-2 | 3 | - | 2026-11-28 |
| judge | gpt-6.2-sol | 4 | - | 2026-11-28 |
| judge | gemini-3.8-flash-high | 5 | - | 2026-11-28 |
| judge | gemini-3.8-flash-medium | 6 | - | 2026-11-28 |
| judge | gemini-4-neon-high | 7 | - | 2026-11-28 |
| judge | gemini-4-neon-medium | 8 | - | 2026-11-28 |

</details>

<details>
<summary>Historical held-outcome scores (before 2026-11-19)</summary>

| Role | Model | Routing order | Held score | Wilson lower score | Date |
|---|---|---:|---:|---:|---|
| taste | claude-opus-5-5 | 1 | 0.333 | 0.097 | 2026-11-03 |
| taste | claude-fable-5-1 | 2 | - | - | 2026-11-03 |
| taste | deepseek/deepseek-v4.1-flash-1017 | - | 0.0 | 0.0 | 2026-11-03 |
| taste | gpt-6.1-sol | - | 0.0 | 0.0 | 2026-11-03 |
| review | claude-opus-5-5 | 1 | - | - | 2026-11-03 |
| review | gpt-6-astra | 2 | 1.0 | 0.342 | 2026-11-03 |
| review | claude-fable-5-1 | 3 | - | - | 2026-11-03 |
| review | gpt-6.1-sol | 4 | - | - | 2026-11-03 |
| mechanical | gpt-6.1-sol | 1 | 1.0 | 0.207 | 2026-11-03 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | 1.0 | 0.438 | 2026-11-03 |
| builder | claude-opus-5-5 | 1 | 1.0 | 0.207 | 2026-11-03 |
| builder | gpt-6.1-sol | 2 | 1.0 | 0.342 | 2026-11-03 |
| builder | deepseek/deepseek-v4.1-flash-1017 | - | 0.0 | 0.0 | 2026-11-03 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | - | 2026-11-03 |
| cheap | z-ai/glm-5.3-flash | 2 | - | - | 2026-11-03 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | - | 2026-11-03 |
| batch | gpt-6.1-sol | 1 | 0.824 | 0.748 | 2026-11-03 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-03 |
| writing | claude-opus-5-5 | 1 | 1.0 | 0.51 | 2026-11-03 |
| ideation | claude-opus-5-5 | 1 | 0.5 | 0.268 | 2026-11-03 |
| ideation | gpt-6-astra | 2 | 0.933 | 0.702 | 2026-11-03 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | - | 2026-11-03 |
| taste | claude-opus-5-5 | 1 | - | - | 2026-11-14 |
| taste | claude-fable-5-2 | 2 | - | - | 2026-11-14 |
| review | claude-opus-5-5 | 1 | 1.0 | 0.207 | 2026-11-14 |
| review | gpt-6-astra | 2 | - | - | 2026-11-14 |
| review | claude-fable-5-2 | 3 | - | - | 2026-11-14 |
| review | gpt-6.1-sol | 4 | - | - | 2026-11-14 |
| review | gpt-5.6-sol | 5 | - | - | 2026-11-14 |
| review | moonshotai/kimi-k3.1-pro | 6 | - | - | 2026-11-14 |
| review | google/gemini-4-argon | 7 | - | - | 2026-11-14 |
| review | claude-sonnet-5-5 | 8 | - | - | 2026-11-14 |
| mechanical | gpt-6.1-sol | 1 | - | - | 2026-11-14 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-14 |
| builder | claude-opus-5-5 | 1 | - | - | 2026-11-14 |
| builder | gpt-6.1-sol | 2 | - | - | 2026-11-14 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | - | 2026-11-14 |
| cheap | z-ai/glm-5.3-flash | 2 | - | - | 2026-11-14 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | - | 2026-11-14 |
| batch | gpt-6.1-sol | 1 | 1.0 | 0.867 | 2026-11-14 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-14 |
| batch | gpt-6-astra | 3 | - | - | 2026-11-14 |
| writing | claude-opus-5-5 | 1 | - | - | 2026-11-14 |
| ideation | claude-opus-5-5 | 1 | - | - | 2026-11-14 |
| ideation | gpt-6-astra | 2 | - | - | 2026-11-14 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | - | 2026-11-14 |
| ideation | claude-fable-5-2 | 4 | 1.0 | 0.741 | 2026-11-14 |
| ideation | gpt-6.1-sol | 5 | - | - | 2026-11-14 |
| design | claude-opus-5-5 | 1 | - | - | 2026-11-14 |
| design | claude-fable-5-2 | 2 | 1.0 | 0.342 | 2026-11-14 |
| design | gpt-6.1-sol | 3 | - | - | 2026-11-14 |
| judge | claude-opus-5-5 | 1 | - | - | 2026-11-14 |
| judge | gpt-6-astra | 2 | - | - | 2026-11-14 |
| judge | claude-fable-5-2 | 3 | 0.0 | 0.0 | 2026-11-14 |
| judge | gpt-6.1-sol | 4 | - | - | 2026-11-14 |
| taste | claude-opus-5-5 | 1 | - | - | 2026-11-15 |
| taste | claude-fable-5-2 | 2 | - | - | 2026-11-15 |
| review | claude-opus-5-5 | 1 | 1.0 | 0.207 | 2026-11-15 |
| review | gpt-6-astra | 2 | - | - | 2026-11-15 |
| review | claude-fable-5-2 | 3 | - | - | 2026-11-15 |
| review | gpt-6.1-sol | 4 | - | - | 2026-11-15 |
| review | gpt-5.6-sol | 5 | - | - | 2026-11-15 |
| review | moonshotai/kimi-k3.1-pro | 6 | - | - | 2026-11-15 |
| review | google/gemini-4-argon | 7 | - | - | 2026-11-15 |
| review | claude-sonnet-5-5 | 8 | - | - | 2026-11-15 |
| mechanical | gpt-6.1-sol | 1 | - | - | 2026-11-15 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-15 |
| builder | claude-opus-5-5 | 1 | - | - | 2026-11-15 |
| builder | gpt-6.1-sol | 2 | - | - | 2026-11-15 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | - | 2026-11-15 |
| cheap | z-ai/glm-5.3-flash | 2 | - | - | 2026-11-15 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | - | 2026-11-15 |
| batch | gpt-6.1-sol | 1 | 1.0 | 0.867 | 2026-11-15 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-15 |
| batch | gpt-6-astra | 3 | - | - | 2026-11-15 |
| writing | claude-opus-5-5 | 1 | - | - | 2026-11-15 |
| ideation | claude-opus-5-5 | 1 | - | - | 2026-11-15 |
| ideation | gpt-6-astra | 2 | - | - | 2026-11-15 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | - | 2026-11-15 |
| ideation | claude-fable-5-2 | 4 | 1.0 | 0.741 | 2026-11-15 |
| ideation | gpt-6.1-sol | 5 | - | - | 2026-11-15 |
| design | claude-opus-5-5 | 1 | - | - | 2026-11-15 |
| design | claude-fable-5-2 | 2 | 1.0 | 0.438 | 2026-11-15 |
| design | gpt-6.1-sol | 3 | - | - | 2026-11-15 |
| judge | claude-opus-5-5 | 1 | - | - | 2026-11-15 |
| judge | gpt-6-astra | 2 | - | - | 2026-11-15 |
| judge | claude-fable-5-2 | 3 | 0.0 | 0.0 | 2026-11-15 |
| judge | gpt-6.1-sol | 4 | - | - | 2026-11-15 |
| taste | claude-opus-5-5 | 1 | - | - | 2026-11-16 |
| taste | claude-fable-5-2 | 2 | - | - | 2026-11-16 |
| taste | gpt-6-astra | 3 | - | - | 2026-11-16 |
| review | claude-opus-5-5 | 1 | 1.0 | 0.207 | 2026-11-16 |
| review | gpt-6-astra | 2 | - | - | 2026-11-16 |
| review | claude-fable-5-2 | 3 | - | - | 2026-11-16 |
| review | gpt-6.1-sol | 4 | - | - | 2026-11-16 |
| review | google/gemini-4-carbon | 5 | - | - | 2026-11-16 |
| review | google/gemini-4-hydrogen | 6 | - | - | 2026-11-16 |
| review | gpt-5.6-sol | 7 | - | - | 2026-11-16 |
| review | moonshotai/kimi-k3.1-pro | 8 | - | - | 2026-11-16 |
| review | google/gemini-4-argon | 9 | - | - | 2026-11-16 |
| review | claude-sonnet-5-5 | 10 | - | - | 2026-11-16 |
| mechanical | gpt-6.1-sol | 1 | - | - | 2026-11-16 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-16 |
| mechanical | google/gemini-4-carbon | 3 | - | - | 2026-11-16 |
| mechanical | google/gemini-4-hydrogen | 4 | - | - | 2026-11-16 |
| builder | claude-opus-5-5 | 1 | - | - | 2026-11-16 |
| builder | gpt-6.1-sol | 2 | - | - | 2026-11-16 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | - | 2026-11-16 |
| cheap | z-ai/glm-5.3-flash | 2 | - | - | 2026-11-16 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | - | 2026-11-16 |
| batch | gpt-6.1-sol | 1 | 1.0 | 0.867 | 2026-11-16 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-16 |
| batch | google/gemini-4-carbon | 3 | - | - | 2026-11-16 |
| batch | google/gemini-4-hydrogen | 4 | - | - | 2026-11-16 |
| batch | gpt-6-astra | 5 | - | - | 2026-11-16 |
| writing | claude-opus-5-5 | 1 | - | - | 2026-11-16 |
| ideation | claude-opus-5-5 | 1 | 1.0 | 0.342 | 2026-11-16 |
| ideation | gpt-6-astra | 2 | - | - | 2026-11-16 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | - | 2026-11-16 |
| ideation | google/gemini-4-carbon | 4 | - | - | 2026-11-16 |
| ideation | google/gemini-4-hydrogen | 5 | - | - | 2026-11-16 |
| ideation | claude-fable-5-2 | 6 | 1.0 | 0.741 | 2026-11-16 |
| ideation | gpt-6.1-sol | 7 | - | - | 2026-11-16 |
| design | claude-opus-5-5 | 1 | - | - | 2026-11-16 |
| design | claude-fable-5-2 | 2 | 1.0 | 0.438 | 2026-11-16 |
| design | google/gemini-4-carbon | 3 | - | - | 2026-11-16 |
| design | google/gemini-4-hydrogen | 4 | - | - | 2026-11-16 |
| design | gpt-6.1-sol | 5 | - | - | 2026-11-16 |
| judge | claude-opus-5-5 | 1 | - | - | 2026-11-16 |
| judge | gpt-6-astra | 2 | - | - | 2026-11-16 |
| judge | claude-fable-5-2 | 3 | 0.0 | 0.0 | 2026-11-16 |
| judge | gpt-6.1-sol | 4 | - | - | 2026-11-16 |
| judge | google/gemini-4-carbon | 5 | - | - | 2026-11-16 |
| judge | google/gemini-4-hydrogen | 6 | - | - | 2026-11-16 |
| taste | claude-opus-5-5 | 1 | - | - | 2026-11-17 |
| taste | claude-fable-5-2 | 2 | - | - | 2026-11-17 |
| taste | gpt-6-astra | 3 | - | - | 2026-11-17 |
| review | claude-opus-5-5 | 1 | 1.0 | 0.207 | 2026-11-17 |
| review | gpt-6-astra | 2 | 0.6 | 0.231 | 2026-11-17 |
| review | claude-fable-5-2 | 3 | - | - | 2026-11-17 |
| review | gpt-6.1-sol | 4 | 0.8 | 0.376 | 2026-11-17 |
| review | google/gemini-4-carbon | 5 | - | - | 2026-11-17 |
| review | google/gemini-4-hydrogen | 6 | - | - | 2026-11-17 |
| review | gpt-5.6-sol | 7 | - | - | 2026-11-17 |
| review | moonshotai/kimi-k3.1-pro | 8 | - | - | 2026-11-17 |
| review | google/gemini-4-argon | 9 | - | - | 2026-11-17 |
| review | gpt-6.2-astra | 10 | - | - | 2026-11-17 |
| review | claude-sonnet-5-5 | 11 | - | - | 2026-11-17 |
| mechanical | gpt-6.1-sol | 1 | - | - | 2026-11-17 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-17 |
| mechanical | google/gemini-4-carbon | 3 | - | - | 2026-11-17 |
| mechanical | google/gemini-4-hydrogen | 4 | - | - | 2026-11-17 |
| builder | claude-opus-5-5 | 1 | - | - | 2026-11-17 |
| builder | gpt-6.1-sol | 2 | - | - | 2026-11-17 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | - | 2026-11-17 |
| cheap | z-ai/glm-5.3-flash | 2 | - | - | 2026-11-17 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | - | 2026-11-17 |
| batch | gpt-6.1-sol | 1 | 1.0 | 0.867 | 2026-11-17 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-17 |
| batch | google/gemini-4-carbon | 3 | - | - | 2026-11-17 |
| batch | google/gemini-4-hydrogen | 4 | - | - | 2026-11-17 |
| batch | gpt-6-astra | 5 | - | - | 2026-11-17 |
| writing | claude-opus-5-5 | 1 | - | - | 2026-11-17 |
| ideation | claude-opus-5-5 | 1 | 1.0 | 0.342 | 2026-11-17 |
| ideation | gpt-6-astra | 2 | - | - | 2026-11-17 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | - | 2026-11-17 |
| ideation | google/gemini-4-carbon | 4 | - | - | 2026-11-17 |
| ideation | google/gemini-4-hydrogen | 5 | - | - | 2026-11-17 |
| ideation | claude-fable-5-2 | 6 | 1.0 | 0.741 | 2026-11-17 |
| ideation | gpt-6.1-sol | 7 | - | - | 2026-11-17 |
| design | claude-opus-5-5 | 1 | - | - | 2026-11-17 |
| design | claude-fable-5-2 | 2 | 1.0 | 0.438 | 2026-11-17 |
| design | google/gemini-4-carbon | 3 | - | - | 2026-11-17 |
| design | google/gemini-4-hydrogen | 4 | - | - | 2026-11-17 |
| design | gpt-6.1-sol | 5 | - | - | 2026-11-17 |
| judge | claude-opus-5-5 | 1 | - | - | 2026-11-17 |
| judge | gpt-6-astra | 2 | 1.0 | 0.61 | 2026-11-17 |
| judge | claude-fable-5-2 | 3 | 0.0 | 0.0 | 2026-11-17 |
| judge | gpt-6.1-sol | 4 | 0.833 | 0.436 | 2026-11-17 |
| judge | google/gemini-4-carbon | 5 | - | - | 2026-11-17 |
| judge | google/gemini-4-hydrogen | 6 | - | - | 2026-11-17 |
| judge | gpt-6.2-astra | 7 | - | - | 2026-11-17 |
| taste | claude-opus-5-5 | 1 | - | - | 2026-11-18 |
| taste | claude-fable-5-2 | 2 | - | - | 2026-11-18 |
| review | claude-opus-5-5 | 1 | 1.0 | 0.566 | 2026-11-18 |
| review | gpt-6.2-astra | 2 | - | - | 2026-11-18 |
| review | claude-fable-5-2 | 3 | - | - | 2026-11-18 |
| review | gpt-6.2-sol | 4 | - | - | 2026-11-18 |
| review | gpt-5.6-sol | 5 | - | - | 2026-11-18 |
| review | moonshotai/kimi-k3.1-pro | 6 | - | - | 2026-11-18 |
| review | claude-sonnet-5-5 | 7 | - | - | 2026-11-18 |
| review | gpt-6-astra | 8 | - | - | 2026-11-18 |
| review | gpt-6.1-sol | 9 | - | - | 2026-11-18 |
| review | google/gemini-4-argon | - | - | - | 2026-11-18 |
| review | google/gemini-4-hydrogen | - | - | - | 2026-11-18 |
| mechanical | gpt-6.2-sol | 1 | - | - | 2026-11-18 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-18 |
| mechanical | gpt-6.1-sol | 3 | - | - | 2026-11-18 |
| builder | claude-opus-5-5 | 1 | - | - | 2026-11-18 |
| builder | gpt-6.2-sol | 2 | - | - | 2026-11-18 |
| builder | gpt-6.1-sol | 3 | - | - | 2026-11-18 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | - | 2026-11-18 |
| cheap | z-ai/glm-5.3-flash | 2 | - | - | 2026-11-18 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | - | 2026-11-18 |
| batch | gpt-6.2-sol | 1 | - | - | 2026-11-18 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-18 |
| batch | gpt-6.1-sol | 3 | 1.0 | 0.867 | 2026-11-18 |
| writing | claude-opus-5-5 | 1 | - | - | 2026-11-18 |
| ideation | claude-opus-5-5 | 1 | 1.0 | 0.342 | 2026-11-18 |
| ideation | gpt-6.2-astra | 2 | - | - | 2026-11-18 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | - | 2026-11-18 |
| ideation | claude-fable-5-2 | 4 | 1.0 | 0.741 | 2026-11-18 |
| ideation | gpt-6-astra | 5 | - | - | 2026-11-18 |
| design | claude-opus-5-5 | 1 | - | - | 2026-11-18 |
| design | claude-fable-5-2 | 2 | 1.0 | 0.438 | 2026-11-18 |
| judge | claude-opus-5-5 | 1 | - | - | 2026-11-18 |
| judge | gpt-6.2-astra | 2 | - | - | 2026-11-18 |
| judge | claude-fable-5-2 | 3 | 0.0 | 0.0 | 2026-11-18 |
| judge | gpt-6.2-sol | 4 | - | - | 2026-11-18 |
| judge | gpt-6-astra | 5 | - | - | 2026-11-18 |
| judge | gpt-6.1-sol | 6 | - | - | 2026-11-18 |
| taste | claude-opus-5-5 | 1 | - | - | 2026-11-19 |
| taste | claude-fable-5-2 | 2 | - | - | 2026-11-19 |
| review | claude-opus-5-5 | 1 | 1.0 | 0.566 | 2026-11-19 |
| review | gpt-6.2-astra | 2 | - | - | 2026-11-19 |
| review | claude-fable-5-2 | 3 | - | - | 2026-11-19 |
| review | gpt-6.2-sol | 4 | - | - | 2026-11-19 |
| review | gpt-5.6-sol | 5 | - | - | 2026-11-19 |
| review | moonshotai/kimi-k3.1-pro | 6 | - | - | 2026-11-19 |
| review | claude-sonnet-5-5 | 7 | - | - | 2026-11-19 |
| review | gpt-6-astra | 8 | - | - | 2026-11-19 |
| review | gpt-6.1-sol | 9 | - | - | 2026-11-19 |
| review | google/gemini-4-argon | - | - | - | 2026-11-19 |
| review | google/gemini-4-hydrogen | - | - | - | 2026-11-19 |
| mechanical | gpt-6.2-sol | 1 | - | - | 2026-11-19 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-19 |
| mechanical | gpt-6.1-sol | 3 | - | - | 2026-11-19 |
| builder | claude-opus-5-5 | 1 | - | - | 2026-11-19 |
| builder | gpt-6.2-sol | 2 | - | - | 2026-11-19 |
| builder | gpt-6.1-sol | 3 | - | - | 2026-11-19 |
| cheap | deepseek/deepseek-v4.1-flash-1017 | 1 | - | - | 2026-11-19 |
| cheap | z-ai/glm-5.3-flash | 2 | - | - | 2026-11-19 |
| biology | moonshotai/kimi-k3.1-pro | 1 | - | - | 2026-11-19 |
| batch | gpt-6.2-sol | 1 | - | - | 2026-11-19 |
| batch | deepseek/deepseek-v4.1-flash-1017 | 2 | - | - | 2026-11-19 |
| batch | gpt-6.1-sol | 3 | 1.0 | 0.867 | 2026-11-19 |
| writing | claude-opus-5-5 | 1 | - | - | 2026-11-19 |
| ideation | claude-opus-5-5 | 1 | 1.0 | 0.342 | 2026-11-19 |
| ideation | gpt-6.2-astra | 2 | - | - | 2026-11-19 |
| ideation | moonshotai/kimi-k3.1-pro | 3 | - | - | 2026-11-19 |
| ideation | claude-fable-5-2 | 4 | 1.0 | 0.741 | 2026-11-19 |
| ideation | gpt-6-astra | 5 | - | - | 2026-11-19 |
| design | claude-opus-5-5 | 1 | - | - | 2026-11-19 |
| design | claude-fable-5-2 | 2 | 1.0 | 0.438 | 2026-11-19 |
| judge | claude-opus-5-5 | 1 | - | - | 2026-11-19 |
| judge | gpt-6.2-astra | 2 | - | - | 2026-11-19 |
| judge | claude-fable-5-2 | 3 | 0.0 | 0.0 | 2026-11-19 |
| judge | gpt-6.2-sol | 4 | - | - | 2026-11-19 |
| judge | gpt-6-astra | 5 | - | - | 2026-11-19 |
| judge | gpt-6.1-sol | 6 | - | - | 2026-11-19 |

</details>

## Recorded observation scores

Historical 0–4 labels; these are not the pass rates above.

| Role | Model | Scores | Date |
|---|---|---|---|
| batch | gpt-6.1-sol | 0, 0, 4, 4, 4, 4 | 2026-10-19 |
| batch | gpt-6.1-sol | 4, 4, 4 | 2026-10-20 |
| batch | gpt-6.1-sol | 4, 4, 4, 4 | 2026-10-22 |
| batch | gpt-6.1-sol | 0, 0, 0 | 2026-10-25 |
| batch | gpt-6.1-sol | 0, 4 | 2026-10-26 |
| batch | gpt-6.1-sol | 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 4, 4, 4 | 2026-10-30 |
| batch | gpt-6.1-sol | 4, 4, 4 | 2026-10-31 |
| batch | gpt-6.1-sol | 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-01 |
| batch | gpt-6.1-sol | 0, 0, 0, 0, 0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-02 |
| batch | gpt-6.1-sol | 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-03 |
| builder | claude-opus-5-5 | 4 | 2026-10-15 |
| builder | deepseek/deepseek-v4.1-flash-1017 | 1, 2 | 2026-10-25 |
| builder | gpt-6.1-sol | 2, 3, 4 | 2026-10-25 |
| ideation | claude-opus-5-5 | 0, 0, 0, 0, 0, 0, 0, 4, 4, 4, 4, 4, 4, 4 | 2026-11-02 |
| ideation | gpt-6-astra | 0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-02 |
| mechanical | deepseek/deepseek-v4.1-flash-1017 | 3, 4, 4 | 2026-10-25 |
| mechanical | gpt-6.1-sol | 4 | 2026-10-25 |
| review | gpt-6-astra | 3 | 2026-10-25 |
| review | gpt-6-astra | 4 | 2026-11-02 |
| taste | claude-opus-5-5 | 0, 0, 4, 4 | 2026-11-02 |
| taste | claude-opus-5-5 | 0, 0 | 2026-11-03 |
| taste | deepseek/deepseek-v4.1-flash-1017 | 1 | 2026-10-25 |
| taste | gpt-6.1-sol | 1 | 2026-10-25 |
| writing | claude-opus-5-5 | 4, 4, 4, 4 | 2026-11-02 |
| judge | gpt-6-astra | 4, 4, 4, 4, 4, 4 | 2026-11-17 |
| judge | gpt-6.1-sol | 0, 4, 4, 4, 4, 4 | 2026-11-17 |
| judge | gpt-6.2-astra | 4, 4, 4, 4, 4, 4 | 2026-11-17 |
| review | gpt-6-astra | 0, 0, 4, 4, 4 | 2026-11-17 |
| review | gpt-6.1-sol | 0, 4, 4, 4, 4 | 2026-11-17 |
| review | gpt-6.2-astra | 4, 4, 4, 4, 4 | 2026-11-17 |
| review | gemini-3.8-flash-high | 0 | 2026-11-23 |
| review | gemini-3.8-flash-low | 0 | 2026-11-23 |
| review | gemini-3.8-flash-medium | 0 | 2026-11-23 |
| review | gemini-4-argon-medium | 0 | 2026-11-23 |
| review | gemini-4-hydrogen-medium | 0 | 2026-11-23 |
| review | gemini-4-neon-medium | 0 | 2026-11-23 |
| review | google/gemini-4-hydrogen | 0, 0 | 2026-11-23 |
| review | claude-sonnet-5-5 | 0 | 2026-11-23 |
| batch | claude-sonnet-5-5 | 2, 4 | 2026-11-20 |
| batch | claude-sonnet-5-5 | 4, 4 | 2026-11-22 |
| batch | gemini-4-argon-medium | 4 | 2026-11-20 |
| batch | gemini-4-carbon-high | 4, 4, 4, 4 | 2026-11-25 |
| batch | gemini-4-carbon-high | 2, 2, 2, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-26 |
| batch | gemini-4-carbon-high | 0, 2 | 2026-11-27 |
| batch | gemini-4-hydrogen-high | 0, 0, 0, 0, 0, 4, 4 | 2026-11-23 |
| batch | gemini-4-hydrogen-high | 0, 0, 0, 0, 0, 0 | 2026-11-24 |
| batch | gemini-4-hydrogen-high | 0, 0, 0 | 2026-11-25 |
| batch | gemini-4-hydrogen-medium | 0, 2, 2, 4, 4 | 2026-11-20 |
| batch | gemini-4-hydrogen-medium | 0, 0, 0, 0, 0, 0, 0 | 2026-11-22 |
| batch | gemini-4-neon-high | 4, 4, 4, 4, 4 | 2026-11-25 |
| batch | gemini-4-neon-high | 0, 0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-26 |
| batch | gemini-4-neon-high | 0, 0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-27 |
| batch | gemini-4-neon-high | 2, 2 | 2026-11-28 |
| batch | gpt-6.1-sol | 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-04 |
| batch | gpt-6.1-sol | 4, 4 | 2026-11-05 |
| batch | gpt-6.1-sol | 2, 4, 4, 4, 4, 4 | 2026-11-26 |
| batch | gpt-6.2-astra | 2, 4, 4, 4, 4, 4 | 2026-11-20 |
| batch | gpt-6.2-astra | 4 | 2026-11-22 |
| batch | gpt-6.2-astra | 4, 4 | 2026-11-23 |
| batch | gpt-6.2-astra | 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-26 |
| batch | gpt-6.2-sol | 0, 4, 4 | 2026-11-20 |
| batch | gpt-6.2-sol | 0, 0 | 2026-11-21 |
| batch | gpt-6.2-sol | 0, 0, 0, 2, 2, 4, 4 | 2026-11-22 |
| batch | gpt-6.2-sol | 2, 4, 4, 4, 4, 4 | 2026-11-23 |
| batch | gpt-6.2-sol | 4, 4, 4, 4, 4 | 2026-11-24 |
| batch | gpt-6.2-sol | 0, 0, 0, 0, 0, 0, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-25 |
| batch | gpt-6.2-sol | 2, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-26 |
| batch | gpt-6.2-sol | 2, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-27 |
| builder | claude-opus-5-5 | 2, 4, 4, 4, 4, 4, 4, 4 | 2026-11-20 |
| builder | claude-opus-5-5 | 4 | 2026-11-21 |
| builder | claude-opus-5-5 | 4, 4, 4, 4, 4, 4 | 2026-11-22 |
| builder | claude-opus-5-5 | 2, 4 | 2026-11-23 |
| builder | claude-opus-5-5 | 4 | 2026-11-25 |
| builder | claude-opus-5-5 | 4, 4, 4 | 2026-11-26 |
| builder | claude-opus-5-5 | 2, 2, 4, 4, 4, 4, 4, 4 | 2026-11-27 |
| builder | claude-sonnet-5-5 | 2, 4, 4 | 2026-11-20 |
| builder | claude-sonnet-5-5 | 2 | 2026-11-27 |
| builder | gemini-4-argon-medium | 4 | 2026-11-20 |
| builder | gemini-4-hydrogen-low | 2 | 2026-11-19 |
| builder | gemini-4-hydrogen-low | 2 | 2026-11-20 |
| builder | gemini-4-neon-high | 4, 4, 4, 4, 4 | 2026-11-23 |
| builder | gemini-4-neon-high | 4 | 2026-11-24 |
| builder | gemini-4-neon-high | 0, 4, 4, 4, 4, 4, 4, 4 | 2026-11-25 |
| builder | gemini-4-neon-high | 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-26 |
| builder | gemini-4-neon-high | 2 | 2026-11-27 |
| builder | gemini-4-neon-medium | 4 | 2026-11-19 |
| builder | gemini-4-neon-medium | 4, 4, 4, 4 | 2026-11-20 |
| builder | gemini-4-neon-medium | 4 | 2026-11-21 |
| builder | gemini-4-neon-medium | 4, 4, 4, 4, 4, 4 | 2026-11-22 |
| builder | gpt-6.2-astra | 4 | 2026-11-20 |
| builder | gpt-6.2-sol | 0 | 2026-11-19 |
| builder | gpt-6.2-sol | 2, 4 | 2026-11-20 |
| builder | gpt-6.2-sol | 4 | 2026-11-21 |
| builder | gpt-6.2-sol | 2, 4 | 2026-11-22 |
| builder | gpt-6.2-sol | 2, 4, 4, 4, 4, 4, 4 | 2026-11-23 |
| builder | gpt-6.2-sol | 4 | 2026-11-24 |
| builder | gpt-6.2-sol | 0, 4, 4, 4, 4, 4 | 2026-11-25 |
| builder | gpt-6.2-sol | 4, 4, 4, 4 | 2026-11-26 |
| builder | gpt-6.2-sol | 0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-27 |
| design | claude-fable-5-2 | 4, 4 | 2026-11-13 |
| design | claude-fable-5-2 | 4 | 2026-11-14 |
| ideation | claude-fable-5-2 | 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-13 |
| ideation | claude-fable-5-2 | 4 | 2026-11-14 |
| ideation | claude-opus-5-5 | 4, 4 | 2026-11-16 |
| judge | claude-fable-5-2 | 0, 0 | 2026-11-13 |
| judge | gpt-6.2-astra | 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-26 |
| review | claude-opus-5-5 | 4 | 2026-11-09 |
| review | claude-opus-5-5 | 4, 4 | 2026-11-17 |
| review | claude-opus-5-5 | 4, 4 | 2026-11-18 |
| review | claude-opus-5-5 | 4, 4, 4 | 2026-11-20 |
| review | claude-opus-5-5 | 2, 2, 4, 4, 4 | 2026-11-26 |
| review | claude-opus-5-5 | 4, 4, 4, 4, 4, 4 | 2026-11-27 |
| review | claude-sonnet-5-5 | 4, 4 | 2026-11-19 |
| review | claude-sonnet-5-5 | 0, 4, 4, 4 | 2026-11-20 |
| review | claude-sonnet-5-5 | 4, 4 | 2026-11-25 |
| review | gemini-3.8-flash-high | 4 | 2026-11-19 |
| review | gemini-3.8-flash-high | 4 | 2026-11-25 |
| review | gemini-3.8-flash-low | 4 | 2026-11-19 |
| review | gemini-3.8-flash-low | 4 | 2026-11-25 |
| review | gemini-3.8-flash-medium | 4 | 2026-11-19 |
| review | gemini-3.8-flash-medium | 4 | 2026-11-25 |
| review | gemini-4-argon-low | 4 | 2026-11-19 |
| review | gemini-4-argon-medium | 4, 4 | 2026-11-19 |
| review | gemini-4-argon-medium | 4, 4, 4, 4 | 2026-11-20 |
| review | gemini-4-argon-medium | 4 | 2026-11-25 |
| review | gemini-4-carbon-high | 4 | 2026-11-25 |
| review | gemini-4-carbon-high | 0, 0, 2, 4, 4, 4, 4, 4 | 2026-11-26 |
| review | gemini-4-carbon-high | 0, 0 | 2026-11-27 |
| review | gemini-4-hydrogen-medium | 4 | 2026-11-19 |
| review | gemini-4-hydrogen-medium | 4 | 2026-11-25 |
| review | gemini-4-neon-high | 4 | 2026-11-24 |
| review | gemini-4-neon-high | 4, 4, 4, 4 | 2026-11-25 |
| review | gemini-4-neon-high | 4, 4, 4, 4, 4 | 2026-11-26 |
| review | gemini-4-neon-medium | 4 | 2026-11-19 |
| review | gemini-4-neon-medium | 4 | 2026-11-25 |
| review | google/gemini-4-argon | 4 | 2026-11-10 |
| review | google/gemini-4-argon | 0 | 2026-11-23 |
| review | google/gemini-4-hydrogen | 0, 4 | 2026-11-16 |
| review | google/gemini-4-hydrogen | 4, 4 | 2026-11-25 |
| review | gpt-5.6-sol | 0, 4, 4 | 2026-11-10 |
| review | gpt-6.2-astra | 4 | 2026-11-19 |
| review | gpt-6.2-astra | 4, 4, 4, 4, 4 | 2026-11-20 |
| review | gpt-6.2-astra | 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-22 |
| review | gpt-6.2-astra | 4, 4 | 2026-11-23 |
| review | gpt-6.2-astra | 4 | 2026-11-24 |
| review | gpt-6.2-astra | 2, 4, 4, 4, 4, 4, 4 | 2026-11-25 |
| review | gpt-6.2-astra | 0, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-26 |
| review | gpt-6.2-astra | 4, 4 | 2026-11-27 |
| review | moonshotai/kimi-k3.1-pro | 4, 4 | 2026-11-10 |
| review | moonshotai/kimi-k3.1-pro | 0 | 2026-11-27 |

Ranking method and limits: [leaderboard/README.md](leaderboard/README.md).
