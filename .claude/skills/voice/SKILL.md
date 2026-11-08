---
name: voice
description: Make an agent write in your own voice, measured from your own writing, and refuse text that doesn't sound like you before it goes out. Use before drafting anything sent under your name, and to set up or tune the voice check.
---

# Your voice, measured and enforced

The problem I had was not that agents wrote badly. They wrote fluently in someone else's voice,
and people noticed. A paragraph in a CLAUDE.md saying "write like me" didn't fix it. Three things
together did.

## 1. Measure your voice from your own writing

Export a few hundred things you actually wrote: chat messages, emails, comments. Not polished
documents, they're the wrong register. Then profile them:

```sh
rstack/tools/voice-lint --measure my-messages/*.txt
```

It reports median and 90th-percentile sentence length, how often you use contractions, start in
lowercase, hedge ("I think", "probably"), use exclamation marks and em dashes. Write a short guide
from those numbers, each rule with its count. "Short sentences" is a wish; "median 8 words per
sentence, 90% under 14" is a rule an agent can follow and you can check. Keep the corpus and the
guide private. Never publish your own phrases.

## 2. Keep a slop list

Every time a draft reads wrong to you, write down the phrase that did it. That list is what the
lint checks. [slop.example.txt](../../../rstack/tools/slop.example.txt)
has generic entries to start from; yours will be specific to you.

## 3. Gate every outbound text with a lint

The guide steers the draft. The lint refuses it:

```sh
rstack/tools/voice-lint --slop my-slop.txt < draft.txt     # FAIL: lines and exit 1, or PASS
```

Wire it where text leaves, not where it's written. In the research harness, set
`RH_VOICE_COMMAND` to that command and `rh outreach lint` refuses a draft that fails it; for email
sent from a browser, the send hook in `tools/email-voice-gate.py` checks the exact bytes against an
approved, linted draft. A rule that only lives in the prompt gets skipped on a busy day. A send that
fails the lint doesn't go.

## Using it when drafting

Load the guide, write the draft, run the lint, fix what it finds, and show the result. Start with
the actual thought. Stop when the thought is done. When the person pushes back on tone, the fix is
a new line in the guide or the slop list, not a promise to do better.
