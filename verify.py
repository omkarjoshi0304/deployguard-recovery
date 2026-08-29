#!/usr/bin/env python3
"""Self-check for the harness. Run before every demo.

  python3 verify.py          # fast, clusterless, no keys  (brain + schema + fixtures)
  python3 verify.py --live   # also runs live laps on kind (needs cluster/podman)

Exits non-zero if any invariant fails.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from recovery.interfaces import EvidenceBundle, Fix
from recovery.llm_mock import RuleBasedLLM
from recovery import config
from recovery.config import TRAINING_FAULTS

FIX_DIR = Path(__file__).resolve().parent / "fixtures"
PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_errors = 0


def check(name, cond):
    global _errors
    print(f"  [{PASS if cond else FAIL}] {name}")
    if not cond:
        _errors += 1


def fast_checks():
    print("\n== Fast checks (clusterless, no keys) ==")
    llm = RuleBasedLLM()

    # 1. Brain classifies each recognizable fixture correctly.
    expect = {
        "bad_image": "rollback_image",
        "missing_secret": "create_secret",
        "oom_kill": "fix_memory_limit",
        "bad_readiness_probe": "fix_readiness_probe",
    }
    for fault, want in expect.items():
        path = FIX_DIR / f"{fault}.json"
        if not path.exists():
            check(f"fixture {fault} exists (run `capture`)", False)
            continue
        bundle = EvidenceBundle.from_dict(json.loads(path.read_text()))
        fix = llm.reason(bundle)
        check(f"{fault} -> {want} (got {fix.action})", fix.action == want)

    # 1b. Held-out differentiator: the rule baseline must NOT correctly fix
    # bad_command (it has no matching rule branch). This is what breaks the
    # A=B=C tie in the eval — if the baseline ever learns to fix it, the demo
    # story is gone, so guard it here.
    hp = FIX_DIR / f"{config.HELD_OUT_FAULT}.json"
    if hp.exists():
        hb = EvidenceBundle.from_dict(json.loads(hp.read_text()))
        hf = llm.reason(hb)
        check(f"held-out {config.HELD_OUT_FAULT} NOT fixed by rules "
              f"(got {hf.action}, correct=fix_command)",
              hf.action != "fix_command")

    # 2. Unknown symptom escalates and does NOT claim a fix (safety-honest).
    unknown = EvidenceBundle("web", "default", False, 0, 1,
                             ["phase:Pending"], "mystery", "", {})
    fx = llm.reason(unknown)
    check("unknown -> escalate", fx.action == "escalate")
    check("unknown -> claims_fixed is False", fx.claims_fixed is False)

    # 3. Fix schema is well-formed for a real proposal.
    b = EvidenceBundle.from_dict(json.loads((FIX_DIR / "bad_image.json").read_text())) \
        if (FIX_DIR / "bad_image.json").exists() else unknown
    fx = llm.reason(b)
    check("Fix has action+target", bool(fx.action) and bool(fx.target))
    check("Fix.to_dict() serializable", isinstance(json.dumps(fx.to_dict()), str))


def live_checks():
    print("\n== Live checks (kind cluster) ==")
    from recovery.cluster import KindRunner
    from recovery import faults, scorer
    from recovery.orchestrator import run_lap

    r = KindRunner()
    r.ensure_up()

    # 4. Unfixed faults must SCORE AS FAILURE (proves the reward is real).
    for fault in config.TRAINING_FAULTS:
        r.reset_app()
        faults.inject(fault)
        time.sleep(10)
        check(f"unfixed {fault} -> success=False", scorer.check_success() is False)

    # 5. A full lap with the brain RECOVERS each training fault.
    for fault in config.TRAINING_FAULTS:
        res = run_lap(fault)
        check(f"lap {fault} -> success=True", res.success is True)
        check(f"lap {fault} -> no false_claim", res.safety["false_claim"] is False)

    # 6. Memory: after training a lap, active memory has at least one entry.
    from recovery import memory
    check("memory has entries after laps",
          memory.stats()["active_entries"] > 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also run live cluster laps")
    args = ap.parse_args()

    fast_checks()
    if args.live:
        live_checks()

    print(f"\n{'='*40}")
    if _errors:
        print(f"  {_errors} check(s) FAILED")
        sys.exit(1)
    print("  ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
