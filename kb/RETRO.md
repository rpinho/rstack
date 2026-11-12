# Retro: what my agent knowledge base is for

I've kept this knowledge base since September 2025. It started as a folder of notes. It became a git repo in
April 2026, when I rebuilt it on Andrej Karpathy's [LLM wiki idea](https://x.com/karpathy/status/2039805659525644595).
I thought I was building a better way to keep up with AI and science. That's not what it turned into.

It's closer to a second brain. It remembers, it connects, and it steps in at the right moment with your own
evidence. That last part is the one I care about. A generic chatbot can't do it, because it doesn't know your
history. It can tell you what usually helps people. It can't tell you how your last five talks went.

## What that looks like

The night before a talk you want to hand it to someone else. The agent pulls up how your last five talks actually
went. They went fine. You give the talk.

The market drops and you want to sell everything. The agent shows you the plan you wrote when you were calm.
Nothing in it says sell on a red day. You hold.

Six weeks into a project, someone criticizes it and you want to drop the whole thing. The agent asks what actually
changed. The work from those six weeks is still good. One review is one data point. You keep going.

You're about to say yes to a fourth project when the last three slipped. You've been here before. The agent brings
back the post-mortem you wrote last time, before you say yes, not after.

All four have the same shape. You put in the effort, someone pushes back, and now you want to give away the part
people can see. In the moment it doesn't feel like a pattern. It feels like a judgment. Usually it's a prediction
that it will go badly, and usually the record says otherwise.

## What the agent does

When you say you want out, it doesn't help you get out.

It names it. "This is the urge to bail, not new information."

It shows the evidence. Your record, not average advice.

It brings it back to specifics. What's actually at stake. How prepared you actually are. How short the exposure
actually is. A talk is twenty minutes.

Then it doesn't let you skip the rep. Each time you go through with it and it goes fine, the prediction gets a
bit more accurate. Taking the exit removes that evidence.

None of this needs the agent to be clever. It needs it to know you, and to be there at the moment. A coach you
see once a week hears about it after. The KB is in the conversation where you say "maybe someone else should
present this."

## What the research says

The prediction is usually wrong. In one study, people in treatment for anxiety logged their worries and later
checked what happened. 91% didn't come true. The people whose logs showed that most clearly improved the most
([LaFreniere and Newman 2020](https://doi.org/10.1016/j.beth.2019.07.003)).

Timing matters. Health researchers call this a just-in-time adaptive intervention: the right support at the right
time, only when it's needed ([Nahum-Shani et al. 2018](https://doi.org/10.1007/s12160-016-9830-8)). They mostly
build it with phones and sensors. An agent that already has your notes and your plans can do it in the
conversation.

Decide cold. In a hot moment people don't just choose differently, they can't imagine choosing otherwise
([Loewenstein 1996](https://doi.org/10.1006/obhd.1996.0028)). If-then plans made in advance help. A meta-analysis
found a medium-to-large effect on reaching goals
([Gollwitzer and Sheeran 2006](https://doi.org/10.1016/S0065-2601(06)38002-1)). The KB is where the cold plan
lives.

## Hard mode and easy mode

Markets are the clearest case, because the urge has a price.

The rule: a plan is binding until it's invalidated, not until it's uncomfortable. Wanting to lock something in
isn't a reason. Neither is tightening a stop because the day felt bad. A reason is something the plan said would
end it. Whales, news and vibes don't count unless the plan named them.

The other half is reading the regime. You write down which mode you're in.

- **Hard mode.** Almost nothing works. Size small, protect what you have, most days do nothing.
- **Easy mode.** A lot works. The mistake now is sitting out.

The agent holds you to the mode you wrote. In hard mode it pushes back on the trade that only looks good because
you're bored. When the regime flips, it says so out loud, because missing easy mode is also a failure. Risk
management isn't avoiding risk. It's knowing which mode you're in.

## Post-mortems, and the past next to the present

Write the post-mortem while it's fresh. Not to feel bad. So the lesson shows up the next time the same setup does.

That's the other thing I didn't expect: associations. Something happens today and the KB says "this looks like
that thing in June, and here's what you wrote then." I don't remember most of what I wrote. The KB does. It's
the same job as the coaching. The past, next to the present, at the moment it matters.

## The other three jobs

Coach is one of four jobs. The assistant part is boring and useful. Reminders, what's due, where a document is,
what I decided last month and why. The partner part is talking through an idea and getting back what I already
know, what I read, and who said it. The counselor part is putting my own past reasoning next to the new facts.
Often the most useful thing it says is "you decided this already, here's why."

## A second brain

Karpathy's pattern is simple. Drop sources in a folder, let the model compile them into a wiki, ask questions,
file the answers back. "Every query makes the wiki better," as
[@jumperz](https://x.com/jumperz/status/2039826228224430323) put it. A lot of people built one.
[@SebKrog](https://x.com/SebKrog/status/2111837281568874577) built one for stock research in April and still uses
it every day. Mine is the same idea, used for everything.

Karpathy also named the catch in a [follow-up](https://x.com/karpathy/status/2041162213160091996): it lets you
skip writing, "but it doesn't let you skip reading and thinking." I agree. The KB doesn't think for me. It makes
sure I'm thinking with the right context.

## Process is secondary

There's a lot of machinery behind it. Lint checks, hooks, worktrees, a nightly digest, backups. I wrote about that
in the [rstack](https://github.com/rpinho/rstack) README. It matters, because a rule written in a prompt doesn't
hold and a rule enforced by code does.

But the machinery isn't the point. If someone copies this, I'd tell them to start from the function. What do you
want it to do for you on a bad day? Build that first. Then add the checks that keep it doing that.

## Still open

- How to tell whether it changed a decision, not just whether it was there.
- What it should forget.
- How much pushback is right. A coach that steps in too often becomes noise.
- Whether it works the same for someone whose pattern runs the other way, toward too much risk instead of too
  little.

## Thanks

Andrej Karpathy for the idea. Lauren Tan ([@poteto](https://x.com/poteto/status/2102050467505430555)) for the
instinct to turn every repeated mistake into a check. Steph Ango for
["file over app"](https://stephango.com/file-over-app).

## References

**Research**
- LaFreniere, L. S. and Newman, M. G. (2020). Exposing worry's deceit: percentage of untrue worries in
  generalized anxiety disorder treatment. *Behavior Therapy* 51(3), 413-423.
  [doi:10.1016/j.beth.2019.07.003](https://doi.org/10.1016/j.beth.2019.07.003)
- Nahum-Shani, I. et al. (2018). Just-in-time adaptive interventions (JITAIs) in mobile health: key components
  and design principles for ongoing health behavior support. *Annals of Behavioral Medicine* 52(6), 446-462.
  [doi:10.1007/s12160-016-9830-8](https://doi.org/10.1007/s12160-016-9830-8)
- Loewenstein, G. (1996). Out of control: visceral influences on behavior. *Organizational Behavior and Human
  Decision Processes* 65(3), 272-292. [doi:10.1006/obhd.1996.0028](https://doi.org/10.1006/obhd.1996.0028)
- Gollwitzer, P. M. and Sheeran, P. (2006). Implementation intentions and goal achievement: a meta-analysis of
  effects and processes. *Advances in Experimental Social Psychology* 38, 69-119.
  [doi:10.1016/S0065-2601(06)38002-1](https://doi.org/10.1016/S0065-2601(06)38002-1)

**The LLM wiki and the machinery**
- Andrej Karpathy, LLM wiki: [post](https://x.com/karpathy/status/2039805659525644595),
  [gist announcement](https://x.com/karpathy/status/2040470801506541998),
  [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f),
  [follow-up on reading and thinking](https://x.com/karpathy/status/2041162213160091996).
- [@jumperz on the query-and-file-back loop](https://x.com/jumperz/status/2039826228224430323).
- [@SebKrog, an LLM knowledge base for stock research, six months on](https://x.com/SebKrog/status/2111837281568874577).
- Steph Ango, [File over app](https://stephango.com/file-over-app).
- Lauren Tan (@poteto), [lint-rule instinct](https://x.com/poteto/status/2102050467505430555) and
  [pstack](https://github.com/cursor/plugins/tree/main/pstack), which rstack is named after.
- [rstack](https://github.com/rpinho/rstack) (the machinery), formerly agent-kb.
