# DeployGuard-Recovery — Demo & Proof

**Daytona × Give(a)Go × Baseline HackSprint — Dublin, August 2026**

A reliability-training harness that teaches an agent to recover from **real Kubernetes
failures** and **proves it learned**, running real K8s inside **Daytona sandboxes**.

---

## What it does (30 seconds)

1. Inject a real failure into a live Kubernetes deployment (bad image, missing secret,
   OOMKill, broken readiness probe, bad command).
2. The agent gathers evidence (pod state, events, logs, the shipped diff) and proposes a fix.
3. We **objectively verify** the fix — did the Deployment reach `Ready`? (0/1, plus safety flags).
4. Successful fixes are distilled into a **frozen incident memory** (the learned artifact).
5. We **prove learning** by evaluating on an **unseen** failure vs. baselines.

The learning loop is domain-agnostic — any agent with a checkable success condition
plugs in via two adapters (Environment + Agent).

---

## PROOF 1 — Real Kubernetes running inside Daytona (headline)

kind (full K8s) can't run in Daytona's container-class sandbox (its node is a privileged
nested container that must create device nodes — blocked by the sandbox security profile).
We solved it by running **k3s**, which runs pods at the same depth as a normal container.

**A complete incident, end-to-end, on real k3s inside a Daytona sandbox:**

```
=== LAP: bad_image ===
[daytona] creating sandbox (docker:28.3.3-dind) ...
[daytona] uploading k3s binary ...
[daytona] bootstrapping (k3s server) ...
[daytona] real Kubernetes (k3s) ready inside sandbox
[daytona] applying healthy app
  [daytona] $ k3s kubectl apply -f - (via /tmp/manifest.yaml)
  [daytona] $ k3s kubectl rollout status deployment/web --timeout=60s
[inject] breaking the deployment
  [daytona] $ k3s kubectl set image deployment/web web=nginx:9.9.9-doesnotexist
[evidence] gathering
  pod_reasons=['ErrImagePull', 'phase:Pending'] ready=True
[agent] reasoning
  fix=rollback_image rationale='Image pull failing; roll back to last-known-good image...'
[apply] applying fix
  [daytona] $ k3s kubectl set image deployment/web web=nginx:1.27-alpine
[score] verifying
  SUCCESS=True safety={'false_claim': False, 'wrong_target': False, 'destructive': False}

[result] fault=bad_image success=True safety={...all False}
```

Run it yourself:
```bash
export DAYTONA_API_KEY=... DAYTONA_TARGET=eu
python3 main.py lap --fault bad_image --sandbox daytona --llm gemini
```

---

## PROOF 2 — The reward signal is real (not rigged)

The scorer verifies the actual cluster, so **unfixed faults score as failure** and
**fixed faults score as success** — this is what makes "it improved" a credible claim.

```
unfixed bad_image      -> success = False
unfixed missing_secret -> success = False
lap bad_image          -> success = True   (agent rolled back the image)
lap missing_secret     -> success = True   (agent created the secret)
```

---

## PROOF 3 — Learning: training builds a frozen memory artifact

```
TRAINING FAULT: bad_image        -> rollback_image   ✓ success — recorded to memory
TRAINING FAULT: missing_secret   -> create_secret    ✓ success — recorded to memory
TRAINING FAULT: oom_kill         -> fix_memory_limit ✓ success — recorded to memory

[train] done — {'total': 6, 'success': 6, 'fail': 0, 'memory_entries': 3}
[memory] FROZEN — 3 entries written to memory/incidents_frozen.json
```

Frozen artifact (`memory/incidents_frozen.json`) — a symptom fingerprint → proven fix:
```json
{ "fingerprint": {"pod_reasons": ["ErrImagePull"], "change_kind": "image_update"},
  "fix_action": "rollback_image",
  "fix_params": {"image": "nginx:1.27-alpine"} }
```

---

## PROOF 4 — Real LLM reasoning (Gemini)

Gemini reads the evidence and reasons a fix (not pattern-matching):

```
[gemini] raw response: {"action": "rollback_image", "target": "web",
  "params": {"image": "nginx:1.27-alpine"}, ...}
=> action: rollback_image
   rationale: "The new image 'nginx:9.9.9-doesnotexist' caused ErrImagePull because
   it does not exist; reverting to the previously working image will resolve the issue."
```

---

## PROOF 5 — Held-out evaluation (proving generalization)

Three systems run on the **same** cluster state, on a fault held out of training:

- **A. Rule-based** (no memory)
- **B. One-shot LLM** (Gemini, no memory)
- **C. Memory-augmented agent** (frozen artifact + LLM fallback)

The `bad_command` fault is the held-out differentiator: it has **no rule branch**, so the
rule baseline (A) escalates/fails, while the LLM (B/C) must *reason* a fix — this is what
breaks the A=B=C tie and shows the value of learning. Metrics captured per system:
success rate, false-claim rate, avg latency, and token cost. Results save to
`eval/results_<fault>.json`.

```bash
python3 main.py train --laps 2 --llm mock     # build memory (free)
python3 main.py freeze
python3 main.py eval --laps 1 --llm gemini     # ~2 API calls; shows A fail, B/C reason a fix
```

---

## Why Daytona is essential (not decorative)

- **Isolation** — each incident runs in a disposable cloud sandbox, not a shared machine.
- **Fork** — clone an identical starting cluster per candidate fix → fair comparison.
- **Snapshot** — replay the exact broken state deterministically (kills "results are noise").
- **Safety** — AI-generated fixes run in a throwaway box, never against real infra.

This experiment is impossible to run rigorously without Daytona's fork/snapshot primitives.

---

## Architecture (fixed core + two adapters)

```
Orchestrator ── create/fork/snapshot ──▶ Daytona Sandbox (k3s = real Kubernetes)
   drives                                 ┌── Failure Gym ──┐
   train + eval                           │ inject → broken  │
      ▲                                   │  ↓ evidence      │
      │ metrics                           │ Agent → fix      │
      │                                   │  ↓ apply+verify  │
      └── Learned Memory ◀── distill ─────┘ Scorer: Ready? 0/1 + safety
          (frozen) ──▶ Held-out Eval: A (rules) vs B (LLM) vs C (memory+LLM)
```

Swap two adapters and the same harness trains a coding agent (repo + tests), an API
agent (mock service + DB), or a browser agent — the learning is domain-agnostic.

---

## Run it

```bash
# Local (real K8s via kind on podman) — full learning loop
python3 verify.py --live          # self-check gate
python3 main.py setup
python3 main.py train --laps 2 --llm mock
python3 main.py freeze
python3 main.py eval --laps 1 --llm gemini

# Daytona (real K8s via k3s in an isolated cloud sandbox)
export DAYTONA_API_KEY=... DAYTONA_TARGET=eu
python3 main.py lap --fault bad_image --sandbox daytona --llm gemini
```

**Repo:** https://github.com/omkarjoshi0304/deployguard-recovery
