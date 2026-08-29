# DeployGuard-Recovery — Team Guide

*One-day HackSprint (Daytona × Give(a)Go × Baseline). Read this first.*

---

## 1. What we're building (in one paragraph)

A **reliability-training harness for agents**. We take an agent — DeployGuard's
Kubernetes triage brain — put it in a *controlled, broken* Kubernetes cluster,
let it propose a fix, and **objectively verify the fix** (does the Deployment
become `Ready`?). We collect those outcomes, distill them into a learned artifact
(memory / a small classifier), **freeze it**, and prove it fixes *unseen* failure
types better than baselines. Think "driving school for agents": we don't build the
agent, we make an existing one measurably more reliable under failure.

## 2. Why this wins this event

- **Measurable & visible.** Success is a stopwatch-simple fact: cluster goes green
  or it doesn't. Great live demo.
- **Proves real learning.** Train on faults 1–N → freeze → beat baselines on an
  *unseen* fault. That's the exact thing the event asks for and most teams won't have.
- **Daytona is essential, not decorative.** Fork = identical starting clusters;
  snapshot = deterministic replay; parallel isolated rollouts. Can't do it rigorously
  without them → the sponsor story writes itself.
- **Reuses our own work** (DeployGuard) → also moves our Aug 31 deadline forward.

**Objections we pre-empt:**
- *"It's just a k8s linter / k8sgpt."* → We **verify** the fix works and **learn**
  from outcomes with a held-out eval; diagnosis tools don't.
- *"Your results are noise."* → Daytona fork gives identical baselines; we report
  success + safety across repeated, seeded runs.
- *"You optimized one case."* → Frozen policy evaluated on an unseen failure type.

## 3. The general framework (our real contribution)

Only two parts change per agent; the core never does:

| Fixed core (the framework) | Swappable per agent (thin adapters) |
|---|---|
| Orchestrator (runs laps) | **Environment adapter**: how to break it + gather evidence + check success |
| Learning loop (distill/freeze/eval) | **Agent adapter**: `reason(evidence) -> fix` |
| Daytona harness (isolation/replay) | |

Same harness, different agents:

| Agent | Environment | Break it with | Success check |
|---|---|---|---|
| **DeployGuard** (ours) | kind cluster | bad image, missing secret, OOM… | Deployment `Ready` |
| Coding/bug-fix agent | a repo | inject a failing bug | tests pass |
| API/data agent | mock service + DB | timeout-after-success, partial write | state consistent |

We build **only the DeployGuard adapter** today; we *pitch* the generality.

## 4. Architecture

```
 ORCHESTRATOR (local)  ──create/fork/snapshot──▶  DAYTONA SANDBOX (DinD)
   drives laps, logs                              ┌────── FAILURE GYM (kind) ──────┐
        ▲                                         │ fault injector ─▶ broken deploy │
        │ metrics                                 │                     │ evidence  │
        │                                         │              evidence collector │
        │                                         └───────────────┬─────────────────┘
        │                                                         ▼
        │                                   AGENT (DeployGuard brain)
        │                                   gather ▶ reason (LLM) ▶ memory ▶ propose fix
        │                                                         ▼
        │                                   SCORER: apply fix ▶ Ready? ▶ success 0/1
        │                                                         │      + safety flags
        └──────────────── LEARNED ARTIFACT ◀── distill ──────────┘
                          (memory / classifier) ──FREEZE──▶ EVAL on UNSEEN fault
                          baseline vs one-shot vs frozen agent
```

## 5. Current status (already built & verified ✅)

The keyless 80% runs on **local podman + kind** with a rule-based mock brain:

- ✅ kind cluster on podman + healthy app
- ✅ fault injector: `bad_image`, `missing_secret`
- ✅ evidence collector (events, logs, pod state, shipped diff)
- ✅ scorer: `apply_fix` + `check_success` + safety flags — **verified it fails on
  unfixed faults** (real reward signal)
- ✅ mock brain (rule-based) → correctly triages both faults
- ✅ full lap end-to-end: both faults recover, SUCCESS=True
- ✅ fixtures captured (fallback dataset + clusterless `replay`)

## 6. Quickstart (get running in 5 min)

Prereqs: `podman` (with machine started), `kind`, `kubectl`, python 3.11+.

```bash
export PATH="/opt/homebrew/bin:$PATH"   # so kind is found
podman machine start                    # if not running

cd deployguard-recovery
python3 main.py setup                    # cluster + healthy app
python3 main.py lap --fault bad_image    # full lap: inject -> fix -> score
python3 main.py lap --fault missing_secret
python3 main.py capture                  # save evidence fixtures
python3 main.py replay --fault bad_image # run brain on fixture (NO cluster needed)
python3 main.py teardown                 # delete cluster
```

## 7. The two seams (where keys plug in later)

Change **only these two files** when keys arrive — nothing else moves:

- **Seam 1 — the brain** (`recovery/llm_mock.py`): write `GeminiClient`/`ClaudeClient`
  implementing `LLMClient.reason(evidence) -> Fix`. Mock stays as the rule-based baseline.
- **Seam 2 — where the Gym runs** (`recovery/cluster.py`): write `DaytonaRunner` with
  the same interface as `KindRunner`, running kind inside a Daytona DinD sandbox + fork/snapshot.

## 8. Build plan & task split

Build window is short — **get one full lap solid before anything fancy** (already done ✅).

### Owner A — Environment / Daytona
- [ ] Add faults: `oom_kill`, `bad_readiness_probe`, `wrong_config_value`
- [ ] (on key) Write `DaytonaRunner` (Seam 2): kind-in-DinD + fork per lap + snapshot replay
- [ ] Parallelize laps across forked sandboxes

### Owner B — Agent / Learning
- [ ] (on key) Write `GeminiClient`/`ClaudeClient` (Seam 1); parse LLM JSON → `Fix`
- [ ] Build the learned artifact: incident-memory store the brain consults
- [ ] (stretch) small root-cause classifier trained on `runs/` records
- [ ] Freeze the artifact; confirm success rate rises on training faults

### Owner C — Eval / Demo
- [ ] Baselines: rule-based (mock), one-shot LLM, DeployGuard-no-memory
- [ ] Held-out eval: pick ONE unseen fault; run all systems on same snapshots
- [ ] Results table + Pareto (success vs safety)
- [ ] Live demo script + the "two-look-alike-faults, opposite-fixes" moment
- [ ] 2 slides (problem + method); rehearse twice

## 9. Definition of done (milestones that matter)
1. ✅ One full lap runs and scores objectively.
2. ⬜ Real LLM brain + ≥4 fault types.
3. ⬜ Learned artifact frozen; beats its earlier self on training faults.
4. ⬜ Held-out eval: frozen agent beats baselines on an **unseen** fault.
5. ⬜ 3-minute demo rehearsed.

## 10. Risks & fallbacks
- **kind/Daytona flaky on demo day** → use recorded `fixtures/` + `replay` (clusterless).
- **Behind on time** → cut Daytona (demo on local kind), cut classifier (use memory only),
  cut to one unseen *fault* instead of a whole unseen task. Keep the held-out eval no matter what.
- **LLM key delayed** → the rule-based brain already runs the whole pipeline; it's the baseline anyway.

## 11. Fix schema (contract between brain and scorer)
```python
Fix(action, target, params, rationale, claims_fixed)
# actions today: rollback_image | set_image | create_secret | noop | escalate
# claims_fixed=False when the agent escalates instead of guessing (safety-honest)
```
Whatever the real LLM outputs must map to this. Unknown symptom → `escalate` with
`claims_fixed=False` (never fake a fix — that trips the false-claim safety flag).
