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
copying it rather than symlinking it. `harness.storage.trash` uses the same check. The canonical library is tracked under
`harness/`, so normal harness sync includes it; the tools directory links to it.
Application-specific retention belongs to the application: the games deployment
code computes its last three successful live releases and registers its private
path-list file as a source. No release metadata belongs in this repository.

Direct calls to the operating system's deletion utilities are outside these
Python boundaries. Cleanup clients must call this check immediately before moving
paths, and applications must keep their own cleanup code protected as well.
The existing `trash-guard.py` shell hook also checks ordinary `trash`, `rm`,
`rmdir` and `unlink` operands against the registry. Unresolvable deletion operands
refuse when protected paths are registered. This is not a general shell sandbox.
