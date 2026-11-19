"""Vendored acted() from the M4's ~/.local/share/x-engage/bookmark_queue.py (11-19 fixes), for CI.

The real file stays in the M4's local-only x-engage repo: it reads the private bookmark store and
names the accounts the round never engages. test_x_log.py runs the same rows through this copy
everywhere, and through the real file too when X_ENGAGE_DIR names a host copy (the M4's, or the
m5's synced one). Keep this function identical to the real one; the test then compares them.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))


def acted():
    liked, replied, followed = set(), set(), set()
    try:
        for line in open(os.path.join(HERE, "log.jsonl")):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            # 11-19: x-reply-review writes target_url: null for summary rows; a None here crashed every round
            url, act = d.get("target_url") or "", d.get("action")
            if not isinstance(url, str):
                url = str(url)
            try:
                m = re.search(r"/status/(\d+)", url)
            except Exception:  # 11-19 poteto: one bad row must never crash a round
                continue
            if act == "like" and m:
                liked.add(m.group(1))
            elif act == "reply" and m:
                replied.add(m.group(1))
            elif act == "follow":
                followed.add(url.rstrip("/").split("/")[-1].lower())
    except FileNotFoundError:
        pass
    try:
        replied |= set(json.load(open(os.path.join(HERE, "replied.json"))))
    except (FileNotFoundError, ValueError):
        pass
    return liked, replied, followed
