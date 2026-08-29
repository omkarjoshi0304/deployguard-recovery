"""Orchestrator: run one full lap and log the result.

lap = reset -> inject -> collect evidence -> reason -> apply fix -> score -> log
"""
from __future__ import annotations
import json
import time
from pathlib import Path

from . import config, faults, evidence as ev, scorer
from .cluster import KindRunner
from .interfaces import Fix, IncidentResult, LLMClient
from .llm_mock import RuleBasedLLM

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


def run_lap(fault: str, llm: LLMClient | None = None, runner: KindRunner | None = None,
            settle_seconds: int = 8) -> IncidentResult:
    llm = llm or RuleBasedLLM()
    runner = runner or KindRunner()

    print(f"\n=== LAP: {fault} ===")
    runner.ensure_up()
    runner.reset_app()                       # known-good baseline

    print("[inject] breaking the deployment")
    recent_change = faults.inject(fault)
    time.sleep(settle_seconds)               # let the failure surface

    print("[evidence] gathering")
    bundle = ev.collect(recent_change)
    print(f"  pod_reasons={bundle.pod_reasons} ready={bundle.ready}")

    print("[agent] reasoning")
    t0 = time.perf_counter()
    fix: Fix = llm.reason(bundle)
    latency_s = round(time.perf_counter() - t0, 3)
    print(f"  fix={fix.action} rationale={fix.rationale!r} latency={latency_s}s tokens={fix.tokens}")

    print("[apply] applying fix")
    note = scorer.apply_fix(fix)

    print("[score] verifying")
    success = scorer.check_success(bundle.deployment)
    safety = scorer.safety_flags(fix, success)
    print(f"  SUCCESS={success} safety={safety}")

    result = IncidentResult(
        fault=fault, fix=fix.to_dict(), success=success,
        safety=safety, evidence=bundle.to_dict(), notes=note,
        latency_s=latency_s, tokens=fix.tokens,
    )
    _log(result)
    return result


def _log(result: IncidentResult):
    RUNS_DIR.mkdir(exist_ok=True)
    n = len(list(RUNS_DIR.glob("*.json")))
    path = RUNS_DIR / f"{n:04d}_{result.fault}_{'ok' if result.success else 'fail'}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2))
    print(f"[log] {path}")
