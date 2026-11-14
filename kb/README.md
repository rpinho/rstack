# agent-kb

**A file-based, agent-maintained knowledge base you run locally.** Clone it, point a coding agent (Claude Code, Codex, ...) at it, and feed it what you read, decide and learn. The agent files each piece into the right place, keeps an index, remembers across sessions, and runs a scheduled digest, because the memory *is* the filesystem, not the model's context window.

This is a **scaffold**, not an app. No database, no account. It ships empty. What it gives you is a *system*: conventions, small scripts, git hooks and agent hooks that turn a directory of markdown into a durable, queryable second brain an agent can maintain for years. It is the persistent-agent memory layer, as a scaffold.

> The design follows the "LLM wiki" pattern (Karpathy, 2026): **the human curates sources and directs attention; the agent writes and maintains the wiki.** You don't type into a notes app. You hand the agent a podcast, a thread, a decision, and it compiles it into the knowledge graph.

What it turned out to be for, a year in: [RETRO.md](RETRO.md).

---

## Why this works (the load-bearing ideas)

1. **The filesystem is the memory.** Plain markdown and JSON on disk. Any agent, any runtime, any editor can read it; it survives model upgrades and vendor changes; you can `grep` it, `git log` it, and read it yourself.

2. **Two layers: an immutable *raw* quarantine and a compiled *wiki*.** Everything ingested lands first in `raw/`, never edited, never trusted, one file per source. The agent compiles the signal into `wiki/`, the trusted, cross-linked layer you actually read. Untrusted input can never masquerade as settled knowledge.

3. **One source fans out to many wiki pages.** The wiki is organized by topic, not by source. Route each piece to where it belongs; never dump into a catch-all.

4. **Index-first retrieval.** `index.md` is the catalog the agent reads before it searches or answers; `log.md` is the append-only audit trail; `state.md` is the one-glance list of open loops.

5. **Idempotent, resumable ingestion.** A processed ledger (`scripts/ledger.py`) makes re-running an ingest safe and cheap.

6. **Enforce with architecture, not prose.** *(new in v2)* `architecture > compiler > CI/git hook > lint > prose`. Rules written only in `AGENTS.md` get broken. Every rule that broke once was promoted to a mechanism: a git hook, an agent hook, a lint that fails the build, a runner that cannot go silent. The prose stays as the explanation.

7. **Concurrency-safe by construction.** *(stronger in v2)* Every agent session runs in its own sparse git worktree and *lands* to `main` with a fast-forward-only merge. Hooks refuse edits and commits in the main tree, so the flow is enforced, not remembered.

8. **It protects you from yourself.** The highest-value thing a second brain does isn't recall, it's **intervention**: a KB that has watched you learns your recurring failure modes and pushes back when you're about to act against your own interest (and says so just as clearly when the evidence favours the risk you've been waiting to take). Post-mortems are how it learns the patterns. See `AGENTS.md` -> "The KB as a protector".

---

## Architecture

```
            you ── paste / link / "ingest this" ──┐
                                                  ▼
  ┌─────────── session worktree (one per agent session) ───────────┐
  │  raw/ (verbatim, immutable)  ->  wiki/ (compiled, cross-linked) │
  │  index.md · log.md · state.md · memory/                         │
  │  + one line in raw/_index/day-ledger.jsonl per ingest           │
  └──────────────── land: merge main in, fast-forward main ────────┘
                                                  │
  scheduled run (own worktree, nightly):          ▼
    probe -> phase 1 ingest (orchestrator + cheap sub-agents) -> brief
          -> phase 2 write (best writer, fresh session) -> digest
          -> digest-lint (compiler) -> one repair pass -> lint again
          -> consume day-ledger -> deliver | fallback digest | failure notice
          -> land (guarded; tomorrow self-heals anything stranded)
                                                  │
  readers:  kb-server (token-gated web reader + /home)  ·  alerts dir -> phone push
```

**Enforcement map** (what keeps each rule true):

| Rule | Mechanism |
|---|---|
| One agent per working tree | `shell/kb-launcher.zsh` (worktree per session) + `.claude/hooks/guard-main-tree.sh` + pre-commit check 1 |
| `raw/` is immutable | pre-commit check 2 |
| No secrets / private records in history | pre-commit check 3 |
| Every ingest reaches the next digest | `scripts/day-ledger.py` + pre-commit check 4 + digest-lint L5 |
| Printed docs don't contradict open items | `scripts/prep-lint.py` + `scripts/print.sh` + pre-commit check 5 |
| No `git add -A` accidents | pre-commit check 6 (blast radius) + settings deny rule |
| Nothing goes out in your name unchecked | `.claude/hooks/friend-reply-gate.py` (email reply clicks need a fresh reply-lint pass or outreach approval), `voice-send-gate.py` (other browser sends need a fresh `rh voice-cuts` pass), `email-voice-gate.py` (API sends pass the voice check and an exact-byte approval); all read their paths and phrase lists from `~/.config/kb/gates.json` (`gates.example.json`) and refuse a send they cannot check |
| "Check the index before saying we never documented X" | SessionStart hook injecting a title index |
| Digest length, order, coverage, no permission-slip asks | `scripts/digest-lint.py` + repair pass |
| The digest is never silently missing | `scripts/nightly/run.sh` (EXIT trap, fallback, failure notice) |
| Failures reach a human the same day | `scripts/alert.py` (alerts dir -> digest top line + push loop) |
| A touched `state.md` item opens with its current status | `scripts/state-lint.py` + pre-commit check 7 |
| No project working detail in the files every session reloads | `scripts/context-hygiene-lint.py` (your own terms file, `KB_CONTEXT_TERMS`) + pre-commit check 8 |
| Stale or contradictory open items get fixed | `scripts/coherence.py` (weekly report) + `scripts/state-hygiene.py` (nightly, judged) |

---

## Layout

```
agent-kb/
├── AGENTS.md              canonical operating manual (start here)
├── CLAUDE.md              thin Claude Code overlay: hooks, worktree rules
├── CONVENTIONS.md         naming, routing, ingest / query / lint operations
├── index.md · log.md · state.md · goals.md
├── memory/                MEMORY.md index + one durable fact per file
├── docs/agent-operations.md  model routing, private process checks, resource guards, session recovery
├── docs/model-roles.md       which model for which job, scored from this setup's own outcomes
├── raw/                   IMMUTABLE sources (sources/<Author - @handle>/, _index/ = generated metadata)
├── wiki/<domain>/         COMPILED knowledge, by topic
├── outbox/                deliverables: digests, reports, printable pages
├── templates/             digest-pins.md (one-shot) · digest-daily.md (recurring)
├── shell/
│   └── kb-launcher.zsh    kb-claude / kb-codex (worktree per session) · kb-land
├── .githooks/pre-commit   the enforced rules (+ README with the table)
├── .claude/
│   ├── settings.json      hook wiring + deny rules
│   ├── hooks/             guard-main-tree · friend-reply-gate · voice-send-gate · email-voice-gate
│   │                      (each through _hookfail.py, a copy of rstack/hooks/_hookfail.py) · inject-title-index.sh
│   └── skills/            byte-identical mirror of .agents/skills/
├── .codex/hooks.json      same guard hook for Codex
├── .agents/skills/        ingest (+ references/) · land · postmortem
└── scripts/
    ├── ledger.py               processed-id ledger (idempotent ingestion)
    ├── day-ledger.py           intraday ledger: daytime ingests -> next digest
    ├── digest-lint.py          the digest compiler (caps, order, ledger coverage, must-mention, asks)
    ├── digest-fallback.py      deterministic no-model digest (alerts, 14-day countdown, ledger)
    ├── nightly/                run.sh · agent-run.sh (claude|codex) · build_prompt.py · models.env
    │                           prompt-ingest.md · prompt-write.md · notify.sh (your delivery seam)
    ├── alert.py                alerts dir: raise / clear / list / push-pending
    ├── coherence.py            deterministic coherence report (+ kb-coherence.sh weekly job)
    ├── state-hygiene.py        close open items a newer entry resolved (candidates -> judge -> apply)
    ├── prep-lint.py · print.sh hand-over docs: claims of absence vs open items, then print
    ├── state-lint.py           state.md openings must carry the current status (pre-commit check 7)
    ├── context-hygiene-lint.py keep working detail out of state/index/goals (pre-commit check 8)
    ├── kb-server.py            read-only, token-gated web reader with /home and a "Latest" box
    ├── kb-title-index.sh       compact page-title index (feeds the SessionStart hook)
    ├── kb-encrypted-backup.sh  encrypted snapshots to a synced folder; media excluded; counted prune
    ├── build-entity-index.py · whois.py   "do we have <author>, and how much?"
    ├── build-wiki-html.py      render the wiki to one HTML file
    ├── transcribe.py           local faster-whisper transcription
    ├── test-hooks.sh           exercises every hook branch in a throwaway repo
    └── launchd/                example LaunchAgents (nightly run, reader)
```

## Quickstart

```bash
git clone <your-fork> ~/kb && cd ~/kb
git config core.hooksPath .githooks          # turn on the enforced rules
scripts/test-hooks.sh                        # watch every hook fire once

# worktree-per-session launcher (add to ~/.zshrc)
echo 'export KB_REPO=~/kb; source ~/kb/shell/kb-launcher.zsh' >> ~/.zshrc && exec zsh
kb-claude                                    # or: kb-codex
```

Then, to the agent:

> "Read AGENTS.md. Here's a podcast I want to remember: <url>. Ingest it."

It fetches the source, saves the raw transcript under `raw/sources/`, compiles the signal into `wiki/`, updates `index.md` and `log.md`, records both ledgers, and commits in its worktree. Say **"land"** to merge into `main`. Next session, ask *"what do we know about X?"*: it already knows which pages exist (the title index is injected at session start) and answers from what it filed.

**Make it yours:** edit `goals.md` (what is this KB *for*?), rename `wiki/example-domain/`, and delete the examples. Then, when you want it:
- **A scheduled digest:** fill in `scripts/nightly/prompt-*.md` (marked *YOUR SPEC*) and `models.env`, set `DIGEST_SEND_CMD` / `NOTICE_SEND_CMD` for `notify.sh`, test with `NIGHTLY_TEST=1 scripts/nightly/run.sh`, then schedule it (`scripts/launchd/`).
- **A reader for your phone:** `python3 scripts/kb-server.py`; put your own links in a gitignored `home-links.json`.
- **Backups:** `DEST=<synced folder> scripts/kb-encrypted-backup.sh`.

Python scripts use the standard library only (`kb-server.py` uses the `markdown` package if present and falls back to a built-in renderer). The scheduled runner needs `claude` and/or `codex` CLIs.

---

## What changed since v1

v1 (July 2026) was the core loop: raw/wiki split, index-first retrieval, the ledger, portable skills, the protector function. v2 is what running that loop daily for a few more months forced into existence. The theme: **every rule that failed as prose became a mechanism.**

- **Worktree-per-session is now the default path**, not advice: a shell launcher creates a sparse worktree per session; a PreToolUse hook (Claude and Codex) blocks agent edits in the main tree; the pre-commit hook blocks commits there. The `land` skill finds the main tree itself.
- **A real pre-commit hook** with six checks (worktree, raw immutability, never-commit paths, ingest-without-ledger, hand-over doc lint, blast radius) and a test script that exercises every branch.
- **A stateful digest**: `day-ledger.py` carries daytime ingests into the next scheduled digest; the lint fails a digest that drops one; the shell consumes the ledger only after a passing digest exists.
- **A digest compiler**: `digest-lint.py` (length, section order, ledger coverage, required mentions, permission-slip asks, tool-leak fingerprints; style reported, never gated) plus one automatic repair pass.
- **A lab-agnostic, two-phase scheduled runner** replacing the single-phase template: one adapter for `claude`/`codex`, probe through the real code path, failover backend, ingest capped by a writer deadline, EXIT trap, self-healing of stranded branches, pluggable delivery.
- **Same-day failure alerts** through one alerts directory (digest top line + a push loop), because email is where alarms go to be ignored.
- **Coherence tooling**: a weekly deterministic report and a nightly judged cleanup of open items that a newer entry already resolved.
- **Hand-over document lint** (`prep-lint.py` + `print.sh`): a printed sheet can no longer claim "nothing outstanding" about something `state.md` carries as open.
- **A token-gated web reader** with a phone home page and a "Latest" box for long living pages.
- **A SessionStart title index**, so "we never documented that" is checked against every page title before it is said.
- **Encrypted backups** that exclude media by default and count what the prune matched.
- **Docs**: new hard rules in `AGENTS.md` (enforcement hierarchy, capture facts in the same turn, never assert absence from an unverified search, standing permission for routine work); skills split into a short `SKILL.md` plus `references/`; memory conventions for a growing index.

---

## Running it beyond one session

The next set of lessons came from running several agents, long jobs and phone-controlled sessions together. The theme is still **enforce with architecture**, now at the boundary between sessions:

- **Cheap coordination, capable judgment.** Use inexpensive models for bounded execution and status routing; escalate plans, ambiguous results and scientific decisions. Run long builds as shell jobs, with small event-driven watchers, so a large conversation does not keep paying to watch a log.
- **Process listings are a privacy boundary.** Another agent's prompt can be in its command line. Inspect PIDs, elapsed time and executable names; keep prompts on stdin and never print another session's arguments or logs.
- **Fallbacks preserve the job contract.** Bound retries, checkpoint progress, record the provider actually used, and verify the artifact after resuming. A specifically requested model must never be silently replaced.
- **The output and the alarm need separate paths.** Keep the deterministic fallback; run alerts outside the interactive session and verify that a test push reaches the phone. An API accepting a push request is only one step.
- **Compute needs a lifecycle.** Record ownership and budget before launch, stop idle resources, verify billing stopped, and clean up only the workers the job owns. A low-balance warning is useful; a spending limit is stronger.
- **A session lane has an identity.** Pin its conversation and project directory, start only missing lanes under a lock, and verify phone discovery as well as process health. Test updates against the behavior you need to preserve.
- **Workers tell the conductor through a script.** `tell-conductor` (alias `tell-general`, in `harness/tools/conductor-inbox/`) files an FYI without waking the conductor, wakes it only for a decision, a human or a break, and quarantines detail that matches your terms file behind a one-line summary.
- **Waiting sessions are surfaced, not discovered.** `rstack/tools/asks-waiting` lists sessions stopped on a question or a permission prompt, and untouched PRs, on every conductor turn.
- **Briefs and reports carry the ask and the result.** `rstack/hooks/results-brief-guard.py` and `results-report-guard.py` hold every subagent brief to "You asked: X. I will: Y." plus "Done when:", and every report to "You asked: X. Shipped: Y".
- **Text in your name is cut from your own messages.** `rh voice-cuts DRAFT` passes a draft built from your voice banks and records the pass the KB's voice-send gate checks.
- **Research starts with prior art; cleanup starts with live references.** Reproduce the public baseline before improving it, and check deployment/configuration references before moving an apparently stale folder to the trash.

See the [operations guide](docs/agent-operations.md) for the decision tables, checks and rollout order. The [model roles leaderboard](docs/model-roles.md) is the concrete counterpart: which model this setup uses for taste, review, mechanical work, building, cheap execution and writing, ranked from its own logged outcomes rather than public benchmarks, with list prices and measured cost per task. The machine-readable contract the harnesses read is [model-roles.json](docs/model-roles.json). It distinguishes mechanisms already shipped here from patterns to wire into your own deployment; this scaffold does not provision compute or manage your sessions for you.

---

## Design credits & philosophy

Built from a personal knowledge base an agent has maintained daily for about a year. This scaffold is the **system extracted from that KB**, rewritten as templates, with **none of the personal content**. It's the machine, published so others can run their own.

The core belief: *your knowledge, decisions, and taste are portable career capital.* Keep them in files you own, in a format any agent can read, and let the agent do the filing. See `AGENTS.md` for the full operating manual.

MIT licensed. Fork it, gut it, make it yours.

## References

The pattern this implements is not ours. Where it came from:

- Andrej Karpathy's LLM wiki: [the original post](https://x.com/karpathy/status/2039805659525644595), [the gist announcement](https://x.com/karpathy/status/2040470801506541998), [the gist itself](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and the [follow-up](https://x.com/karpathy/status/2041162213160091996) ("lets you skip writing but it doesn't let you skip reading and thinking").
- [@jumperz](https://x.com/jumperz/status/2039826228224430323) — the clearest statement of the loop: dump sources, let the model organise, file answers back.
- [@SebKrog](https://x.com/SebKrog/status/2111837281568874577) — six months of the same pattern on stock research; independent evidence that it holds up.
- Steph Ango, [File over app](https://stephango.com/file-over-app) — why the context lives in plain files you own.
- The counter-takes, kept because they set the limits: [@thomasmurphy__](https://x.com/thomasmurphy__/status/2040515487822442685) (you can't outsource metabolising what you read), [@rohit4verse](https://x.com/rohit4verse/status/2048081996841435596) (stacking markdown files isn't memory), [@_avichawla](https://x.com/_avichawla/status/2075489241245823325) (the more the agent remembers, the less it knows), [@0xaporia](https://x.com/0xaporia/status/2075533644114887069) (the knowledge base can't be smarter than the person building it).
- Harvey's [post-training update](https://x.com/gabepereyra/article/2090453918547685537) — the case for knowledge in the weights rather than notes read at inference.
- [Boris Cherny](https://x.com/bcherny/status/2077460395279692197) on encoding domain knowledge as infrastructure, and [Ali Ghodsi](https://x.com/a16z/status/2115118840388665644) on the "context problem" — the company-scale version of the same thing.
- Lauren Tan (@poteto), [pstack](https://github.com/cursor/plugins/tree/main/pstack) — the enforcement idea: a rule in prose doesn't hold, a lint rule does.
