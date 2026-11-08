---
name: reciprocate
description: Write a reply that mirrors the message it answers (length, greeting, warmth, questions, family, language, emoticons), checked by the outreach lint. Use for any reply to a person who wrote first, and for any send they asked for.
---

A reply is a mirror of the message it answers. A short note gets a short note back. A warm one
gets something as warm. Every question they asked gets an answer, and if they asked how you are,
you say what you're doing and ask about them. They mention family, yours goes in; they don't, it
stays out. Answer in the language they wrote in.

1. Save their latest message to a private file (not a temporary directory).
2. Draft with `rh outreach draft ... --incoming THEIR_FILE`. A draft to a contact whose move it is
   to answer (ball on our side) or one drafted with `--requested` fails as
   `RECIPROCATE_INCOMING_MISSING` without it.
3. `rh outreach lint LANE ID`. Each `RECIPROCATE_*` finding quotes their line and ours. Fix the
   draft, not the numbers: the length band is 0.7 to 1.6 times their words (2.0 when they asked
   something), and a short message under 40 words may get up to 40 back.
4. Read it next to theirs once more before approving. The lint is lexical, English and
   Portuguese; it catches the common misses, not tone.

Codes and settings: docs/outreach.md, "Reciprocate". Code: harness/reciprocate.py.
