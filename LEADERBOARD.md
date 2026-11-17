# Model leaderboard

A dated routing snapshot from selected local harness outcomes. Scores are held-outcome rates and 95% Wilson lower bounds. A dash means unscored; starting orders include operator seed choices. This is not a universal benchmark.

## Matched replay and easy plants (11-17)

Selected local replay cases and selected synthetic calibration tasks, not a general ranking. All three OpenAI models reran the same nine historical tasks; judge uses the shared PDF-extraction repair cohort. Operational failures are not quality zeros. The easy plants are a separate six-task cohort, not additional replay cases.

| Entry | Completed replay /9 | Review batch catches /2 | Judge historical agreement /3 | Ideation CLI completions /3 | Easy plants /24 |
|---|---:|---:|---:|---:|---:|
| openai/gpt-6.2-astra | 6 | 2 | 3 | 0 | 24 |
| openai/gpt-6.1-sol | 9 | 1 | 2 | 3 | 24 |
| openai/gpt-6-astra | 8 | 0 | 3 | 3 | 24 |

The inherited review label rule is maximized by always returning BLOCKED; all three historical judge references conditionally forward. Neither measure establishes general correctness. One review case is excluded for an inherited key mismatch. Ideation quality is unresolved for every model; CLI completion measures bounded delivery only. All three models tie on the six easy plants (three review, three judge), so that cohort cannot separate them. Easy-plant mean score /4: trivial 0.3333, simple linear baseline 0.6667, each model 4.0000; SBS 0.090909. Historical review means /4: trivial 4, simple 0, GPT-6.2 Astra 4 / Sol 2 / GPT-6 Astra 0. Historical judge means /4: trivial 4, simple 0, respective model means 4 / 2.6667 / 4; SBS is undefined because no method beats the trivial controls. These baseline scores apply only to their original cohorts.

## Harder planted errors (laptop, 11-17)

Selected synthetic calibration tasks, not a general ranking. Source: `laptop-public-plants-hard`, 2026-11-17. Six entries ran the same 32 tasks (19 review, 13 judge); each row is the mean of two repetitions, not two independent tasks. The laptop reports the same API defaults, a 4,000-token output ceiling, and empty answers scored 0.

| Entry | Total /128 | Review /76 | Judge /52 | Empty-answer count |
|---|---:|---:|---:|---|
| openai/gpt-6.2-astra | 128 | 76 | 52 | unavailable |
| anthropic/claude-opus-5.5 | 123 | 76 | 47 | unavailable |
| anthropic/claude-fable-5.2 | 120 | 76 | 44 | unavailable |
| google/gemini-4-argon | 115 | 76 | 39 | unavailable |
| google/gemini-4-carbon | 98 | 62 | 36 | unavailable |
| google/gemini-4-hydrogen † | 96 | 60 | 36 | unavailable |

† Hydrogen includes a supplied review score of −2, outside the 0–4 rubric. Its sums are shown exactly as supplied, without clamping, dropping or repairing the row. Empty-answer counts are unavailable: the seven-field export has neither answer text nor an empty-answer flag, and zero scores do not distinguish empty from incorrect answers. The prompts, keys, individual repetitions and raw answers were not supplied, so scoring, API settings and emptiness cannot be independently checked here.

Review reaches the ceiling for GPT-6.2 Astra, Opus, Fable and Argon. Judge separates them: GPT-6.2 Astra leads Opus by 5 points on 13 paired judge tasks (two repetitions averaged per task), with the entire margin on two tasks. These are descriptive calibration sums; no general-role superiority follows. No trivial or simple baseline on these hard tasks was supplied; the score-only export cannot provide them, so hard-task SBS is unavailable.

## v3.1 calibration (laptop, 11-17)

Selected synthetic calibration tasks, not a general ranking. Source: `laptop-public-plants-v3.1`, 2026-11-17. Eleven entries share 48 public synthetic tasks: 29 review and 19 judge. Scores are floored at 0 on a 0–4 scale. Companion event counts cover 96 replies per entry; replies are not 96 independent tasks. v3.1 replaces the unused v3 (20261117-1539); no v3 scores are included. The earlier hard-plants cohort is retained separately.

| Entry | Total /192 | Review /116 | Judge /76 | False alarms | No-answers | Empty finals | Truncated finals | Provider errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| anthropic/claude-fable-5.2 | 192 | 116 | 76 | 0 | 0 | 0 | 0 | 0 |
| google/gemini-4-argon | 192 | 116 | 76 | 0 | 0 | 0 | 0 | 0 |
| google/gemini-4-hydrogen | 192 | 116 | 76 | 0 | 0 | 0 | 0 | 0 |
| openai/gpt-6.1-sol | 192 | 116 | 76 | 0 | 0 | 0 | 0 | 0 |
| openai/gpt-6.2-astra | 192 | 116 | 76 | 0 | 0 | 0 | 0 | 0 |
| anthropic/claude-opus-5.5 | 191 | 116 | 75 | 0 | 0 | 0 | 0 | 0 |
| anthropic/claude-haiku-5.5 | 187 | 112 | 75 | 2 | 0 | 0 | 0 | 0 |
| moonshotai/kimi-k3.1-pro | 186 | 113 | 73 | 1 | 0 | 0 | 0 | 0 |
| anthropic/claude-sonnet-5.5 | 184 | 109 | 75 | 3 | 0 | 0 | 0 | 0 |
| google/gemini-4-carbon | 176 | 104 | 72 | 0 | 8 | 8 | 6 | 2 |
| z-ai/glm-5.3-flash | 173 | 109 | 64 | 2 | 3 | 3 | 2 | 1 |

Five entries tie at the 192 ceiling: Fable, Argon, Hydrogen, Sol and GPT-6.2 Astra; all five report zero false alarms and no-answers. Opus is one point behind overall, tied at the review ceiling and one point behind on judge (hard-s04). Six entries tie at 116 on review. For review selection, count false alarms against Kimi (1), Sonnet (3), Haiku (2) and GLM (2); Opus and every ceiling entry report 0. These event counts cover both roles; a per-role event breakdown is unavailable. They are not added to the supplied score as a new metric.

The supplied false_alarm_replies equal false_alarms for every entry. Wrong_answers is 1 for GLM and 0 for the other entries. Empty/truncated/provider-error/no-answer categories may overlap and must not be summed as disjoint failures. Counts are laptop-reported event labels, not inferred from zero scores. Raw replies, prompts, keys and per-reply outcomes are absent, so answer grading and the event labels cannot be independently checked or reconciled reply by reply here.

File checks found no mismatches: 528 seven-field score rows, 11 eleven-field count rows, identical unique task/role sets per entry, all scores within 0–4, and maxima 48×4=192, 29×4=116, 19×4=76. Each total equals its review plus judge sum. The count file contains no independent per-entry score totals to cross-check. No same-task trivial or simple baseline results were supplied; this score/count export cannot provide them, so v3.1 SBS is unavailable. These are descriptive calibration sums, with no predictive-baseline gain or general-role superiority claim.

## Dated routing snapshots

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

## Recorded observation scores

Selected local labels on a 0–4 scale, including proxy and operational outcomes. Repeated scores are retained; no task identifiers or text are exported. These labels are not matched benchmark trials.

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
| batch | gpt-6.1-sol | 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-04 |
| batch | gpt-6.1-sol | 4, 4 | 2026-11-05 |
| design | claude-fable-5-2 | 4, 4 | 2026-11-13 |
| design | claude-fable-5-2 | 4 | 2026-11-14 |
| ideation | claude-fable-5-2 | 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 | 2026-11-13 |
| ideation | claude-fable-5-2 | 4 | 2026-11-14 |
| ideation | claude-opus-5-5 | 4, 4 | 2026-11-16 |
| judge | claude-fable-5-2 | 0, 0 | 2026-11-13 |
| judge | gpt-6-astra | 4, 4, 4, 4, 4, 4 | 2026-11-17 |
| judge | gpt-6.1-sol | 0, 4, 4, 4, 4, 4 | 2026-11-17 |
| judge | gpt-6.2-astra | 4, 4, 4, 4, 4, 4 | 2026-11-17 |
| review | claude-opus-5-5 | 4 | 2026-11-09 |
| review | google/gemini-4-argon | 4 | 2026-11-10 |
| review | google/gemini-4-hydrogen | 0, 4 | 2026-11-16 |
| review | gpt-5.6-sol | 0, 4, 4 | 2026-11-10 |
| review | gpt-6-astra | 0, 0, 4, 4, 4 | 2026-11-17 |
| review | gpt-6.1-sol | 0, 4, 4, 4, 4 | 2026-11-17 |
| review | gpt-6.2-astra | 4, 4, 4, 4, 4 | 2026-11-17 |
| review | moonshotai/kimi-k3.1-pro | 4, 4 | 2026-11-10 |

Ranking method and limits: [leaderboard/README.md](leaderboard/README.md).
