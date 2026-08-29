#!/usr/bin/env python3
"""DeployGuard-Recovery CLI.

  python3 main.py setup                         create cluster + deploy healthy app
  python3 main.py lap --fault bad_image         one full lap (inject->fix->score)
  python3 main.py capture                       save evidence fixtures for all faults
  python3 main.py replay --fault bad_image      run brain on a saved fixture (no cluster)
  python3 main.py train                         training loop on all training faults
  python3 main.py freeze                        freeze memory (run once after train)
  python3 main.py eval                          held-out eval: A vs B vs C
  python3 main.py teardown                      delete the cluster
"""
import argparse

from recovery import config
from recovery.cluster import KindRunner
from recovery.orchestrator import run_lap
from recovery import fixtures


def main():
    p = argparse.ArgumentParser(description="DeployGuard-Recovery harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup")

    lap = sub.add_parser("lap")
    lap.add_argument("--fault", required=True, choices=config.FAULTS)

    sub.add_parser("capture")

    rep = sub.add_parser("replay")
    rep.add_argument("--fault", required=True, choices=config.FAULTS)

    tr = sub.add_parser("train")
    tr.add_argument("--laps", type=int, default=3, help="laps per fault (default 3)")

    sub.add_parser("freeze")

    ev = sub.add_parser("eval")
    ev.add_argument("--fault", default=config.HELD_OUT_FAULT,
                    help=f"held-out fault (default: {config.HELD_OUT_FAULT})")
    ev.add_argument("--laps", type=int, default=3)

    sub.add_parser("teardown")

    args = p.parse_args()

    if args.cmd == "setup":
        r = KindRunner()
        r.ensure_up()
        r.deploy_healthy()
        print("\n[ok] cluster ready with healthy app")

    elif args.cmd == "lap":
        res = run_lap(args.fault)
        print(f"\n[result] fault={res.fault} success={res.success} safety={res.safety}")

    elif args.cmd == "capture":
        fixtures.capture_all()

    elif args.cmd == "replay":
        fixtures.replay(args.fault)

    elif args.cmd == "train":
        from recovery.trainer import train
        summary = train(laps_per_fault=args.laps)
        print(f"\n[train] summary: {summary}")
        print("[next] run `python3 main.py freeze` then `python3 main.py eval`")

    elif args.cmd == "freeze":
        from recovery.trainer import freeze_memory
        n = freeze_memory()
        print(f"\n[ok] memory frozen ({n} entries)")
        print("[next] run `python3 main.py eval`")

    elif args.cmd == "eval":
        from recovery.evaluator import evaluate
        evaluate(held_out_fault=args.fault, laps=args.laps)

    elif args.cmd == "teardown":
        KindRunner().teardown()


if __name__ == "__main__":
    main()
