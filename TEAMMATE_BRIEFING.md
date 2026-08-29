# DeployGuard-Recovery — Teammate Briefing

*Read this first. 5-minute brief on what we're building and why it wins.*

---

## The Elevator Pitch (30 seconds)

We're building a **reliability-training harness for agents**. We take DeployGuard's
K8s triage brain, put it in controlled failure scenarios, verify its fixes objectively
(does the cluster actually recover?), learn from successful outcomes, freeze the
learned artifact, and **prove** it generalizes to unseen failures better than
rule-based systems or one-shot LLM reasoning.

Think: "driving school for agents" — we don't build the agent, we make an existing
one measurably more reliable.

---

## The Problem We're Solving

### Current State (what's broken today)

**Agents fail when their environment fails.** When a Kubernetes deployment breaks,
GitHub Actions times out, or an API returns an ambiguous error, agents don't have
a principled way to recover. They either:

1. **Retry blindly** → create duplicates, corrupt state, or waste budget
2. **Hallucinate success** → claim they fixed it when they didn't
3. **Escalate/give up** → "I don't know, ask a human"

No production agent framework (LangGraph, AutoGen, OpenAI Agents SDK, CrewAI) ships
a *learned* recovery policy. They all use dumb retries and hand-written guardrails.

### How It's "Solved" Today (the gap we exploit)

| Approach | How it works | Limitation |
|---|---|---|
| **Rule-based systems** (k8sgpt, runbooks) | Pattern-match symptoms → known fixes | Brittle: unseen symptom → fails or escalates |
| **One-shot LLM reasoning** | Feed evidence to LLM, ask for a fix | No memory of past incidents; reinvents the wheel |
| **Diagnosis-only tools** (k8sgpt, Komodor) | Explain what's wrong | Don't verify fixes or learn from outcomes |

None of these **learn from measured outcomes**. If a fix worked yesterday, there's
no retained knowledge. If it failed, no record to avoid it next time.

---

## Our Solution (what makes it better)

### The Architecture (what we built)

```
 Orchestrator  ──create/fork──▶  Daytona Sandbox (isolated, reproducible)
    drives                        ┌─── Failure Gym (kind cluster) ────┐
    train +                       │  inject fault → broken deployment  │
    eval loops                    │        ↓ gather evidence            │
      ▲                           │  Agent reasons → proposes fix       │
      │                           │        ↓ apply + verify             │
      │                           │  Scorer: cluster Ready? → 0/1       │
      │                           └────────┬────────────────────────────┘
      │                                    │ (evidence, fix, outcome)
      └────── Learned Artifact ◀── distill┘
           (incident memory)      ──FREEZE──▶ Eval on UNSEEN fault
```

### The Training Loop (how the agent improves)

1. **Train:** Run the agent on 3 known faults (bad image, missing secret, OOMKill).
   Each time it successfully fixes one, record the symptom fingerprint + the fix
   that worked into **incident memory**.

2. **Freeze:** Lock the memory. No more writes. This is the learned artifact.

3. **Evaluate:** Run three systems on an **unseen** fault (bad readiness probe):
   - **A.** Rule-based brain, no memory
   - **B.** One-shot LLM, no memory
   - **C.** Memory-augmented agent (frozen artifact)

4. **Prove:** If C beats A and B on fix-success rate + safety (no false claims),
   learning is proven — it generalized to a failure it never trained on.

### Why This Is Genuine Learning (what you say to judges)

> "We didn't hand-write a rule for the readiness-probe fault. The agent had never
> seen it during training. But because the memory captured the *pattern* — 'when
> pods are running but not Ready, check what changed in the shipped diff' — it
> applied that knowledge to the new fault. That's generalization from a frozen
> artifact, not overfitting."

---

## The Three Innovations (why it's not just another tool)

### 1. It's a Framework, Not a Single-Purpose Agent

Only two adapters change per agent type; the core never does:

| Agent Type | Environment | How to Break It | Success Check |
|---|---|---|---|
| **DeployGuard** (ours) | kind K8s cluster | bad image, OOM, probe fail | Deployment Ready |
| Coding/bug-fix agent | repo + tests | inject failing test | tests pass |
| API/data agent | mock service + DB | timeout, partial write | state consistent |

Same orchestrator, learning loop, and Daytona harness. We demo K8s; we *pitch*
the generality.

### 2. Measured Learning with Held-Out Eval

We don't claim "it got better" — we **prove it**:
- Freeze the artifact so it can't be tuned against the eval set
- Evaluate on an unseen failure
- Report fix-success **and** safety violations (false claims, destructive actions)

Most hackathon projects will train and eval on the same data, or claim improvement
without a credible baseline. We have both.

### 3. Daytona Makes the Experiment Honest

- **Fork** = every candidate fix runs on an identical starting cluster (kills "noise")
- **Snapshot** = deterministic replay of the exact broken state
- **Isolation** = parallel rollouts don't contaminate each other

Without Daytona's primitives, "the agent improved" is an unverifiable claim. With
them, it's reproducible science. That's the sponsor story judges reward.

---

## Current Status

**Built & verified (keyless, on podman/kind):**
- ✅ Failure Gym with 4 faults (bad image, missing secret, OOM, bad readiness probe)
- ✅ Scorer with objective reward (cluster Ready?) + safety flags
- ✅ Training loop (6/6 laps pass, 3 memory entries distilled)
- ✅ Frozen artifact
- ✅ Held-out eval infrastructure
- ✅ `verify.py` self-check

**Pending (needs keys tomorrow):**
- ⬜ Swap in real LLM (Gemini/Claude) — Seam 1, ~30 min
- ⬜ Daytona fork/snapshot integration — Seam 2, ~1 hr
- ⬜ Demo rehearsal + slides

**The gate:** `python3 verify.py --live` must be green before we demo.

---

## How to Explain the Value Prop

### To a Technical Judge
"We built a training harness that takes any agent with a verifiable success condition,
runs it through controlled failures in isolated Daytona sandboxes, distills successful
outcomes into a learned artifact, freezes it, and proves generalization with a
held-out eval. The K8s agent is our demo; the framework is the contribution."

### To a Business Judge
"Agents fail in production because they can't learn from past incidents. We train
them to recover reliably, measure the improvement objectively, and prove it works
on failures they've never seen. Daytona makes the whole experiment reproducible."

### To the Sponsor (Daytona)
"This project is impossible without your primitives. Fork gives us identical baselines
for fair comparison. Snapshot lets us replay the exact failure deterministically.
Isolation means we can run hundreds of parallel experiments safely. You're not
decorative — you're the foundation."

---

## The Demo Script (3 minutes)

1. **The failure** (30s): `python3 main.py lap --fault bad_image` — show a recovery.
2. **Training** (30s): `python3 main.py train --laps 2` — 6 laps, memory grows.
3. **Freeze** (10s): `python3 main.py freeze` — lock the artifact.
4. **Proof** (60s): `python3 main.py eval` — 3 systems, unseen fault, results table.
5. **Mic drop** (30s): Memory agent beats baselines; mention the general framework.

**Fallback if cluster breaks:** `python3 main.py replay --fault X` — brain reasons
live on saved fixtures, no cluster needed.

---

## Objections We Pre-Empt

| Objection | Our Answer |
|---|---|
| "This is just k8sgpt / a diagnosis tool" | "We **verify** fixes and **learn** from outcomes with held-out eval. k8sgpt only diagnoses." |
| "Your results are noise" | "Daytona fork = identical baselines; snapshot = deterministic replay; we report success + safety over repeated runs." |
| "You optimized one case" | "Frozen artifact evaluated on an **unseen** fault it never trained on." |
| "This is middleware / retry logic" | "We make **semantic** decisions the cluster state, not status codes. Two faults can return the same error but need opposite fixes — the memory agent gets both right." |

---

## What You Should Know for Tomorrow

1. **Keys first** — get Daytona + LLM keys at 11:30 as job #1.
2. **The non-negotiable** — held-out eval + frozen artifact. Cut Daytona live if tight on time; never cut the learning proof.
3. **The pre-demo gate** — `verify.py --live` must be green.
4. **The fallback** — if cluster misbehaves, `replay` runs the brain on fixtures with no infra.

---

*See `TEAM_GUIDE.md` for task split and build plan.*
