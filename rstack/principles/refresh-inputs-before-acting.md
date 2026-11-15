# Refresh inputs before acting

**The rule.** Re-read any inventory, status board, device or account list, or cached state from
its source before acting on it, when it is older than a day or older than the last change to what
it describes.

**Why.** A stale snapshot looks like a bug and sends the next fix at the wrong target. That is the
laptop's lesson. The Mini hit the same
shape with clones: an audit found public repos, retros and live code that had each drifted from
where they came from, with nothing failed, only aged.

**Enforced by**
- [repo-freshness](../tools/repo-freshness): every night, every configured host's clones, public
  releases and backups are re-read from their source and compared, so the repo state an agent acts
  on is never more than a day old without someone being told.
- [leaderboard-freshness](../tools/leaderboard-freshness): flags a model leaderboard whose newest
  table is old or that is missing models in recent use, since model roles are read from it.

**Not enforced yet** for other cached state: status boards, account lists and device inventories
are still prose. The cheap version is a timestamp next to every snapshot and a check that refuses
to act on one older than its source's last change.

Related: [a failed read is never all clear](a-failed-read-is-not-all-clear.md).
