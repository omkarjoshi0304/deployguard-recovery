"""DaytonaRunner (Seam 2) — runs the Failure Gym inside a Daytona sandbox.

Instead of a kind cluster on your laptop, this provisions a Daytona Docker-in-Docker
sandbox, installs kind + kubectl, creates the cluster inside it, and routes every
kubectl call through the sandbox via an executor.

Requires: DAYTONA_API_KEY (and optionally DAYTONA_TARGET, default 'us').

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

# DinD base image recommended by Daytona docs (Alpine, lightweight).
DIND_IMAGE = "docker:28.3.3-dind"

# Local cache of linux/amd64 binaries we upload into the sandbox.
# (Daytona sandboxes allow docker-registry egress but block arbitrary HTTPS like
#  dl.k8s.io, so we ship the binaries in rather than downloading them there.)
_BIN_DIR = Path(__file__).resolve().parent.parent / ".bin"
_KUBECTL_URL = "https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl"
_KIND_URL = "https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64"


def _ensure_local_binaries() -> tuple[Path, Path]:
    """Make sure linux/amd64 kind + kubectl are cached on the host for upload."""
    _BIN_DIR.mkdir(exist_ok=True)
    kubectl, kind = _BIN_DIR / "kubectl", _BIN_DIR / "kind"
    if not kubectl.exists():
        cl.run(["curl", "-sSLo", str(kubectl), _KUBECTL_URL], timeout=180, check=True)
    if not kind.exists():
        cl.run(["curl", "-sSLo", str(kind), _KIND_URL], timeout=180, check=True)
    return kubectl, kind


class SandboxExecutor:
    """Runs commands INSIDE a Daytona sandbox. Implements the executor contract
    that recovery.cluster.kubectl() expects (run_cmd + apply_manifest)."""

    def __init__(self, sandbox):
        self.sandbox = sandbox

    def run_cmd(self, cmd, timeout=60, check=False, quiet=False) -> Result:
        cmd_str = " ".join(shlex.quote(a) for a in cmd)
        if not quiet:
            print("  [daytona] $", cmd_str)
        resp = self.sandbox.process.exec(cmd_str, timeout=timeout)
        res = Result(resp.exit_code, (resp.result or "").strip(), "")
        if check and not res.ok:
            raise RuntimeError(f"[daytona] command failed ({res.code}): {cmd_str}\n{res.out}")
        return res

    def apply_manifest(self, manifest: str) -> Result:
        # base64 the manifest to avoid quoting/heredoc issues, decode in the sandbox
        b64 = base64.b64encode(manifest.encode()).decode()
        cmd = (f"echo {b64} | base64 -d > /tmp/manifest.yaml && "
               f"kubectl --context {config.CONTEXT} apply -f /tmp/manifest.yaml")
        print("  [daytona] $ kubectl apply -f - (via /tmp/manifest.yaml)")
        resp = self.sandbox.process.exec(cmd, timeout=60)
        return Result(resp.exit_code, (resp.result or "").strip(), "")


# Script that prepares the sandbox: start docker, install kind + kubectl, make cluster.
# NOTE: docker:*-dind is Alpine-based -> use sh + apk + wget/curl, not bash.
# Binaries are uploaded to /usr/local/bin BEFORE this runs. This script only:
# starts dockerd, makes the binaries executable, and creates the cluster.
_BOOTSTRAP = f"""
set -e

chmod +x /usr/local/bin/kubectl /usr/local/bin/kind

# 1. Start the docker daemon if it isn't already running
if ! docker info >/dev/null 2>&1; then
  echo "starting dockerd..."
  ( dockerd-entrypoint.sh dockerd >/tmp/dockerd.log 2>&1 & ) 2>/dev/null \
    || ( dockerd >/tmp/dockerd.log 2>&1 & )
fi
i=0
while [ $i -lt 60 ]; do docker info >/dev/null 2>&1 && break; i=$((i+1)); sleep 2; done
if ! docker info >/dev/null 2>&1; then
  echo "docker daemon not ready"; tail -30 /tmp/dockerd.log 2>/dev/null; exit 1
fi

# 2. Create the cluster if missing (kind pulls its node image via docker, which works)
if ! kind get clusters 2>/dev/null | grep -q "^{config.CLUSTER_NAME}$"; then
  kind create cluster --name {config.CLUSTER_NAME}
fi
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
        target = target or os.getenv("DAYTONA_TARGET", "us")
        self.daytona = Daytona(DaytonaConfig(api_key=api_key, target=target))
        self.sandbox = None
        self.executor = None

    def _activate(self, sandbox) -> None:
        """Point the harness's kubectl at this sandbox."""
        self.sandbox = sandbox
        self.executor = SandboxExecutor(sandbox)
        cl.set_executor(self.executor)

    def ensure_up(self) -> None:
        kubectl_bin, kind_bin = _ensure_local_binaries()

        print(f"[daytona] creating DinD sandbox ({DIND_IMAGE}) ...")
        sandbox = self.daytona.create(
            self._Create(
                image=DIND_IMAGE,
                resources=self._Resources(cpu=2, memory=4, disk=10),
            ),
            timeout=180,
        )
        self._activate(sandbox)

        print("[daytona] uploading kind + kubectl binaries ...")
        sandbox.fs.upload_file(str(kubectl_bin), "/usr/local/bin/kubectl")
        sandbox.fs.upload_file(str(kind_bin), "/usr/local/bin/kind")

        print("[daytona] bootstrapping (dockerd + kind create cluster) ...")
        resp = sandbox.process.exec(f"sh -c {shlex.quote(_BOOTSTRAP)}", timeout=600)
        if "BOOTSTRAP_OK" not in (resp.result or ""):
            raise RuntimeError(f"[daytona] bootstrap failed:\n{resp.result}")
        print("[daytona] cluster ready inside sandbox")

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

    # ---- Daytona-only superpowers (used in eval for byte-identical replay) ----

    def snapshot(self, name: str) -> None:
        """Freeze the current sandbox state so it can be replayed exactly."""
        print(f"[daytona] snapshot -> {name}")
        self.sandbox.create_snapshot(name, timeout=120)

    def fork(self, name: str | None = None):
        """Clone the current sandbox (copy-on-write) and activate the fork."""
        print(f"[daytona] fork current sandbox")
        forked = self.sandbox.fork(name=name, timeout=120)
        self._activate(forked)
        return forked

    def teardown(self) -> None:
        cl.set_executor(None)
        if self.sandbox is not None:
            print("[daytona] deleting sandbox")
            self.sandbox.delete()
