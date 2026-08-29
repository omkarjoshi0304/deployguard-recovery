"""Training loop: run N laps on training faults, distill successes into memory.

Calling sequence:
  1. train()          — runs laps, writes to active memory
  2. freeze_memory()  — locks the artifact; no more writes
  (evaluate() is in evaluator.py)
"""
from __future__ import annotations
import time

from . import config, memory
from .cluster import KindRunner
from .orchestrator import run_lap
from .llm_mock import RuleBasedLLM
from .interfaces import LLMClient, EvidenceBundle
from . import faults, evidence as ev


def train(
    laps_per_fault: int = 3,
    llm: LLMClient | None = None,
    settle_seconds: int = 8,
) -> dict:
    """
    Run `laps_per_fault` laps on every TRAINING fault.
    Successful outcomes are written to active memory.
    Returns a summary dict.
    """
    llm = llm or RuleBasedLLM()
    runner = KindRunner()
    runner.ensure_up()

    summary = {"total": 0, "success": 0, "fail": 0, "memory_entries": 0}

    for fault in config.TRAINING_FAULTS:
        print(f"\n{'='*50}")
        print(f"  TRAINING FAULT: {fault}  ({laps_per_fault} laps)")
        print(f"{'='*50}")
        for lap_n in range(laps_per_fault):
            print(f"\n  -- lap {lap_n+1}/{laps_per_fault} --")
            runner.reset_app()
            change = faults.inject(fault)
            time.sleep(settle_seconds)
            bundle = ev.collect(change)

            fix = llm.reason(bundle)
            print(f"  [agent] {fix.action} — {fix.rationale}")

            from . import scorer as sc
            note = sc.apply_fix(fix)
            success = sc.check_success()
            safety = sc.safety_flags(fix, success)

            summary["total"] += 1
            if success and not any(safety.values()):
                summary["success"] += 1
                memory.record_success(bundle, fix)
                print(f"  [train] ✓ success — recorded to memory")
            else:
                summary["fail"] += 1
                print(f"  [train] ✗ fail  safety={safety}")

    summary["memory_entries"] = memory.stats()["active_entries"]
    print(f"\n[train] done — {summary}")
    return summary


def freeze_memory() -> int:
    """Freeze active memory into the held-out artifact. Call once, after train()."""
    return memory.freeze()
