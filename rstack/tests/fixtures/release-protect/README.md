`release-retention.mjs` is an unmodified snapshot of the games deploy CLI's
retention module, read on 2026-11-18 from the `20261118-p0-int` worktree. The M4
`20261118-ff-sprint` worktree and installed module had the same SHA-256:
`2841fe98d629c180667f8a8e9e1d67f890b571ec49a4570d6c33c148b20c42a3`.

Tests invoke its exported function against synthetic deploy roots. Production
sync imports the module installed in the supplied deploy root; the snapshot is
only a test fixture, never a production retention implementation. Node is needed
to run these integration tests, just as it is needed by the games deploy CLI.
