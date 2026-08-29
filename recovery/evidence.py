"""EvidenceCollector: gather what the agent sees (events, logs, pod state, diff)."""
from __future__ import annotations
import json

from . import config
from .cluster import kubectl
from .interfaces import EvidenceBundle


def _deployment_status():
    res = kubectl(["get", "deployment", config.APP_NAME, "-o", "json"], quiet=True)
    if not res.ok:
        return {"ready": False, "ready_replicas": 0, "desired": 0,
                "updated_replicas": 0, "stuck_rollout": False}
    d = json.loads(res.out)
    status = d.get("status", {})
    spec = d.get("spec", {})
    desired = spec.get("replicas", 1)
    ready = status.get("readyReplicas", 0)
    updated = status.get("updatedReplicas", 0)
    # Stuck rollout: updated < replicas (new pods aren't replacing old ones)
    stuck = updated < status.get("replicas", 0) if updated > 0 else False
    return {"ready": ready == desired and desired > 0,
            "ready_replicas": ready, "desired": desired,
            "updated_replicas": updated, "stuck_rollout": stuck}


def _pod_reasons() -> list[str]:
    res = kubectl(["get", "pods", "-l", config.APP_LABEL, "-o", "json"], quiet=True)
    reasons: list[str] = []
    if not res.ok:
        return reasons
    pods = json.loads(res.out).get("items", [])
    for p in pods:
        for cs in p.get("status", {}).get("containerStatuses", []):
            waiting = cs.get("state", {}).get("waiting")
            if waiting and waiting.get("reason"):
                reasons.append(waiting["reason"])
        # also surface phase-level trouble
        phase = p.get("status", {}).get("phase")
        if phase and phase not in ("Running", "Succeeded"):
            reasons.append(f"phase:{phase}")
    return reasons


def collect(recent_change: dict) -> EvidenceBundle:
    status = _deployment_status()
    events = kubectl(["get", "events", "--sort-by=.lastTimestamp"], quiet=True).out[-2000:]
    logs = kubectl(["logs", "-l", config.APP_LABEL, "--all-containers",
                    "--tail=30"], quiet=True).out
    return EvidenceBundle(
        deployment=config.APP_NAME,
        namespace=config.NAMESPACE,
        ready=status["ready"],
        replicas_ready=status["ready_replicas"],
        replicas_desired=status["desired"],
        pod_reasons=_pod_reasons(),
        events=events,
        logs=logs,
        recent_change=recent_change,
        updated_replicas=status["updated_replicas"],
        stuck_rollout=status["stuck_rollout"],
    )
