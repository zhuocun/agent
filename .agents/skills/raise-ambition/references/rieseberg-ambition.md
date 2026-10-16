# How to be more ambitious: A tutorial for humans with models

- **Author:** Felix Rieseberg (engineering manager at Anthropic, working on Claude)
- **Published:** 13 October 2026 (the page gives an 8-minute reading time)
- **Original, for the full text:** https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/

This file is a summary in our own words, not the essay. Phrases in quotation marks are the essay's own wording; everything else paraphrases it. The summary runs to the end of the file; no notes of our own are added. Sections follow the essay's order; the essay's own headings are Altitude, Depth, Range and "We have been here before", and the others are added here.

## Summary

### Why the essay exists

The author works on Claude and keeps seeing things done with models that he had not thought of or thought possible; his examples from the month of writing are that Claude may have helped discover a new planet, that an AI music video has finally impressed him, and that people are discussing a new era in mathematics. Citing Terence Tao, he notes that model capabilities grow unevenly, "astounding in some directions, while inadequate in others". Some users exploit the strong directions and achieve a lot; many others are still working out what models are good for beyond trivia questions or toning down an angry email. People who build AI often tell users to be more ambitious, but that advice is hard to act on, so the essay sets out to be a practical tutorial for it. The author uses Claude but says the advice is not tied to any one model.

### The four types of ambition

The essay names four types, in this order:

- **Speed:** the same work done in less time. The essay calls this the core of AI's economic value (for example, writing code faster), well established and needing little creativity, and deliberately does not develop it further.
- **Altitude:** moving up in abstraction, so the model works toward the outcome rather than a single task.
- **Depth:** working to a field-leading expert's standard, which means reaching beneath the task itself to the raw data, tools and problems it rests on.
- **Range:** drawing on several fields, not only the one the task obviously belongs to, and bringing in knowledge, tools and techniques from outside the usual toolkit.

### Altitude

A task handed to a model is the user's best guess at how to reach the outcome they want; ambition in altitude means handing over the outcome itself. The guiding question is what you want to happen next: "What's the goal beyond the goal?" The author's own example is moving from asking Claude to fix individual crashes to asking it to keep the apps crash-free.

The worked example is a quarterly business review (QBR) deck at an imagined company, Acme Inc. Merely filling in a slide template is the unambitious baseline. The essay then climbs in three steps:

1. Give the model as much of the business's data as you can, not just the template's numbers, and ask it to explain the quarter's changes, their causes and the right response.
2. Since good meetings end in decisions, ask the model to work out the three most urgent decisions and to develop possible directions for each with arguments for and against.
3. Question the format itself. The essay notes that quarterly reviews date from when people had to sift the data by hand, and that their real job is early warning and moving budget and staff to where they are needed. Ask the model to propose a mechanism that does that job better than a deck, test it against past quarters to show it would have flagged problems earlier, and trial it alongside the current review for one quarter.

What the essay says about when altitude fits, its limits, and its payoff:

- It suits work aimed at a final outcome and suits creative work less. A good sign that it fits is that the work will be discussed in meetings.
- There are current limits: an open-ended instruction such as telling the model to go and make money does not seem to work for most businesses on its own in 2026, although the author observes that models seem able to work at higher abstraction as they grow more capable.
- Altitude is where lasting workflows that remove the human from the loop come from, so the user needs to hand the model new tasks less often. Getting there often means changing the workflow first. For the crash-free goal, the author first had to let Claude fetch crash reports easily, map each app version to its git commit, and use Windows, macOS and Linux machines so it could reproduce and verify fixes on its own.

### Depth

Depth is for when the task must be done exceptionally well: press the model to work with the instruments, methods, formats and expertise the leading practitioners use, and to continue until those practitioners could learn from the result. The running example is the same QBR, assuming Acme Inc has a customer-churn problem. The essay's techniques:

- **Use the instruments the best practitioners use.** Asked to act like a professional, "models often switch vocabulary without actually switching methods". Hold it to the real methods of leading data scientists and statisticians, such as databases and statistical models rather than markdown tables; the model usually knows what those are even when the user does not.
- **Set unreasonable goals and tell the model they are reasonable.** Ask for far more than you need (the essay's example: needing a 5 s page load instead of 10 s, ask for 200 ms), and when the model calls something impossible, insist that it is solvable and have it keep going.
- **Challenge what you know.** Business beliefs are often only rough approximations, so have the model test them adversarially against the raw data; the essay's example is trying to reproduce from that data the belief that churn is an onboarding problem.
- **Produce new knowledge.** Once the model is deep in the data, ask it for blind spots: for example, have it model the customer base so that it replays the past year from the logs, look for the earliest churn signal that nobody knows about yet, and test that signal on data the model has not seen.
- **Use an outside judge.** "Do not ask the model to judge itself." The author expects this to be solved as models improve, but as of October 2026 he urges outside validation, ideally a tool the model can run on its own for instant feedback.

The section ends with a short prompt the author often uses, which opens "I want a deeper version of this task, not a bigger one." It has the model first answer four questions (what an expert would add that the request leaves out, which unprocessed sources they would begin with, which methods and tools they would apply, and what independent check, neither the model nor the user, would confirm the result) and then restate the request around those answers.

### Range

Range means bringing more fields to bear on the work than it would once have paid to involve. The author compares it to heist films, which spend their opening assembling a crew with different skills. As multi-agent setups (several threads, orchestrators or subagents) get easier to run, he reports interesting results from asking Claude to bring in more fields. He admits it is hard and needs creativity: he had never thought of using Claude to build 3D environments for his homepage, despite having made video games, until he saw his colleague Alex Albert render interior designs in Blender. He nonetheless sees the most striking results here. Techniques:

- **Replace nouns with verbs**, a trick from *The Art of Innovation* by Tom Kelley and Jonathan Littman. Restated as an activity, the QBR is about persuading busy people of a causal account and getting them to decide, despite uncertainty, within a half-hour meeting. Stating the verb shows both user and model which fields could contribute.
- **Assemble the crew.** Imagine, as the essay jokes, that aliens will destroy Earth unless the deck is excellent, and ask who humanity would recruit: for production quality an analyst, a journalist and an editor; for a presentation, a motion and audio designer; and as an adversarial red team, a short seller and a forensic accountant.

The essay's caveat: this easily turns into role play, which makes the transcript stranger without improving the outcome. Use the crew exercise to find fields and techniques, then have the model carry out the actual work of that role; the essay's example is to ask it not to imitate a short seller's style but to "do what a short seller does to research their position".

### A precondition for all four types

Every kind of ambition described needs the model to work on a computer where it can install software, plus access to the relevant data, through MCP connectors or other means. The author recommends using one of the many tools that provide this.

### We have been here before

The closing section explains why the advice is needed. People are held back by what they believe possible and tend to trust themselves only in narrow disciplines; Michelangelo did not want to paint the Sistine Chapel because he saw himself as a sculptor. Psychology calls the relevant belief self-efficacy: people who believe more in their abilities achieve more. The essay argues self-efficacy can be deliberately raised, pointing to Locke and Latham's review of 35 years of goal-setting research (specific hard goals beat being told to do one's best) and to Patrick Collison's "Fast" list of achievements made under audacious goals and tight deadlines. It lists three documented ways:

- **Believing the hard thing is possible:** in 1939 George Dantzig arrived late to a Berkeley statistics class, copied two problems from the board, solved them believing they were homework, and handed them in; they were unsolved problems in statistics.
- **Seeing someone else do it:** Roger Bannister broke the four-minute mile in May 1954 and was the only one to have done so for just 46 days. The essay sees the same with the two-hour marathon: in London in April 2026 Sabastian Sawe became the first to finish an official marathon in under two hours, and the second-placed runner in that race did so too.
- **Permitting yourself to fail:** *The Inner Game of Tennis* argues that you do not play your best when trying very hard; Linux was announced as just a hobby that would not become big and professional.

The essay ends by saying self-efficacy is an old problem made more powerful now that abilities leap every few weeks, so people need techniques for doing things they had not considered or believed possible, and it invites readers to send the author further techniques. The post's image is Francisco Goya's "Modo de volar" (A Way of Flying).
