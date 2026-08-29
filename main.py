#!/usr/bin/env python3
"""DeployGuard-Recovery CLI.

  python3 main.py setup                         create cluster + deploy healthy app
  python3 main.py lap --fault bad_image         one full lap (inject->fix->score)
  python3 main.py lap --fault bad_image --llm gemini   use Gemini instead of rules
  python3 main.py capture                       save evidence fixtures for all faults
  python3 main.py replay --fault bad_image      run brain on a saved fixture (no cluster)
  python3 main.py train                         training loop on all training faults
  python3 main.py train --llm gemini            train with Gemini reasoning
  python3 main.py freeze                        freeze memory (run once after train)
  python3 main.py eval                          held-out eval: A vs B vs C
  python3 main.py eval --llm gemini             eval with Gemini as System B
  python3 main.py teardown                      delete the cluster

Set GEMINI_API_KEY environment variable to use --llm gemini.
"""
import argparse
import os

from recovery import config
from recovery.cluster import KindRunner
from recovery.orchestrator import run_lap
from recovery import fixtures


def _get_llm(llm_type: str):
    """Return an LLM client instance based on type."""
    if llm_type == "gemini":
        from recovery.llm_gemini import GeminiClient
        return GeminiClient()
    elif llm_type == "mock":
        from recovery.llm_mock import RuleBasedLLM
        return RuleBasedLLM()
    else:
        raise ValueError(f"Unknown LLM type: {llm_type}")


def _get_runner(sandbox_type: str):
    """Return a SandboxRunner (local kind or Daytona)."""
    if sandbox_type == "daytona":
        from recovery.daytona_runner import DaytonaRunner
        return DaytonaRunner()
    from recovery.cluster import KindRunner
    return KindRunner()


def main():
    p = argparse.ArgumentParser(description="DeployGuard-Recovery harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    setup = sub.add_parser("setup")
    setup.add_argument("--sandbox", choices=["local", "daytona"], default="local")

    lap = sub.add_parser("lap")
    lap.add_argument("--fault", required=True, choices=config.FAULTS)
    lap.add_argument("--llm", choices=["mock", "gemini"], default="mock",
                     help="LLM to use (default: mock)")
    lap.add_argument("--sandbox", choices=["local", "daytona"], default="local")

    sub.add_parser("capture")

    rep = sub.add_parser("replay")
    rep.add_argument("--fault", required=True, choices=config.FAULTS)
    rep.add_argument("--llm", choices=["mock", "gemini"], default="mock")

    tr = sub.add_parser("train")
    tr.add_argument("--laps", type=int, default=3, help="laps per fault (default 3)")
    tr.add_argument("--llm", choices=["mock", "gemini"], default="mock")

    sub.add_parser("freeze")

    ev = sub.add_parser("eval")
    ev.add_argument("--fault", default=config.HELD_OUT_FAULT,
                    help=f"held-out fault (default: {config.HELD_OUT_FAULT})")
    ev.add_argument("--laps", type=int, default=3)
    ev.add_argument("--llm", choices=["mock", "gemini"], default="mock",
                    help="LLM for System B (default: mock)")

    sub.add_parser("teardown")

    args = p.parse_args()

    if args.cmd == "setup":
        r = _get_runner(args.sandbox)
        r.ensure_up()
        r.deploy_healthy()
        print("\n[ok] cluster ready with healthy app")

    elif args.cmd == "lap":
        llm = _get_llm(args.llm)
        runner = _get_runner(args.sandbox)
        res = run_lap(args.fault, llm=llm, runner=runner)
        print(f"\n[result] fault={res.fault} success={res.success} safety={res.safety}")

    elif args.cmd == "capture":
        fixtures.capture_all()

    elif args.cmd == "replay":
        llm = _get_llm(args.llm)
        fixtures.replay(args.fault, llm=llm)

    elif args.cmd == "train":
        from recovery.trainer import train
        llm = _get_llm(args.llm)
        summary = train(laps_per_fault=args.laps, llm=llm)
        print(f"\n[train] summary: {summary}")
        print("[next] run `python3 main.py freeze` then `python3 main.py eval`")

    elif args.cmd == "freeze":
        from recovery.trainer import freeze_memory
        n = freeze_memory()
        print(f"\n[ok] memory frozen ({n} entries)")
        print("[next] run `python3 main.py eval`")

    elif args.cmd == "eval":
        from recovery.evaluator import evaluate
        llm = _get_llm(args.llm)
        evaluate(held_out_fault=args.fault, laps=args.laps, base_llm=llm)

    elif args.cmd == "teardown":
        KindRunner().teardown()


if __name__ == "__main__":
    main()
