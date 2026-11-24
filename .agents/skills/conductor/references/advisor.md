# Advisor

Read this file in full before consulting an advisor, and again after a compaction before the next consultation. **Advisor** in `SKILL.md` says when to consult one.

**Advisor model.** Consult at most two advisors, never three, each from a different family. Choose them by these steps in order, whatever model you run on and with your own model eligible:

1. Walk these six slots in order, skipping a slot whose family already has an advisor, until two advisors are taken or the list ends. A slot considers only models with an eligible version in a successfully retrieved catalog that an available source in its family's order can run with its effective credentials: a too-expensive-edge slot takes the strongest such model of its family as the provider ranks them, breaking a provider-ranking tie by the costlier model, then by the candidate runnable on the earlier source in the family's order, then by that source's catalog order; a top-tier slot takes its family's top-tier model. Skip a slot that no eligible source can fill.
   - Too-expensive edge (see **Tiers.** in `dispatch.md`): (1) Anthropic's, Fable or Mythos today; (2) Google's, Gemini 4 Carbon today; (3) OpenAI's, Astra today.
   - Top tier: (4) Google's, Gemini 4 Neon today; (5) Anthropic's, Opus today; (6) OpenAI's, Sol today.

   For example, when all three providers have a runnable too-expensive-edge model, consult the winning runnable Anthropic model (Fable or Mythos) and Gemini 4 Carbon, not Astra; when Astra is the only runnable too-expensive-edge model and Google and Anthropic have runnable top-tier models, consult Astra and Gemini 4 Neon; when no too-expensive-edge model can run, consult Gemini 4 Neon and Opus when both can run.
2. Use each taken model's newest eligible version (see **Model ID** in `dispatch.md`) from the first available source in its family's order that can run it. Run Anthropic's too-expensive-edge slot at `high`, Anthropic's top-tier slot at `xhigh`, both Google slots at `high`, and both OpenAI slots at `xhigh`.
3. When the six slots leave no selected or retained advisor for the consultation, choose two advisors from distinct families (or one when only one family qualifies), as **Fallbacks** in `dispatch.md` chooses for a role on the Brainstorming and discussion row, except that each advisor takes the strongest runnable model the available sources offer for its family, too-expensive-edge models included.
4. On a mode-only route, carry the advisor in the mode that the product's own description of its modes places highest in capability, such as Ultra on Devin, or in the costlier of two modes that description places level at the top.
5. When a dispatch fails at run time, exclude that failed model–source pair (or failed mode-only route) for the rest of the consultation and apply steps 1–4 again to fill that advisor's place, keeping any other advisor already chosen and skipping its family; clear those exclusions for the next consultation.
6. When only one advisor can run, consult it alone; when no route can run one, decide on your own grounding, or escalate when you cannot ground it.

On a CLI route, apply `cli-dispatch.md` with the advisor's model in place of the top-tier model it names, pin that model's full ID, and set aside the reference's bans on too-expensive-edge models.

In the first round, run the advisors concurrently on the same question, neither seeing the other's answer, or one after the other when a concurrency limit allows only one.

**Advisor input** — the decision, the options, the evidence with its sources (workers' final artifacts and reviewers' verdicts included), the DoD and the constraints. In every round, withhold the intermediate reasoning behind any result, yours or a delegate's, and withhold your own leaning so it cannot anchor the advice. The advisor may read the sources itself but writes nothing to the deliverable.

**Advisor output** — a recommendation, the reasons tied to the evidence, what would change it, and its confidence.

Keep consulting while the decision stays uncertain. Each follow-up round asks what the last left open: a condition the advice said would change it, a gap it left unaddressed, evidence that arrived since, or, when the advisors disagree, each one's recommendation and reasons put to the other; re-sending the same question for a different answer is not a round. Stop once you can decide on grounded reasons or a round no longer moves your decision or confidence. Then check the advice at the source and decide yourself, whether or not the advisors agree; take a decision you still cannot ground to the user (see **Run it to done** in `SKILL.md`).

**Advisor check.** At the **Self-check** in `SKILL.md`, confirm for every consultation: each round used at most two advisors from distinct families selected under **Advisor model**, with cumulative exclusions applied to any replacement for a failed dispatch; each round asked something new, the advisors were briefed without your leaning or the intermediate reasoning behind any result, and you checked their advice at the source before deciding.
