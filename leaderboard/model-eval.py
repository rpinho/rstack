#!/usr/bin/env python3
"""Validate and summarize the private, append-only field-evaluation ledger. No API calls.

Usage: python3 scripts/model-eval.py [path/to/ledger.jsonl]
Scores describe selected cases, never a controlled model benchmark or personal vote.
"""
import os
import collections
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'harness'))
from model_slugs import canon


def load_rows(path):
    rows, seen, by_id, retired = [], set(), {}, set()
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        required = {"id", "case", "date", "model", "effort", "route", "role",
                    "task_family", "layer", "score", "cost_usd", "evidence", "note"}
        if required - row.keys():
            raise ValueError(f"line {line_no}: missing {sorted(required - row.keys())}")
        for field in ("id", "case", "date", "model", "effort", "route", "role", "task_family", "note"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"line {line_no}: {field} must be a nonempty string")
        if row["id"] in seen:
            raise ValueError(f"line {line_no}: duplicate observation id {row['id']}")
        seen.add(row["id"])
        if (not isinstance(row["evidence"], list) or not row["evidence"]
                or any(not isinstance(e, str) or not e.strip() for e in row["evidence"])):
            raise ValueError(f"line {line_no}: evidence required")
        score = row["score"]
        if score is not None and (type(score) is not int or score not in range(5)):
            raise ValueError(f"line {line_no}: score must be null or integer 0..4")
        if row["layer"] not in {"model", "workflow", "route", "infrastructure"}:
            raise ValueError(f"line {line_no}: unknown failure layer")
        cost = row["cost_usd"]
        if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
            raise ValueError(f"line {line_no}: cost must be null or finite nonnegative USD")
        estimate = row.get("reported_list_cost_usd")
        if estimate is not None and (type(estimate) not in (int, float) or not math.isfinite(estimate) or estimate < 0):
            raise ValueError(f"line {line_no}: list-price estimate must be null or finite nonnegative USD")
        if "supersedes" in row:
            old = row["supersedes"]
            if not isinstance(old, str) or old not in by_id or old in retired:
                raise ValueError(f"line {line_no}: supersedes must identify an earlier active observation")
            if by_id[old]["case"] != row["case"]:
                raise ValueError(f"line {line_no}: supersession must retain case identity")
            retired.add(old)
        row['model'] = canon(row['model']) or row['model']
        rows.append(row)
        by_id[row["id"]] = row
    return [r for r in rows if r["id"] not in retired]


def report(rows):
    groups = collections.defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in ("model", "effort", "route", "role", "task_family", "layer"))
        groups[key].append(row)
    print("Selected-case scorecard; 0..4 anchored outcome scores, not a universal ranking.\n")
    print("| Model / effort | Route / role / task / layer | Cases | Scores | API-reported USD (coverage) | List-price estimate USD (coverage) |")
    print("|---|---|---:|---|---|---|")
    for key, items in sorted(groups.items()):
        model, effort, route, role, task, layer = key
        scores = [str(r["score"]) for r in items if r["score"] is not None]
        costs = [r["cost_usd"] for r in items if r["cost_usd"] is not None]
        money = f"${sum(costs):.6f} ({len(costs)}/{len(items)})" if costs else "unknown (0/" + str(len(items)) + ")"
        estimates = [r["reported_list_cost_usd"] for r in items if r.get("reported_list_cost_usd") is not None]
        list_money = f"${sum(estimates):.6f} ({len(estimates)}/{len(items)})" if estimates else "none (0/" + str(len(items)) + ")"
        print(f"| {model} / {effort} | {route} / {role} / {task} / {layer} | {len(set(r['case'] for r in items))} | {', '.join(scores) or 'unscored'} | {money} | {list_money} |")
    print("\nUnknown costs remain unknown; route/infrastructure cases are separate from model capability.")
    estimates = [r["reported_list_cost_usd"] for r in rows if r.get("reported_list_cost_usd") is not None]
    if estimates:
        print(f"CLI list-price estimates: ${sum(estimates):.7f} across {len(estimates)} observations; excluded from API-reported USD above.")


if __name__ == "__main__":
    default = pathlib.Path(os.environ.get("MODEL_LEDGER", "evaluations.jsonl"))
    try:
        report(load_rows(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else default))
    except (ValueError, OSError, TypeError) as exc:
        sys.exit(str(exc))
