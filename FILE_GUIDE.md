# DeployGuard-Recovery — Complete File Guide

Every file in the project, organized by purpose.

---

## 📋 Entry Points & Documentation

### `main.py`
**Purpose:** Command-line interface — the main entry point for all operations.

**Commands:**
- `setup` — create kind cluster + deploy healthy app
- `lap --fault X` — run one full incident (inject → reason → fix → score)
- `train` — training loop on all training faults
- `freeze` — lock the memory artifact (run once after train)
- `eval` — held-out evaluation (3 systems on unseen fault)
- `capture` — save evidence fixtures for offline dev
- `replay --fault X` — run brain on saved fixture (no cluster needed)
- `teardown` — delete the cluster

**You run this every time you interact with the harness.**

---

### `verify.py`
**Purpose:** Self-check script — verifies all invariants before demo.

**Two modes:**
- `python3 verify.py` — fast, clusterless checks (brain logic, schema)
- `python3 verify.py --live` — full-stack checks (cluster, laps, memory)

**Pre-demo gate:** This must be green before you walk on stage.

---

### `README.md`
**Purpose:** Quickstart guide for getting the harness running.

**Contains:** Prerequisites, commands, the two-seam architecture, build order.

---

### `TEAM_GUIDE.md`
**Purpose:** Build plan & task split for the team.

**Contains:** What we're building (1-paragraph), why it wins, architecture, current status, task split (Owner A/B/C), milestones, risks & fallbacks.

**Hand this to teammates when they join.**

---

### `TEAMMATE_BRIEFING.md`
**Purpose:** Full explanation of the problem, solution, and value prop.

**Contains:** Problem statement, how it's solved today (the gap), our 3 innovations (framework / held-out eval / Daytona), demo script, objections we pre-empt.

**Use this to explain the project to anyone — judges, teammates, sponsors.**

---

## 🧠 Core Harness (recovery/ package)

### `recovery/__init__.py`
**Purpose:** Empty package marker (makes `recovery/` a Python module).

---

### `recovery/config.py`
**Purpose:** Central constants shared across the harness.

**Key values:**
- `CLUSTER_NAME`, `CONTEXT` — kind cluster naming
- `GOOD_IMAGE` — known-healthy nginx image
- `FAULTS` — all 4 fault types
- `TRAINING_FAULTS` — faults used in training (excludes held-out)
- `HELD_OUT_FAULT` — the unseen fault for eval (`bad_command`)

**Change this file to add faults or change the held-out selection.**

---

### `recovery/interfaces.py`
**Purpose:** Stable contracts (data classes + abstract interfaces).

**Key types:**
- `EvidenceBundle` — what the agent sees (pod state, events, logs, diff)
- `Fix` — structured action the agent proposes
- `IncidentResult` — scored outcome of one lap
- `LLMClient` (abstract) — **Seam 1**: swap mock → real LLM here
- `SandboxRunner` (abstract) — **Seam 2**: swap local kind → Daytona here

**These interfaces never change; only their implementations swap.**

---

### `recovery/sh.py`
**Purpose:** Thin subprocess wrapper so every shell call is logged and consistent.

**Why:** Avoids repetitive `subprocess.run()` boilerplate; makes debugging easier.

---

## 🔧 The Failure Gym

### `recovery/cluster.py`
**Purpose:** **Seam 2 implementation** — runs the kind cluster locally (via podman).

**Key class:** `KindRunner(SandboxRunner)`
- `ensure_up()` — create the cluster if it doesn't exist
- `deploy_healthy()` — apply the known-good nginx deployment
- `reset_app()` — delete + redeploy to a clean baseline (cheap snapshot restore)
- `teardown()` — delete the cluster

**Helper:** `kubectl(args)` — runs kubectl with the right context.

**To swap to Daytona:** write `DaytonaRunner(SandboxRunner)` with the same interface; run kind *inside* a Daytona DinD sandbox and add fork/snapshot.

---

### `recovery/faults.py`
**Purpose:** Fault injector — breaks the deployment in defined, repeatable ways.

**Faults implemented:**
1. `bad_image` — invalid image tag → `ImagePullBackOff`
2. `missing_secret` — references a secret that doesn't exist → `CreateContainerConfigError`
3. `oom_kill` — memory limit too low (4Mi) → `OOMKilled` / `CrashLoopBackOff`
4. `bad_readiness_probe` — probe checks a nonexistent path → stuck rollout

**Returns:** `recent_change` dict (the diff that shipped) — legitimate evidence the agent sees.

**To add a fault:** write `_new_fault()`, add to `inject()` switch, update `config.FAULTS`.

---

### `recovery/evidence.py`
**Purpose:** Evidence collector — gathers what the agent sees.

**Collects:**
- Deployment status (ready, replicas, updated replicas, stuck rollout)
- Pod reasons (ImagePullBackOff, OOMKilled, etc.)
- Recent events (sorted by timestamp)
- Container logs (last 30 lines)
- The shipped diff (from the fault injector)

**Returns:** `EvidenceBundle` — everything the agent reasons from.

---

### `recovery/scorer.py`
**Purpose:** Applies a fix, verifies it objectively, and checks safety.

**Key functions:**
- `apply_fix(fix)` — translates structured Fix → kubectl commands
- `check_success()` — waits for deployment to become Ready (0 or 1)
- `safety_flags(fix, success)` — checks false_claim, wrong_target, destructive

**Why it matters:** This is the **objective reward signal** — not a vibe, a measured fact.

---

## 🤖 The Brains

### `recovery/llm_mock.py`
**Purpose:** **Seam 1 implementation** — rule-based brain (the baseline).

**Key class:** `RuleBasedLLM(LLMClient)`
- Pattern-matches pod reasons + the shipped diff → proposes a fix
- Escalates on unknown symptoms (with `claims_fixed=False` for safety)

**Triple duty:**
1. Lets the whole pipeline run with zero API keys
2. Becomes the **rule-based baseline** in the final eval
3. Documents the exact `Fix` schema the real LLM must produce

**To swap in real LLM:** write `GeminiClient(LLMClient)` or `ClaudeClient(LLMClient)` implementing `reason(evidence) -> Fix`.

---

### `recovery/memory.py`
**Purpose:** Incident memory store — the learned artifact.

**Key functions:**
- `record_success(evidence, fix)` — appends to active memory
- `recall(evidence, frozen=False)` — fuzzy-match lookup (similarity scoring)
- `freeze()` — copy active → frozen (locks the artifact)
- `load(frozen=False)` — read memory entries

**Structure:** Each entry is `{fingerprint, fix_action, fix_params, rationale}`.
- Fingerprint = `{pod_reasons, change_kind, ready}` — a matchable symptom signature
- Similarity scoring (0.0–1.0) lets the agent apply a learned fix to a *similar* new case

**Files:**
- `memory/incidents.json` — active (writable during training)
- `memory/incidents_frozen.json` — frozen (read-only in eval)

---

### `recovery/memory_brain.py`
**Purpose:** Memory-augmented agent — the improved brain.

**Key class:** `MemoryBrain(LLMClient)`
1. Check frozen memory for a similar past incident (similarity ≥ threshold)
2. If hit → return the remembered fix instantly
3. If miss → fall back to the base LLM (mock or real)

**This is System C in the eval** — the agent that uses the frozen artifact.

---

## 🔄 The Learning Loop

### `recovery/orchestrator.py`
**Purpose:** Runs one full lap and logs the result.

**Key function:** `run_lap(fault)`
1. Reset cluster to clean baseline
2. Inject the fault
3. Collect evidence
4. Agent reasons → proposes fix
5. Apply fix
6. Score (success 0/1 + safety flags)
7. Log to `runs/`

**This is the atomic unit of the harness** — everything else chains laps.

---

### `recovery/trainer.py`
**Purpose:** Training loop — runs N laps on training faults, distills memory.

**Key functions:**
- `train(laps_per_fault=3)` — runs laps on `TRAINING_FAULTS`, records successes
- `freeze_memory()` — locks the artifact (call once after train)

**Returns:** summary dict (total, success, fail, memory_entries)

**Output:** Writes to `memory/incidents.json` (active memory).

---

### `recovery/evaluator.py`
**Purpose:** Held-out evaluation — compares 3 systems on the unseen fault.

**Key function:** `evaluate(held_out_fault, laps=3)`

**Three systems under test:**
- **A.** Rule-based (no memory) — `RuleBasedLLM()`
- **B.** One-shot LLM (no memory) — base LLM (mock or real)
- **C.** Memory agent (frozen) — `MemoryBrain()` reading frozen memory

**All three run on identical cluster resets** (same starting state).

**Output:**
- Prints a table: System | Success | False claim
- Saves to `eval/results_{fault}.json`

---

## 📦 Data / Artifacts

### `fixtures/*.json`
**Purpose:** Saved evidence bundles for clusterless dev & demo fallback.

**Created by:** `python3 main.py capture`

**Used by:** `python3 main.py replay --fault X` — runs the brain on a saved fixture with no cluster.

**Example:** `fixtures/bad_image.json` contains the full `EvidenceBundle` for a bad-image failure (pod reasons, events, logs, diff).

**Why it matters:** If the cluster misbehaves on demo day, `replay` lets the brain reason live on fixtures — no infra needed.

---

### `runs/*.json`
**Purpose:** Logged results from every lap.

**Created by:** `orchestrator.py` after each lap.

**Structure:** `IncidentResult` — fault, fix, success, safety, evidence, notes.

**Filename format:** `0000_bad_image_ok.json` (sequence, fault, outcome).

**Example:**
```json
{
  "fault": "bad_image",
  "fix": {"action": "rollback_image", "params": {"image": "nginx:1.27-alpine"}},
  "success": true,
  "safety": {"false_claim": false, "wrong_target": false, "destructive": false},
  "evidence": {...},
  "notes": "set image -> nginx:1.27-alpine"
}
```

**Why it matters:** This is your training dataset. You could train a classifier on these records (stretch goal).

---

### `memory/incidents.json`
**Purpose:** Active memory — writable during training.

**Structure:** Array of `{fingerprint, fix_action, fix_params, rationale}`.

**Created by:** `trainer.py` calling `memory.record_success()` after each successful lap.

**Example:**
```json
{
  "fingerprint": {"pod_reasons": ["ErrImagePull"], "change_kind": "image_update"},
  "fix_action": "rollback_image",
  "fix_params": {"image": "nginx:1.27-alpine"},
  "rationale": "Image pull failing; roll back to last-known-good image."
}
```

**Why it matters:** This is the **learned artifact** while it's still being built.

---

### `memory/incidents_frozen.json`
**Purpose:** Frozen memory — read-only snapshot after training.

**Created by:** `python3 main.py freeze` (copies active → frozen).

**Used by:** `MemoryBrain(frozen=True)` in the held-out eval.

**Why it matters:** Freezing prevents hand-tuning against the eval set — makes the learning claim credible.

---

### `eval/results_{fault}.json`
**Purpose:** Held-out eval results — the proof of learning.

**Created by:** `evaluator.py`.

**Structure:** `{"fault": "...", "results": [...]}`
- Each result: system, fault, action, success, safety, rationale

**Example:** 9 entries (3 laps × 3 systems) all on `bad_command`.

**Why it matters:** This is your **results table for the demo** — shows all 3 systems side-by-side.

---

## 📊 Summary Table

| File/Dir | Purpose | When You Touch It |
|---|---|---|
| `main.py` | CLI entry point | Every command you run |
| `verify.py` | Self-check gate | Before demo, after changes |
| `README.md` | Quickstart | Share with teammates |
| `TEAM_GUIDE.md` | Build plan | Share with teammates |
| `TEAMMATE_BRIEFING.md` | Full explanation | Explain to anyone |
| **Core Harness** | | |
| `recovery/config.py` | Constants (faults, cluster name) | Add faults, change held-out |
| `recovery/interfaces.py` | Stable contracts (the 2 seams) | Almost never |
| `recovery/sh.py` | Shell wrapper | Never |
| **Failure Gym** | | |
| `recovery/cluster.py` | Seam 2: local kind → Daytona | Swap for Daytona tomorrow |
| `recovery/faults.py` | Fault injector | Add new fault types |
| `recovery/evidence.py` | Evidence collector | Add new evidence signals |
| `recovery/scorer.py` | Apply + verify + safety | Add new fix actions |
| **Brains** | | |
| `recovery/llm_mock.py` | Seam 1: rule-based → real LLM | Swap for Gemini/Claude tomorrow |
| `recovery/memory.py` | Incident memory store | Tune similarity threshold |
| `recovery/memory_brain.py` | Memory-augmented agent | Almost never |
| **Learning Loop** | | |
| `recovery/orchestrator.py` | One full lap | Almost never |
| `recovery/trainer.py` | Training loop | Tune laps_per_fault |
| `recovery/evaluator.py` | Held-out eval | Almost never |
| `recovery/fixtures.py` | Capture/replay | Add new faults |
| **Data / Artifacts** | | |
| `fixtures/*.json` | Saved evidence (fallback) | After `capture` |
| `runs/*.json` | Logged lap results | Auto-generated |
| `memory/incidents.json` | Active memory | Auto-generated during train |
| `memory/incidents_frozen.json` | Frozen artifact | After `freeze` |
| `eval/results_*.json` | Eval results (the proof) | After `eval` |

---

## The Two Files You Swap Tomorrow

| Seam | File | Today | Tomorrow (with keys) |
|---|---|---|---|
| **Seam 1** | `recovery/llm_mock.py` | Rule-based brain | `GeminiClient` / `ClaudeClient` |
| **Seam 2** | `recovery/cluster.py` | Local kind | `DaytonaRunner` (kind-in-DinD + fork/snapshot) |

Everything else is already done and verified.
