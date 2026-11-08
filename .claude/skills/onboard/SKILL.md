---
name: onboard
description: Start here if you are new to rstack. Asks whether you are a beginner, intermediate or advanced, checks that with three short questions, and walks you through the track that fits. Use when someone opens this repo for the first time, says "where do I start", or types /onboard.
---

Most people who open this repo don't need most of it. Put them on the track that fits and keep the
rest out of the way.

1. Ask one question, exactly: **"Are you a beginner, intermediate, or advanced with coding agents?"**
   Their answer is where you start, not where they end up.
2. Then ask these three, one at a time, and wait for each answer:
   - Have you used Claude Code or Codex on real work, not only tried it?
   - Have you written a skill or a CLAUDE.md (or AGENTS.md) yourself?
   - Have you run agents in the background or several in parallel?
3. Place them:
   - No to the first question: **beginner**, whatever they said in step 1.
   - Yes to the first, no to the second: **intermediate** at most.
   - Yes to all three: **advanced** is open to them. If they said beginner or intermediate, offer
     it, and let them choose.
   - Otherwise keep what they said.
   Tell them the track in one sentence and why ("you've used Claude Code but haven't written a
   skill yet, so intermediate").
4. Walk them through the track, one step at a time, doing the steps with them in their own setup:
   - beginner: [docs/onboarding/beginner.md](../../../docs/onboarding/beginner.md)
   - intermediate: [docs/onboarding/intermediate.md](../../../docs/onboarding/intermediate.md)
   - advanced: [docs/onboarding/advanced.md](../../../docs/onboarding/advanced.md)
5. Each track ends with "Ready for the next one?". Ask those questions. They move up when they can
   do the things listed, not when they've read about them. If they can't yet, say which one to
   practise and stop there.

Don't show a beginner the hooks, the lanes or the harness. The tracks link to that material only
with a "later" next to it, and a test in this repo keeps it that way.
