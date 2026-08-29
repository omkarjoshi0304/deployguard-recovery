"""Gemini LLM Client (Seam 1 - real LLM implementation).

Swap this in for llm_mock.py to use real Gemini reasoning instead of rules.
Requires: GEMINI_API_KEY environment variable.
"""
from __future__ import annotations
import os
import json
import re

from .interfaces import LLMClient, EvidenceBundle, Fix


def _build_prompt(evidence: EvidenceBundle) -> str:
    """Format evidence as a clear prompt for Gemini."""
    return f"""You are a Kubernetes deployment recovery agent. A deployment has failed and you must propose a fix.

## Evidence

**Deployment:** {evidence.deployment} (namespace: {evidence.namespace})
**Status:** {"Ready" if evidence.ready else "NOT Ready"} — {evidence.replicas_ready}/{evidence.replicas_desired} replicas ready
**Updated replicas:** {evidence.updated_replicas} (stuck rollout: {evidence.stuck_rollout})
**Pod reasons:** {evidence.pod_reasons or "none"}

**Recent shipped change:**
```json
{json.dumps(evidence.recent_change, indent=2)}
```

**Recent events (last 2000 chars):**
```
{evidence.events[-2000:]}
```

**Container logs (last 500 chars):**
```
{evidence.logs[-500:] if evidence.logs else "(no logs)"}
```

## Your Task

Analyze the evidence and propose ONE structured fix. Choose from these actions:

- `rollback_image` — revert to the old image from the shipped diff
- `set_image` — set a specific image
- `create_secret` — create a missing secret/configmap
- `fix_memory_limit` — restore a safe memory limit
- `fix_readiness_probe` — restore the readiness probe path
- `escalate` — if you cannot determine a safe fix (set claims_fixed=false)

## Response Format

Respond with ONLY valid JSON, no markdown fences, no explanation:

{{
  "action": "rollback_image",
  "target": "{evidence.deployment}",
  "params": {{"image": "nginx:1.27-alpine"}},
  "rationale": "One-sentence explanation of why this fix is correct.",
  "claims_fixed": true
}}

**Critical rules:**
- If unsure, use `"action": "escalate"` and set `"claims_fixed": false` (never guess)
- Always check the `recent_change` for the old/safe value to restore
- The `target` must be `"{evidence.deployment}"`
- Response must be valid JSON only
"""


def _parse_fix(response_text: str, deployment: str) -> Fix:
    """Parse Gemini's response into a Fix. Handles markdown fences gracefully."""
    # Strip markdown fences if present
    clean = response_text.strip()
    if clean.startswith("```"):
        # Extract JSON from ```json ... ``` or ``` ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL)
        if match:
            clean = match.group(1)
        else:
            # Fallback: strip first and last lines
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        # Gemini returned unparseable output → escalate
        return Fix(
            action="escalate",
            target=deployment,
            params={},
            rationale=f"LLM returned unparseable JSON: {e}. Response was: {response_text[:200]}",
            claims_fixed=False,
        )

    return Fix(
        action=data.get("action", "escalate"),
        target=data.get("target", deployment),
        params=data.get("params", {}),
        rationale=data.get("rationale", "No rationale provided"),
        claims_fixed=data.get("claims_fixed", True),
    )


class GeminiClient(LLMClient):
    """Real Gemini LLM client via google.genai library (new SDK)."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be set (env var or constructor arg)")
        self.model = model

        # Lazy import so the mock brain doesn't require this dependency
        try:
            from google import genai
            from google.genai import types
            self.genai = genai
            self.types = types
            self.client = self.genai.Client(api_key=self.api_key)
        except ImportError:
            raise ImportError(
                "google-genai not installed. Run: pip install google-genai"
            )

    def reason(self, evidence: EvidenceBundle, memory=None) -> Fix:
        prompt = _build_prompt(evidence)
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            text = response.text
            print(f"  [gemini] raw response: {text[:150]}...")
        except Exception as e:
            print(f"  [gemini] API error: {e}")
            return Fix(
                action="escalate",
                target=evidence.deployment,
                params={},
                rationale=f"Gemini API error: {e}",
                claims_fixed=False,
            )

        return _parse_fix(text, evidence.deployment)
