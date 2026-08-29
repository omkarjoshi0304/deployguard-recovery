"""Memory-augmented brain — the improved agent.

Logic:
  1. Check frozen memory for a similar past incident.
  2. If hit (similarity >= threshold): return the remembered fix directly.
  3. If miss: fall through to the base LLM (mock or real).

This is the agent that gets evaluated in the held-out eval.
When a real LLM is wired in, replace `self.base_llm` with GeminiClient/ClaudeClient.
The memory lookup is model-agnostic.
"""
from __future__ import annotations

from .interfaces import LLMClient, EvidenceBundle, Fix
from .llm_mock import RuleBasedLLM
from . import memory


class MemoryBrain(LLMClient):
    """Reads from FROZEN memory first, falls back to the base LLM."""

    def __init__(self, base_llm: LLMClient | None = None, threshold: float = 0.6):
        self.base_llm = base_llm or RuleBasedLLM()
        self.threshold = threshold

    def reason(self, evidence: EvidenceBundle,
               memory_entries=None) -> Fix:
        hit = memory.recall(evidence, threshold=self.threshold, frozen=True)
        if hit:
            return Fix(
                action=hit["fix_action"],
                target=evidence.deployment,
                params=hit["fix_params"],
                rationale=f"[from memory] {hit['rationale']}",
            )
        return self.base_llm.reason(evidence)
