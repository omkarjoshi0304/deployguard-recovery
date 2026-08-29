"""Rule-based LLMClient (Seam 1).

This does triple duty:
  1. Lets the whole pipeline run with zero API keys.
  2. Becomes the 'rule-based baseline' in the final comparison.
  3. Documents the exact Fix schema the real LLM must produce.

To go live: write GeminiClient / ClaudeClient implementing LLMClient.reason(),
feed it the evidence as a prompt, and parse its JSON into a Fix. Nothing else changes.

Note: it reasons from OBSERVED symptoms + the shipped diff — it does not read a
hidden 'answer key'. That is exactly what the real agent must do too.
"""
from __future__ import annotations

from .interfaces import LLMClient, EvidenceBundle, Fix
from . import config


class RuleBasedLLM(LLMClient):
    def reason(self, evidence: EvidenceBundle, memory=None) -> Fix:
        reasons = " ".join(evidence.pod_reasons).lower()
        events = evidence.events.lower()
        change = evidence.recent_change or {}

        # Symptom: container config error, typically a missing secret/configmap ref.
        # Check this BEFORE image: a missing-secret event also contains "not found".
        if "createcontainerconfigerror" in reasons or "secret" in events:
            ref = change.get("secret_ref", {"name": "app-secret", "key": "API_KEY"})
            return Fix(
                action="create_secret",
                target=evidence.deployment,
                params={"name": ref.get("name", "app-secret"),
                        "key": ref.get("key", "API_KEY"),
                        "value": "provisioned-by-agent"},
                rationale="Pod references a secret that does not exist; create it.",
            )

        # Symptom: image cannot be pulled / is invalid.
        if any(k in reasons for k in ("imagepull", "errimage", "invalidimage")) \
                or "imagepullbackoff" in events or "failed to pull image" in events:
            good = change.get("old_image", config.GOOD_IMAGE)  # from the shipped diff
            return Fix(
                action="rollback_image",
                target=evidence.deployment,
                params={"image": good},
                rationale="Image pull failing; roll back to last-known-good image from the shipped diff.",
            )

        # Symptom: OOMKilled — memory limit too low.
        if "oomkilled" in reasons or "oom" in events \
                or change.get("kind") == "resource_limits_changed":
            safe_mem = change.get("old_memory_limit", "128Mi")
            return Fix(
                action="fix_memory_limit",
                target=evidence.deployment,
                params={"memory": safe_mem},
                rationale="Container is OOMKilled; restore the previous memory limit from the shipped diff.",
            )

        # Symptom: stuck rollout — deployment shows ready but new pods aren't progressing.
        # Typically a broken readiness probe: old pods keep serving, new ones never become Ready.
        if evidence.stuck_rollout or (
                evidence.replicas_ready < evidence.replicas_desired
                and change.get("kind") == "readiness_probe_changed"):
            good_path = change.get("old_path", "/")
            return Fix(
                action="fix_readiness_probe",
                target=evidence.deployment,
                params={"path": good_path},
                rationale="Stuck rollout: new pods not replacing old ones; likely broken readiness probe. Restore probe path from shipped diff.",
            )

        # Unknown symptom -> escalate rather than guess (and DON'T claim it's fixed).
        return Fix(
            action="escalate",
            target=evidence.deployment,
            params={},
            rationale="Symptom not recognized; escalate to a human.",
            claims_fixed=False,
        )
