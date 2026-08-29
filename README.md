# DeployGuard-Recovery

A reliability-training harness for agents. We take an agent (DeployGuard's triage brain),
put it in a controlled Kubernetes failure, let it propose a fix, **verify the fix objectively**
(does the Deployment become Ready?), and learn from the outcome — then prove it generalizes
to unseen failures.

This repo is the **keyless 80%**: everything runs on local `podman` + `kind` with a
rule-based mock brain. When API keys arrive you swap two modules:

- `recovery/llm_mock.py`  -> real Gemini/Claude (interface: `recovery/interfaces.py:LLMClient`)
- local `kind`            -> Daytona sandbox (interface: `recovery/interfaces.py:SandboxRunner`)

Nothing else changes.

## The two seams
| Seam | Today (keyless) | Later (with keys) |
|------|-----------------|-------------------|
| `LLMClient.reason(evidence) -> Fix` | rule-based (`llm_mock.py`) | Gemini AI Studio / Claude |
| `SandboxRunner` (runs the Gym) | local kind via podman (`cluster.py`) | Daytona fork/snapshot |

## Prerequisites
- podman (with a running machine)
- kind  (`brew install kind`)
- kubectl
- python 3.11+

```bash
podman machine start           # if not already running
kind version                   # confirm installed
```

## Commands
```bash
python3 main.py setup                  # create kind cluster + deploy healthy app
python3 main.py lap --fault bad_image  # one full lap: inject -> triage -> fix -> score
python3 main.py lap --fault missing_secret
python3 main.py capture                # save evidence bundles to fixtures/ (fallback dataset)
python3 main.py replay --fault bad_image   # run the brain on a saved fixture (no cluster needed)
python3 main.py teardown               # delete the cluster
```

## Build order (keyless steps)
1. Toolchain (podman/kind/kubectl) ✅ prerequisites
2. Failure Gym — `cluster.py`, `faults.py`, `evidence.py`
3. Scorer — `scorer.py`
4. Mock brain — `llm_mock.py`
5. Orchestrator — `orchestrator.py` (one full lap)
6. Capture fixtures — `fixtures.py`
