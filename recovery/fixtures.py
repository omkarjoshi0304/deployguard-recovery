"""Capture real evidence bundles to disk.

Doubles as (a) test fixtures for keyless/clusterless dev and (b) the
recorded-replay fallback dataset if Daytona/kind misbehaves on demo day.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

from . import config, faults, evidence as ev
from .cluster import KindRunner, kubectl
from .interfaces import EvidenceBundle
from .llm_mock import RuleBasedLLM

FIX_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def capture_all(settle_seconds: int = 8):
    runner = KindRunner()
    runner.ensure_up()
    FIX_DIR.mkdir(exist_ok=True)
    for fault in config.FAULTS:
        print(f"\n[capture] {fault}")
        runner.reset_app()
        # Purge namespace events so the fixture captures ONLY this fault's events.
        # kubectl get events is namespace-wide; stale events from the previous
        # fault would otherwise bleed in (e.g. a "secret not found" event landing
        # in the oom_kill fixture).
        kubectl(["delete", "events", "--all"], quiet=True)
        change = faults.inject(fault)
        time.sleep(settle_seconds)
        bundle = ev.collect(change)
        path = FIX_DIR / f"{fault}.json"
        path.write_text(json.dumps(bundle.to_dict(), indent=2))
        print(f"  saved {path}  (pod_reasons={bundle.pod_reasons})")


def replay(fault: str, llm=None):
    """Run the brain against a saved fixture — no cluster required."""
    from .interfaces import LLMClient
    llm = llm or RuleBasedLLM()
    path = FIX_DIR / f"{fault}.json"
    if not path.exists():
        raise FileNotFoundError(f"no fixture for '{fault}'; run `capture` first")
    bundle = EvidenceBundle.from_dict(json.loads(path.read_text()))
    fix = llm.reason(bundle)
    print(f"[replay] fault={fault}")
    print(f"  pod_reasons={bundle.pod_reasons}")
    print(f"  proposed fix: {fix.action}  params={fix.params}")
    print(f"  rationale: {fix.rationale}")
    return fix
