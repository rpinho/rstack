# Release hardening for kid-facing apps

A family learning app shipped a release that passed about 2,600 code tests and still broke what each child saw:
- labels hidden for one profile;
- another child's roster shown;
- generated art and system text-to-speech where recorded audio belonged;
- addition that counted tap positions;
- the previous release deleted in a cleanup, so there was nothing to roll back to.

The tests checked code. Nothing checked each user's experience, and the builder reviewed its own screenshots.

rstack treats this the way it treats research claims:
- **The builder is never the judge.** A separate step, and for visual review a different model, checks what each user sees and hears.
- **A release is judged by yield.** Usage after release, not the act of shipping, decides whether it worked.

## Gates, in build order

1. **Per-profile acceptance (blocking).** Golden screenshots of every profile's home and of each game's first screen, per profile and viewport (`rstack/tools/ui-golden`). Any difference over the threshold refuses the stage until a person approves a new golden. Goldens and profiles stay private, never in a public repo.
2. **Profile data isolation (blocking).** Property tests over every pair of profiles: rosters, faces, words and saves come only from that profile's config plus shared family data, never from another profile's.
3. **Audio and logic (blocking).** A no-TTS lint over shipped code, including built bundles; recorded-clip coverage for every spoken string; property tests for game logic, such as running totals and difficulty ramps.
4. **Blast radius.** Each release lists the profiles whose screens change, computed from the golden diffs, so a shared-code change cannot silently reach one user.
5. **Per-profile flags.** New games and rules ship off, and turn on per profile only after a "what they'll see" card with screenshots is approved on the owner's review page.
6. **Rollback that works.** The last three live releases of every game are protected from cleanup in code, and a one-command rollback to the previous release is allowed at any time. Idle windows apply only to forward releases.
7. **Post-release monitoring.** At 24 and 48 hours: per-profile rounds started vs finished, seconds per board, games opened vs never opened, and load errors. A bad reading flags the conductor with a suggested rollback.
8. **Independent visual referee.** A different model reviews new art against reference art, calibrated each run with a planted ugly variant it must reject.
9. **Post-mortems.** Every user-facing regression gets a short post-mortem whose action items are tracked to closure.

A release freeze holds until gates 1-3 are live.
