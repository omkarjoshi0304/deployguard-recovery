"""The stable contracts. Everything else is an implementation detail behind these.

Two seams you swap when keys arrive:
  - LLMClient      : mock rule-based -> real Gemini/Claude
  - SandboxRunner  : local kind      -> Daytona fork/snapshot
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any


# ---- Data passed between components -----------------------------------------

@dataclass
class EvidenceBundle:
    """What the agent 'sees'. Mirrors what DeployGuard gathers in production."""
    deployment: str
    namespace: str
    ready: bool
    replicas_ready: int
    replicas_desired: int
    pod_reasons: list[str]          # e.g. ["ImagePullBackOff"], ["CreateContainerConfigError"]
    events: str                     # recent k8s events text
    logs: str                       # container logs (may be empty if it never started)
    recent_change: dict[str, Any]   # the diff that shipped (legit evidence)
    updated_replicas: int = 0       # how many pods on the new spec (for rollout detection)
    stuck_rollout: bool = False     # updated < replicas (old pods still serving, new ones stuck)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "EvidenceBundle":
        return EvidenceBundle(**d)


@dataclass
class Fix:
    """A structured, machine-applyable action the agent proposes."""
    action: str                     # rollback_image | set_image | create_secret | noop | escalate
    target: str                     # deployment name
    params: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    claims_fixed: bool = True       # did the agent assert this resolves it? (for false-claim safety)
    tokens: int = 0                 # LLM tokens spent producing this fix (0 for rule/memory)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IncidentResult:
    fault: str
    fix: dict
    success: bool
    safety: dict                    # {false_claim, wrong_target, destructive}
    evidence: dict
    notes: str = ""
    latency_s: float = 0.0          # wall-clock of the reason() call
    tokens: int = 0                 # LLM tokens spent (0 for rule/memory)

    def to_dict(self) -> dict:
        return asdict(self)


# ---- Seam 1: the brain ------------------------------------------------------

class LLMClient(ABC):
    """Given evidence, propose a fix. Swap the body for a real LLM later."""

    @abstractmethod
    def reason(self, evidence: EvidenceBundle, memory: list[dict] | None = None) -> Fix:
        ...


# ---- Seam 2: where the Gym runs --------------------------------------------

class SandboxRunner(ABC):
    """Abstracts *where* the cluster lives. Local kind today, Daytona tomorrow."""

    @abstractmethod
    def ensure_up(self) -> None: ...

    @abstractmethod
    def deploy_healthy(self) -> None: ...

    @abstractmethod
    def teardown(self) -> None: ...
