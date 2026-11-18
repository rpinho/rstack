# Mechanical steps stay with the agent

`ask_lint.lint(text, reason_tag=None)` returns a list of refusal messages, or
`[]` to allow. Each refusal says `do it yourself: <the mechanical step>`.
The CLI reads a text argument or stdin and exits 2 on refusal:

```sh
python3 rstack/tools/ask_lint.py 'upload the PDF at the AAS link'
python3 rstack/tools/ask_lint.py --his-only auth 'click the magic link to log in'
python3 rstack/tools/ask_lint.py 'read and OK the reply'
```

Reasons are `auth`, `money`, `delete`, `attest`, `first-email`, `terms` and
`judgment`. A reason may also appear as `[his-only: auth]` in the text.
Unknown classes raise `ValueError` (CLI exit 2). Signing in, logging in,
approving, reading and OKing, deciding and paying are his actions without a
tag. Clicking or following a login or magic link requires **auth** explicitly.
An approval verb does not excuse a separate mechanical instruction.

The readable patterns cover upload, paste, click, press, fill in/out, copy
to/into, type, attach, run, open, submit, enter and follow a link. They match
imperatives and common second-person requests, including polite questions,
lists and coordinated steps. This is an English pattern lint, not a semantic
classifier: paraphrases can evade it and ambiguous noun uses can be refused.
A reason declares why the owner is needed; the lint cannot establish whether
the declaration is true.

`lint_review_item` checks the review title, note and checkbox labels, including
an optional saved `his_only` reason. Inline tags apply to their individual
field. The `lane-no-questions.py` hook checks each question plus its option
labels and descriptions before its existing conductor restriction. A question
tag covers that question's options, but does not exempt another question.

`harness-sync` ships the lint from committed source into
`~/.local/share/research-harness/rstack/tools/ask_lint.py`. Private wrappers
import or invoke that installed module; `RSTACK_TOOLS` overrides the directory.
The private `review-add` and `notify-ricardo` integrations use per-machine
patches, not copies of private scripts in this repository. `review-add` checks
before rendering or writing the queue, including `--attach`; notification text
and title are checked before reading the topic, writing a log or sending.
Both accept `--his-only class`; notifications retain their existing positional
message, title and priority arguments. Neither integration grants permission
to send, sign, pay or perform any other action.
