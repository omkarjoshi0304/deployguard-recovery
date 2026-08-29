"""Held-out evaluation: compare three systems on the UNSEEN fault.

Systems under test:
  A. Baseline: rule-based brain, no memory  (already the demo "before")
  B. One-shot LLM: base LLM, no memory      (strong baseline if real LLM is wired in)
  C. Frozen memory agent: memory_brain       (our trained agent — the winner)

All three systems run on an identical starting cluster state (same reset_app()).
Results are printed as a table and saved to eval/results.json.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

from . import config, faults, evidence as ev, scorer as sc
from .cluster import KindRunner
from .interfaces import LLMClient
from .llm_mock import RuleBasedLLM
from .memory_brain import MemoryBrain

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def _run_one(
    fault: str,
    llm: LLMClient,
    label: str,
    runner: KindRunner,
    settle: int = 8,
) -> dict:
    runner.reset_app()
    change = faults.inject(fault)
    time.sleep(settle)
    bundle = ev.collect(change)

    fix = llm.reason(bundle)
    note = sc.apply_fix(fix)
    success = sc.check_success()
    safety = sc.safety_flags(fix, success)

    return {
        "system": label,
        "fault": fault,
        "action": fix.action,
        "success": success,
        "safety": safety,
        "false_claim": safety["false_claim"],
        "claims_fixed": fix.claims_fixed,
        "rationale": fix.rationale,
    }


def evaluate(
    held_out_fault: str | None = None,
    base_llm: LLMClient | None = None,
    laps: int = 3,
    settle: int = 8,
) -> dict:
    """Run held-out eval. Returns the results dict."""
    fault = held_out_fault or config.HELD_OUT_FAULT
    base_llm = base_llm or RuleBasedLLM()
    runner = KindRunner()
    runner.ensure_up()

    systems = [
        ("A: Rule-based (no memory)",      RuleBasedLLM()),
        ("B: One-shot LLM (no memory)",     base_llm),
        ("C: Memory agent (frozen, ours)",  MemoryBrain(base_llm=base_llm)),
    ]

    all_results: list[dict] = []

    for label, llm in systems:
        sys_results = []
        print(f"\n[eval] {label}  fault={fault}  laps={laps}")
        for i in range(laps):
            r = _run_one(fault, llm, label, runner, settle)
            sys_results.append(r)
            print(f"  lap {i+1}: success={r['success']} false_claim={r['false_claim']}")
        all_results.extend(sys_results)

    _print_table(all_results, fault)
    _save(all_results, fault)
    return {"fault": fault, "results": all_results}


def _print_table(results: list[dict], fault: str) -> None:
    from collections import defaultdict
    by_sys: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_sys[r["system"]].append(r)

    print(f"\n{'='*60}")
    print(f"  HELD-OUT EVAL  fault={fault}")
    print(f"{'='*60}")
    print(f"  {'System':<35} {'Success':>8} {'False claim':>12}")
    print(f"  {'-'*35} {'-'*8} {'-'*12}")
    for sys, rows in by_sys.items():
        suc = sum(1 for r in rows if r["success"])
        fc  = sum(1 for r in rows if r["false_claim"])
        n   = len(rows)
        print(f"  {sys:<35} {suc}/{n:>6} {fc}/{n:>10}")
    print(f"{'='*60}")


def _save(results: list[dict], fault: str) -> None:
    EVAL_DIR.mkdir(exist_ok=True)
    path = EVAL_DIR / f"results_{fault}.json"
    path.write_text(json.dumps({"fault": fault, "results": results}, indent=2))
    print(f"[eval] saved -> {path}")
