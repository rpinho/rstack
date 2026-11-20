#!/usr/bin/env python3
"""Pooling noisy sources: the plain mean, inverse-variance and Stouffer-z, the standard baselines.

11-20, Illumina CellularAI, winner of the Arc Virtual Cell Challenge 2026 (Jaganathan thread,
https://x.com/kjaganatha/status/2123584965195489604). Their cumulative ablation on 50 cell lines,
as gain over the plain mean across lines: centering +10%, then inverse-variance weighting +17%,
then Stouffer-z (favouring changes consistent across lines) +75%, the biggest of five steps.
Both are textbook meta-analysis. Anywhere a lane pools noisy per-source estimates (papers, runs, judges, cell lines),
run these before anything clever:

    mean             unweighted mean of the effects
    inverse_variance sum(e / se^2) / sum(1 / se^2)
    stouffer         sum(w * z) / sqrt(sum(w^2)), z = e / se (w = 1 by default)

Stouffer needs a signed effect and a standard error per source. A bare pass/fail vote has neither,
so turn it into a score with an uncertainty first or keep the vote count; do not feed it 0/1.
"""
import argparse, json, math, sys


def _finite(xs, name):
    xs = [float(x) for x in xs]
    if not xs or not all(math.isfinite(x) for x in xs):
        raise ValueError(f'{name} must be one or more finite numbers')
    return xs


def _ses(effects, ses):
    e, s = _finite(effects, 'effects'), _finite(ses, 'standard errors')
    if len(e) != len(s):
        raise ValueError('one standard error per effect')
    if not all(x > 0 for x in s):
        raise ValueError('standard errors must be > 0')
    return e, s


def mean(effects):
    e = _finite(effects, 'effects')
    return sum(e) / len(e)


def inverse_variance(effects, ses):
    e, s = _ses(effects, ses)
    w = [1 / x ** 2 for x in s]
    return sum(wi * ei for wi, ei in zip(w, e)) / sum(w)


def stouffer(effects, ses, weights=None):
    e, s = _ses(effects, ses)
    w = [1.0] * len(e) if weights is None else _finite(weights, 'weights')
    if len(w) != len(e):
        raise ValueError('one weight per effect')
    norm = math.sqrt(sum(x * x for x in w))
    if norm == 0:
        raise ValueError('weights must not all be zero')
    return sum(wi * ei / si for wi, ei, si in zip(w, e, s)) / norm


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--effect', type=float, action='append', required=True, help='one per source; repeat')
    p.add_argument('--se', type=float, action='append', required=True, help='its standard error; repeat')
    p.add_argument('--weight', type=float, action='append', help='optional Stouffer weight per source')
    a = p.parse_args(argv)
    try:
        out = dict(n=len(a.effect), mean=mean(a.effect), inverse_variance=inverse_variance(a.effect, a.se),
                   stouffer_z=stouffer(a.effect, a.se, a.weight))
    except ValueError as e:
        print(json.dumps({'error': str(e)}), file=sys.stderr)
        return 2
    print(json.dumps({k: round(v, 6) if isinstance(v, float) else v for k, v in out.items()}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
