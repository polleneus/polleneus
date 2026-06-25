# polleneus — Ways of Working

How work moves from idea to `main`. This is the canonical process; every change follows it.

> **TL;DR.** A change flows **intake → spec → plan → build → review → PR → review → merge**, with
> **review loops that repeat until clean**, on **two channels** (in-repo AI fan-out + `@codex review` on
> the PR). The **Maintainer (CTO)** owns the few high-leverage decisions; the **engineering loop** (AI-assisted)
> owns everything else and operates autonomously between the gates.

---

## Roles

- **Maintainer / CTO** — decision authority. Gates: (0) *what* to build & priority, (1) **spec sign-off**,
  (6) **merge to `main`**, and **any change that bends a [core invariant](specs/2026-06-25-polleneus-design.md#2-goals-non-goals-and-the-design-rule), alters a public claim/the honest promise, or touches releases / money / legal / identity.**
- **Engineering loop** (AI-assisted: Claude drives implementation + the in-repo review board; Codex is the
  external reviewer on PRs) — owns spec/plan drafting, implementation, the review-and-fix loops, PRs, and
  honest verification. Operates **autonomously between the gates**.

Three rules the engineering loop holds to **always**: (1) report verification **truthfully** — real command
output, never a hopeful "should work"; (2) any **invariant-bending** change is a CTO gate, not an autonomous
call; (3) **never skip a review loop** to save time.

---

## The loop

```
0. INTAKE          Maintainer picks the feature + priority.                         [CTO GATE]
1. SPEC            Brainstorm → feature spec (docs/superpowers/specs/).
                   → AI fan-out design review → fix → re-review … until clean.
                   → Maintainer signs off on the spec.                              [CTO GATE]
2. PLAN            writing-plans → plan (docs/superpowers/plans/).
                   → AI fan-out plan review → fix → … until clean.
3. BUILD           Feature branch (git worktree), TDD, implement.
                   → Self-verify: tests green AND the app actually runs.
4. INTERNAL REVIEW AI fan-out code review — correctness + SECURITY + the 7 invariants
                   + simplicity → fix → re-review … until clean.
5. PR + CODEX      Open PR → comment "@codex review".
                   → Triage findings (verify, don't blindly apply) → fix → push
                   → "@codex review" again … until Codex is clean.
6. MERGE           Summarize both review trails → Maintainer approves → merge.       [CTO GATE]
```

Artifacts: specs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`, review reports in
`docs/superpowers/reviews/`.

---

## Review loops — when is it "clean"?

A gate passes when **there are no unresolved high/critical findings.** Lower-severity findings are either
fixed or explicitly recorded as accepted in the PR.

- **Invariant breach = immediate stop.** Any finding that bends one of the seven invariants, weakens the
  honest promise, or changes a public claim halts the loop and escalates to the Maintainer **regardless of
  severity or round count.**
- **Round bound = 2.** If two `fix → re-review` rounds do not reach clean, the loop **stops and the
  disagreement goes to the Maintainer** rather than spinning. (We bring the decision, not the churn.)
- **Security lens is mandatory**, not optional — this is an anonymity tool. Crypto/protocol/transport changes
  also run `/security-review`.

### The two review channels
- **In-repo AI fan-out** (steps 1, 2, 4) — multiple independent reviewers, each a distinct lens
  (correctness, security/anonymity-invariants, simplicity, prior-art). Adversarial *and* constructive.
  Findings + the response to each are recorded in `docs/superpowers/reviews/`.
- **External — `@codex review` on the PR** (step 5) — comment `@codex review`; triage its findings with the
  same rigor (verify before applying — a confident-but-wrong suggestion is not implemented); fix, push, and
  re-request until clean. *(Active once the Codex GitHub App is installed on the org — see SETUP.)*

---

## Branch / PR conventions

- Branch per change: `feat/…`, `fix/…`, `chore/…`, `docs/…`, `spec/…`.
- Small, reviewable PRs. Each PR links its spec and/or plan and fills the PR template.
- **`main` is protected by the CTO merge gate.** The engineering loop pushes branches and opens PRs; it does
  **not** merge to `main`.
- Commits and history carry the project identity only (see the identity boundary note in the repo memory /
  CONTRIBUTING); never a personal name/email.

---

## Definition of Done (a change may merge when…)

1. Spec signed off (for anything non-trivial) and plan reviewed.
2. Tests added and **green**; the app runs and the change is observed to work (not just compiles).
3. The 7 invariants are explicitly checked — none bent (or, if bent, CTO-approved).
4. In-repo fan-out review: clean. `@codex review`: clean (once installed).
5. `/security-review` clean for crypto/protocol/transport changes.
6. PR template complete; review trail recorded.
7. Maintainer approves the merge.

---

## Autonomy, honestly

The engineering loop runs long chains within a session and **polls the PR for the external review verdict in
the background**; it is not unattended-for-days. The Maintainer is pinged at the CTO gates and whenever the
loop is blocked or a 2-round bound is hit. Every "done / passing / fixed" claim is backed by shown evidence.

---

## SETUP — external reviewer (Maintainer task)

`@codex review` requires the **Codex GitHub App** authorized on the `polleneus` org with this repo enabled
(the same setup used on other repos). This needs org-admin and **must be done by the Maintainer** — the
engineering loop cannot install GitHub Apps. Once it's live, the loop drives it via `gh` (open PR, post
`@codex review`, read comments, fix, repeat). Until then, step 5's external channel is **pending** and the PR
is gated by the in-repo fan-out review only.
