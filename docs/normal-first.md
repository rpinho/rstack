# Normal first

> **Please let's do normal things unless they don't work.**

Anthropic's life-sciences team wrote this to Claude while solving a vault-particle structure ([2026-11-04](https://www.anthropic.com/research/investigating-vault-particles-with-claude)). Early in cryo-EM processing Claude skipped a standard step and produced a map blended with its own mirror image. Earlier, a protocol it wrote cost the team two weeks. Agents improvise. In a field you don't know, improvisation costs you the most and is the hardest to catch.

The rule has three parts, and each one is enforced in code, not only stated:

1. **Standard method first.** Run the field's standard method with its standard steps. Deviate only after it has run and failed, and record where it failed. `harness/tools/result_lint.py` requires a `Standard method:` line and a `Deviations:` line that is `none` or says `standard failed: <where>`.
2. **Trivial predictor and simple baseline before any predictive claim.** [Ellington, Wang, Addagudi and Cole (2026)](https://arxiv.org/abs/2610.40700) had one Claude Opus 5 attempt (CPU only, 30 minutes, no pretrained weights) build simple baselines for 36 deep-learning papers in Nature, Science and Cell journals. The baselines recovered a median 95.5% of the published gain over a trivial predictor, and matched or beat 12 of the 36 methods. `harness/tools/sbs.py` computes their simple baseline strength, SBS = (M_simple − M_trivial) / (M_method − M_trivial). `result-lint` requires `BASELINES.json` whenever a claim reports a predictive metric, and recomputes the SBS. Each metric on the `Ours:` line needs its own row, and a method that does not beat the trivial (mean) predictor on a metric fails: in the [Arc Virtual Cell Challenge 2026](https://arcinstitute.org/news/virtual-cell-challenge-2026-wrap-up) over 9 in 10 final entries beat the mean on PDS, but only about 4 in 10 on MSE and 1 in 3 on Jaccard. A row may give `noise`, the run-to-run spread of the method at a fixed step; a gap over the simple baseline no larger than that is printed as noise. Where you can, score on two or three independent benchmarks, one row each with a `harness` name, and keep a change only if it gains on all of them: that is how Illumina's CellularAI won the [Virtual Cell Challenge 2026](https://x.com/kjaganatha/status/2123584965195489604) (VCC2025, Replogle 2022 and a held-out set). A row where the method does not beat simple is printed as a note.
   When you pool noisy sources (papers, runs, judges, cell lines), the baselines are the plain mean, inverse-variance weighting and Stouffer-z, `harness/tools/pool.py`. In CellularAI's ablation at 50 cell lines Stouffer-z was the biggest single step, taking the gain over the mean from +17% to +75%. It needs a signed effect and a standard error per source, so a bare pass/fail vote does not qualify.
3. **Did you find something new? Yes or no.** The first line of every claim is `NEW: yes` or `NEW: no`. A `yes` cites the printed number or open problem it beats or settles. `NEW: no` is an honest answer, and `result-lint --new-only` keeps those claims away from the referee.

```sh
python3 harness/tools/sbs.py --trivial 0.5 --simple 0.84 --method 0.8556 --metric AUROC
python3 harness/tools/result_lint.py path/to/claim_dir [--new-only]
python3 harness/tools/pool.py --effect 0.4 --se 0.1 --effect 0.3 --se 0.2
```

Tests: `tests/test_normal_first.py`.
