# Advisor

Read this file in full before consulting an advisor, and again after a compaction before the next consultation. **Advisor** in `SKILL.md` says when to consult one.

**Advisor model.** Consult one advisor per family, and choose each family's advisor by these steps in order, whatever model you run on and with your own model eligible:

1. Among the family's too-expensive-edge models (see **Tiers.** in `dispatch.md`) that a successfully retrieved catalog of one of its sources offers, take the strongest as the provider ranks them, or the costlier of two that ranking does not separate. Use its newest version (see **Model ID** in `dispatch.md`) from the first source in the family's order that offers it. Run it at the effort the Brainstorming and discussion row in `dispatch.md` gives that family, Claude `high` and GPT `xhigh`; take only the effort from that row, never its top-tier model. For example, an orchestrator on Astra consults Astra and the stronger of Fable and Mythos, not Sol or Opus.
2. When none of the family's sources offers such a model, take its top-tier model the same way.
3. When no source offers a model of either family, choose each advisor as **Fallbacks** in `dispatch.md` chooses for a role on the Brainstorming and discussion row, except that the advisor takes the strongest model the available sources offer, too-expensive-edge models included.
4. On a mode-only route, carry the advisor in the mode that the product's own description of its modes places highest in capability, such as Ultra on Devin, or in the costlier of two modes that description places level at the top.
5. When a dispatch fails at run time, apply steps 1–3 again to that dispatch with its source's catalog treated as not offering its model; each later dispatch starts from step 1.
6. When only one advisor can run, consult it alone; when no route can run one, decide on your own grounding, or escalate when you cannot ground it.

On a CLI route, apply `cli-dispatch.md` with the advisor's model in place of the top-tier model it names, pin that model's full ID, and set aside the reference's bans on too-expensive-edge models.

In the first round, run the advisors concurrently on the same question, neither seeing the other's answer, or one after the other when a concurrency limit allows only one.

**Advisor input** — the decision, the options, the evidence with its sources (workers' final artifacts and reviewers' verdicts included), the DoD and the constraints. In every round, withhold the intermediate reasoning behind any result, yours or a delegate's, and withhold your own leaning so it cannot anchor the advice. The advisor may read the sources itself but writes nothing to the deliverable.

**Advisor output** — a recommendation, the reasons tied to the evidence, what would change it, and its confidence.

Keep consulting while the decision stays uncertain. Each follow-up round asks what the last left open: a condition the advice said would change it, a gap it left unaddressed, evidence that arrived since, or, when the advisors disagree, each one's recommendation and reasons put to the other; re-sending the same question for a different answer is not a round. Stop once you can decide on grounded reasons or a round no longer moves your decision or confidence. Then check the advice at the source and decide yourself, whether or not the advisors agree; take a decision you still cannot ground to the user (see **Run it to done** in `SKILL.md`). Announce each advisor in the **Reporting** form in `dispatch.md` with the role label `Advisor`.

**Advisor check.** At the **Self-check** in `SKILL.md`, confirm for every consultation: each round asked something new, the advisors were briefed without your leaning or the intermediate reasoning behind any result, and you checked their advice at the source before deciding.
