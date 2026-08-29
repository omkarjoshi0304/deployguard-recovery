"""Thin subprocess wrapper so every shell call is logged and consistent."""
import subprocess
from dataclasses import dataclass


@dataclass
class Result:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(args, env=None, timeout=120, check=False, quiet=False):
    """Run a command (list of args). Never raises unless check=True."""
    if not quiet:
        print("  $", " ".join(args))
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    res = Result(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
    if check and not res.ok:
        raise RuntimeError(f"command failed ({res.code}): {' '.join(args)}\n{res.err}")
    return res
