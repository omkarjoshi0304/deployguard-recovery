"""DaytonaRunner (Seam 2) — runs the Failure Gym inside a Daytona sandbox.

Uses **k3s** (not kind) for the Kubernetes cluster. kind runs each node as a
privileged nested container that needs to create device nodes, which Daytona's
container-class sandbox forbids. k3s runs its pods at the same nesting depth as a
normal container (which works), so it gives us REAL Kubernetes inside Daytona.

All kubectl calls route through a SandboxExecutor that rewrites them to `k3s kubectl`
and runs them inside the sandbox — so faults/evidence/scorer stay identical.

Requires: DAYTONA_API_KEY (and optionally DAYTONA_TARGET, default 'eu').

Value it adds over local kind:
  - Isolation: the Gym runs in a disposable cloud sandbox, not your machine
  - Snapshot: freeze the exact broken state for deterministic replay
  - Fork: clone an identical starting state per candidate fix (fair comparison)
  - Safety: AI-generated fixes run in a throwaway box, never against real infra
"""
from __future__ import annotations
import os
import shlex
import base64
from pathlib import Path

from .interfaces import SandboxRunner
from . import config
from .sh import Result
from . import cluster as cl

# Any linux image works (k3s is a static binary); this one is proven to boot.
BASE_IMAGE = "docker:28.3.3-dind"

_BIN_DIR = Path(__file__).resolve().parent.parent / ".bin"
_K3S_URL = "https://github.com/k3s-io/k3s/releases/download/v1.31.5%2Bk3s1/k3s"


def _ensure_local_k3s() -> Path:
    """Cache the k3s linux/amd64 binary on the host for upload (sandbox blocks
    arbitrary HTTPS, so we ship the binary in rather than download it there)."""
    _BIN_DIR.mkdir(exist_ok=True)
    k3s = _BIN_DIR / "k3s"
    if not k3s.exists():
        cl.run(["curl", "-sSLo", str(k3s), _K3S_URL], timeout=300, check=True)
    return k3s


class SandboxExecutor:
    """Runs commands INSIDE a Daytona sandbox. Rewrites `kubectl --context X ...`
    into `k3s kubectl ...` (k3s ships its own kubectl + kubeconfig)."""

    def __init__(self, sandbox):
        self.sandbox = sandbox

    @staticmethod
    def _rewrite(cmd: list[str]) -> list[str]:
        if cmd and cmd[0] == "kubectl":
            rest, i = [], 1
            while i < len(cmd):
                if cmd[i] == "--context":   # drop "--context <name>"
                    i += 2
                    continue
                rest.append(cmd[i])
                i += 1
            return ["k3s", "kubectl", *rest]
        return cmd

    def run_cmd(self, cmd, timeout=60, check=False, quiet=False) -> Result:
        cmd = self._rewrite(cmd)
        cmd_str = " ".join(shlex.quote(a) for a in cmd)
        if not quiet:
            print("  [daytona] $", cmd_str)
        resp = self.sandbox.process.exec(cmd_str, timeout=timeout)
        res = Result(resp.exit_code, (resp.result or "").strip(), "")
        if check and not res.ok:
            raise RuntimeError(f"[daytona] command failed ({res.code}): {cmd_str}\n{res.out}")
        return res

    def apply_manifest(self, manifest: str) -> Result:
        b64 = base64.b64encode(manifest.encode()).decode()
        cmd = (f"echo {b64} | base64 -d > /tmp/manifest.yaml && "
               f"k3s kubectl apply -f /tmp/manifest.yaml")
        print("  [daytona] $ k3s kubectl apply -f - (via /tmp/manifest.yaml)")
        resp = self.sandbox.process.exec(cmd, timeout=60)
        return Result(resp.exit_code, (resp.result or "").strip(), "")


# Bootstrap: start k3s, wait for the node Ready + the default serviceaccount.
_BOOTSTRAP = """
set -e
chmod +x /usr/local/bin/k3s

if ! /usr/local/bin/k3s kubectl get nodes >/dev/null 2>&1; then
  echo "starting k3s server..."
  ( /usr/local/bin/k3s server --snapshotter=native \
      --disable traefik --disable metrics-server --disable servicelb \
      >/tmp/k3s.log 2>&1 & )
fi

# wait for the node to be Ready
i=0
while [ $i -lt 60 ]; do
  /usr/local/bin/k3s kubectl get nodes 2>/dev/null | grep -q " Ready " && break
  i=$((i+1)); sleep 3
done
if ! /usr/local/bin/k3s kubectl get nodes 2>/dev/null | grep -q " Ready "; then
  echo "k3s not ready"; tail -30 /tmp/k3s.log 2>/dev/null; exit 1
fi

# wait for the default serviceaccount (avoids 'default SA not found' race)
i=0
while [ $i -lt 30 ]; do
  /usr/local/bin/k3s kubectl get sa default >/dev/null 2>&1 && break
  i=$((i+1)); sleep 2
done
echo "BOOTSTRAP_OK"
"""


class DaytonaRunner(SandboxRunner):
    def __init__(self, api_key: str | None = None, target: str | None = None):
        try:
            from daytona import Daytona, DaytonaConfig, CreateSandboxFromImageParams, Resources
        except ImportError:
            raise ImportError("daytona SDK not installed. Run: pip install daytona")
        self._Create = CreateSandboxFromImageParams
        self._Resources = Resources

        api_key = api_key or os.getenv("DAYTONA_API_KEY")
        if not api_key:
            raise ValueError("DAYTONA_API_KEY must be set")
        target = target or os.getenv("DAYTONA_TARGET", "eu")
        self.daytona = Daytona(DaytonaConfig(api_key=api_key, target=target))
        self.sandbox = None
        self.executor = None

    def _activate(self, sandbox) -> None:
        self.sandbox = sandbox
        self.executor = SandboxExecutor(sandbox)
        cl.set_executor(self.executor)

    def ensure_up(self) -> None:
        k3s_bin = _ensure_local_k3s()

        print(f"[daytona] creating sandbox ({BASE_IMAGE}) ...")
        sandbox = self.daytona.create(
            self._Create(
                image=BASE_IMAGE,
                resources=self._Resources(cpu=2, memory=4, disk=10),
            ),
            timeout=180,
        )
        self._activate(sandbox)

        print("[daytona] uploading k3s binary ...")
        sandbox.fs.upload_file(str(k3s_bin), "/usr/local/bin/k3s")

        print("[daytona] bootstrapping (k3s server) ...")
        resp = sandbox.process.exec(f"sh -c {shlex.quote(_BOOTSTRAP)}", timeout=400)
        if "BOOTSTRAP_OK" not in (resp.result or ""):
            raise RuntimeError(f"[daytona] bootstrap failed:\n{resp.result}")
        print("[daytona] real Kubernetes (k3s) ready inside sandbox")

    def deploy_healthy(self) -> None:
        print("[daytona] applying healthy app")
        proc = cl._apply_stdin(cl.HEALTHY_MANIFEST)
        if not proc.ok:
            raise RuntimeError(f"deploy failed: {proc.out}")
        cl.kubectl(["rollout", "status", f"deployment/{config.APP_NAME}",
                    f"--timeout={config.ROLLOUT_TIMEOUT}s"],
                   timeout=config.ROLLOUT_TIMEOUT + 10)

    def reset_app(self) -> None:
        cl.kubectl(["delete", "deployment", config.APP_NAME, "--ignore-not-found"], quiet=True)
        cl.kubectl(["delete", "secret", "app-secret", "--ignore-not-found"], quiet=True)
        self.deploy_healthy()

    # ---- Daytona-only superpowers (for byte-identical replay in eval) ----

    def snapshot(self, name: str) -> None:
        print(f"[daytona] snapshot -> {name}")
        self.sandbox.create_snapshot(name, timeout=120)

    def fork(self, name: str | None = None):
        print("[daytona] fork current sandbox")
        forked = self.sandbox.fork(name=name, timeout=120)
        self._activate(forked)
        return forked

    def teardown(self) -> None:
        cl.set_executor(None)
        if self.sandbox is not None:
            print("[daytona] deleting sandbox")
            self.sandbox.delete()
