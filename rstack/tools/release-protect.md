# Protected paths at cleanup

`release-protect --registry PRIVATE.json PATH...` refuses any candidate that is a
protected path, contains it, or lies inside it. Lexical paths and resolved symlink
paths are both checked. The tool only checks; it never deletes or approves data.

The JSON format is `{"paths":["/absolute/path"],"sources":["/absolute/private.json"]}`.
Sources are reread on each call; missing, malformed or cyclic registered sources
refuse cleanup. The default registry is `~/.local/state/rstack/protected-paths.json`
(`RSTACK_PROTECTED_PATHS` overrides it). An absent default registry means that no
application has registered paths; an explicitly requested missing file refuses.

The Finder-delete `osascript` shim checks this registry before either Trash or
Finder fallback. Install `protected_paths.py` beside the shim, including when
copying it rather than symlinking it. Copy its sibling `shell_commands.py` too for
the shell hook; it shares the model gate's parser and unfinished-quote fallback.
`harness.storage.trash` uses the same check. The Bash hook refuses confirmed
overlaps and names the protected path. It logs a warning and allows cleanup if
metadata or shell-local operands are unreadable, while checking any paths it
can resolve. The canonical library is tracked under
`harness/`, so normal harness sync includes it; the tools directory links to it.
Application-specific retention belongs to the application: the games deployment
code computes its last three successful live releases and registers its private
path-list file as a source. No release metadata belongs in this repository.

## Refresh after a live switch

```sh
release-protect sync --from-deploy "$FAMILY_DEPLOY_ROOT" --dry-run
release-protect sync --from-deploy "$FAMILY_DEPLOY_ROOT"
```

Sync uses Node to import `DEPLOY_ROOT/bin/release-retention.mjs` and call the
deploy CLI's exported `releaseProtection` function:
the last three distinct successful live releases per app, plus the current live
symlink target (which can be a fourth release after an interrupted promotion).
It covers configured apps, recorded history and live symlinks. There is no rstack
copy of that retention policy. Importing also works through the installed
`bin/current` symlinks, where the module's standalone CLI guard prints nothing.
`--retention-script FILE` selects a source checkout
module for an offline check; `--node PATH` selects its Node executable. Missing
deployment configuration, failed queries and malformed output refuse sync.

Only paths below this deployment's `releases/APP/VERSION` subtree are replaced.
The root registry receives the desired release set. Old release entries are
removed from its registered sources too, including nested sources, so a stale
source cannot silently keep an expired release protected. Non-release paths,
other deployments, source registrations and schema fields are preserved.
Source entries that are still in the desired set are also preserved.
Source symlinks are preserved. Use this only with sources whose release entries
belong to the supplied deployment's retention policy.

Live symlinks (even broken ones) and `live/current.json` are read independently:
if the deploy result omits any live release, sync refuses before changing paths.
A change to the live pointers during writes also refuses. Run the promote hook
inside the deploy CLI's existing live lock; manual sync must run while live
switches are idle. The registry lock serializes sync writers, not arbitrary
writers to registry/source files. Documents are checked for intervening edits
before each replacement.

Writes use atomic replacements, with new protections in the root registry before
source cleanup. An interruption can leave excess protection; rerunning converges.
`release-protect-sync.jsonl` beside the registry records each intended document
update's adds and removes before its replacement; a log entry alone does not
prove that the replacement completed. `--dry-run` prints both the effective set
diff and per-document changes; it creates no directories, locks or logs and
changes no registry/source files. A converged sync writes no documents or logs.
Install `release_sync.py` beside `release-protect` and `job-health` when activating
the committed tools; no installation is performed by sync.

## Drift alert in the existing job-health job

Merge an entry into the private job-health registry on each deployment host:

```json
{
  "release_protection": [{
    "deploy_root": "~/.local/share/family-games",
    "registry": "~/.local/state/rstack/protected-paths.json"
  }]
}
```

`node` and optional `retention_script` can also be configured in that entry.
The existing scheduled `job-health --prefix YOUR_PREFIX --alert YOUR_ALERT`
compares the effective release set on each run. After more than one hour of
continuously observed drift it reports `release-protection` through its existing
asks-waiting, alert deduplication and recovery path. Run it locally on the M4 for
the M4 deployment; `--push` can forward the existing report. No SSH source is
implicit. The timer starts at the first observed mismatch, resets on equality,
and does not reset when the mismatch changes or a comparison fails. Failed
comparisons are included in the same one-hour alert window. The timer is stored
under `$RSTACK_STATE_DIR/job-health/release-protection.json`; `--dry` and a run
without a prefix never update it. Detection is the first scheduled check after
the hour, rather than a retrospective estimate from file mtimes. This opt-in
requires activating the committed job-health code and configuring its existing
schedule; it creates no new scheduled job.

Direct calls to the operating system's deletion utilities are outside these
Python boundaries. Cleanup clients must call this check immediately before moving
paths, and applications must keep their own cleanup code protected as well.
The existing `trash-guard.py` shell hook also checks ordinary `trash`, `rm`,
`rmdir`, `unlink` and `mv`-to-Trash operands against the registry. It checks the
executable command, including explicit shell/SSH command strings, rather than
looking for deletion words in arbitrary arguments or file contents. Unresolvable
deletion operands refuse when protected paths are registered. This is not a
general shell sandbox.
