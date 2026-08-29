"""SandboxRunner implementation backed by local kind (via podman).

This is Seam 2. To move to Daytona later, write a DaytonaRunner with the same
interface that creates the kind cluster *inside* a Daytona DinD sandbox and adds
fork/snapshot. The rest of the harness is unchanged.
"""
from __future__ import annotations
import os

from .interfaces import SandboxRunner
from . import config
from .sh import run


def _env():
    e = dict(os.environ)
    e["KIND_EXPERIMENTAL_PROVIDER"] = config.PROVIDER
    return e


def kubectl(args, timeout=60, check=False, quiet=False):
    return run(["kubectl", "--context", config.CONTEXT, *args],
               timeout=timeout, check=check, quiet=quiet)


HEALTHY_MANIFEST = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {config.APP_NAME}
  namespace: {config.NAMESPACE}
  labels: {{ app: {config.APP_NAME} }}
spec:
  replicas: 1
  selector:
    matchLabels: {{ app: {config.APP_NAME} }}
  template:
    metadata:
      labels: {{ app: {config.APP_NAME} }}
    spec:
      containers:
        - name: {config.APP_NAME}
          image: {config.GOOD_IMAGE}
          ports: [{{ containerPort: 80 }}]
          readinessProbe:
            httpGet: {{ path: /, port: 80 }}
            initialDelaySeconds: 2
            periodSeconds: 3
"""


class KindRunner(SandboxRunner):
    def __init__(self):
        self.env = _env()

    def _clusters(self) -> list[str]:
        res = run(["kind", "get", "clusters"], env=self.env, quiet=True)
        return [c for c in res.out.splitlines() if c.strip()]

    def ensure_up(self) -> None:
        if config.CLUSTER_NAME in self._clusters():
            print(f"[cluster] '{config.CLUSTER_NAME}' already exists")
            return
        print(f"[cluster] creating kind cluster '{config.CLUSTER_NAME}' via {config.PROVIDER} ...")
        run(["kind", "create", "cluster", "--name", config.CLUSTER_NAME],
            env=self.env, timeout=300, check=True)

    def deploy_healthy(self) -> None:
        print("[cluster] applying healthy app")
        proc = _apply_stdin(HEALTHY_MANIFEST)
        if not proc.ok:
            raise RuntimeError(f"deploy failed: {proc.err}")
        kubectl(["rollout", "status", f"deployment/{config.APP_NAME}",
                 f"--timeout={config.ROLLOUT_TIMEOUT}s"], timeout=config.ROLLOUT_TIMEOUT + 10)

    def reset_app(self) -> None:
        """Delete + redeploy the app to a known-good baseline (cheap 'snapshot restore')."""
        kubectl(["delete", "deployment", config.APP_NAME, "--ignore-not-found"], quiet=True)
        kubectl(["delete", "secret", "app-secret", "--ignore-not-found"], quiet=True)
        self.deploy_healthy()

    def teardown(self) -> None:
        run(["kind", "delete", "cluster", "--name", config.CLUSTER_NAME], env=self.env)


def _apply_stdin(manifest: str):
    import subprocess
    print("  $ kubectl apply -f - (stdin manifest)")
    proc = subprocess.run(
        ["kubectl", "--context", config.CONTEXT, "apply", "-f", "-"],
        input=manifest, capture_output=True, text=True, timeout=60,
    )
    from .sh import Result
    return Result(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
