"""Incident memory — the learned artifact.

Structure: a list of entries, each capturing the symptom fingerprint of a
successful fix. The brain consults this before reasoning from scratch.

Lifecycle:
  - OPEN during training: new successful entries are appended.
  - FROZEN after training: read-only; the frozen copy is what gets evaluated.

The memory file lives at memory/incidents.json.
The frozen snapshot is at memory/incidents_frozen.json.
"""
from __future__ import annotations
import json
from pathlib import Path

from .interfaces import EvidenceBundle, Fix

MEM_DIR = Path(__file__).resolve().parent.parent / "memory"
ACTIVE_FILE = MEM_DIR / "incidents.json"
FROZEN_FILE = MEM_DIR / "incidents_frozen.json"


def _fingerprint(evidence: EvidenceBundle) -> dict:
    """A compact, matchable summary of what the agent observed."""
    return {
        "pod_reasons": sorted(set(evidence.pod_reasons)),
        "change_kind": evidence.recent_change.get("kind", ""),
        "ready": evidence.ready,
    }


def _similarity(fp1: dict, fp2: dict) -> float:
    """0.0–1.0: how similar two fingerprints are."""
    score = 0.0
    # Same change kind is the strongest signal.
    if fp1["change_kind"] and fp1["change_kind"] == fp2["change_kind"]:
        score += 0.6
    # Overlapping pod reasons.
    r1, r2 = set(fp1["pod_reasons"]), set(fp2["pod_reasons"])
    if r1 and r2:
        score += 0.4 * len(r1 & r2) / max(len(r1 | r2), 1)
    return min(score, 1.0)


def load(frozen: bool = False) -> list[dict]:
    path = FROZEN_FILE if frozen else ACTIVE_FILE
    if not path.exists():
        return []
    return json.loads(path.read_text())


def save(entries: list[dict], frozen: bool = False) -> None:
    MEM_DIR.mkdir(exist_ok=True)
    path = FROZEN_FILE if frozen else ACTIVE_FILE
    path.write_text(json.dumps(entries, indent=2))


def record_success(evidence: EvidenceBundle, fix: Fix) -> None:
    """Append a successful (evidence, fix) pair to active memory."""
    entries = load()
    entry = {
        "fingerprint": _fingerprint(evidence),
        "fix_action": fix.action,
        "fix_params": fix.params,
        "rationale": fix.rationale,
    }
    # Deduplicate: don't store the exact same fingerprint+action twice.
    for e in entries:
        if (e["fingerprint"] == entry["fingerprint"]
                and e["fix_action"] == entry["fix_action"]):
            return
    entries.append(entry)
    save(entries)
    print(f"  [memory] recorded: {fix.action} for {_fingerprint(evidence)}")


def recall(evidence: EvidenceBundle, threshold: float = 0.6,
           frozen: bool = False) -> dict | None:
    """Return the best-matching memory entry, or None if below threshold."""
    fp = _fingerprint(evidence)
    entries = load(frozen=frozen)
    best, best_sim = None, 0.0
    for e in entries:
        sim = _similarity(fp, e["fingerprint"])
        if sim > best_sim:
            best_sim, best = sim, e
    if best and best_sim >= threshold:
        print(f"  [memory] hit (sim={best_sim:.2f}): {best['fix_action']}")
        return best
    print(f"  [memory] no match (best_sim={best_sim:.2f}) — falling back to brain")
    return None


def freeze() -> int:
    """Copy active memory to frozen snapshot. Returns entry count."""
    entries = load()
    save(entries, frozen=True)
    print(f"  [memory] FROZEN — {len(entries)} entries written to {FROZEN_FILE}")
    return len(entries)


def stats() -> dict:
    return {
        "active_entries": len(load()),
        "frozen_entries": len(load(frozen=True)),
        "frozen_file_exists": FROZEN_FILE.exists(),
    }
