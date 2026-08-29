"""FaultInjector: break the running deployment in defined, repeatable ways.

Each fault returns a `recent_change` dict = the diff that shipped. That diff is
legitimate evidence the agent gets to see (DeployGuard gathers it in production).
It is NOT the answer key: the agent must still reason about what to do with it.
"""
from __future__ import annotations

from . import config
from .cluster import kubectl

BAD_IMAGE = "nginx:9.9.9-doesnotexist"


def inject(fault: str) -> dict:
    if fault == "bad_image":
        return _bad_image()
    if fault == "missing_secret":
        return _missing_secret()
    if fault == "oom_kill":
        return _oom_kill()
    if fault == "bad_readiness_probe":
        return _bad_readiness_probe()
    if fault == "bad_command":
        return _bad_command()
    raise ValueError(f"unknown fault: {fault}")


def _bad_image() -> dict:
    kubectl(["set", "image", f"deployment/{config.APP_NAME}",
             f"{config.APP_NAME}={BAD_IMAGE}"], check=True)
    return {
        "kind": "image_update",
        "field": "spec.template.spec.containers[0].image",
        "old_image": config.GOOD_IMAGE,
        "new_image": BAD_IMAGE,
    }


def _missing_secret() -> dict:
    # Add an env var sourced from a secret that does not exist -> CreateContainerConfigError.
    patch = (
        '{"spec":{"template":{"spec":{"containers":[{"name":"%s",'
        '"env":[{"name":"API_KEY","valueFrom":{"secretKeyRef":'
        '{"name":"app-secret","key":"API_KEY"}}}]}]}}}}' % config.APP_NAME
    )
    kubectl(["patch", "deployment", config.APP_NAME, "--type", "strategic",
             "-p", patch], check=True)
    return {
        "kind": "env_added",
        "field": "spec.template.spec.containers[0].env",
        "added_env": "API_KEY",
        "secret_ref": {"name": "app-secret", "key": "API_KEY"},
        "secret_exists": False,
    }


def _oom_kill() -> dict:
    # Set memory limit so low (4Mi) that nginx OOMKills immediately -> OOMKilled.
    patch = (
        '{"spec":{"template":{"spec":{"containers":[{"name":"%s",'
        '"resources":{"limits":{"memory":"4Mi"},'
        '"requests":{"memory":"4Mi"}}}]}}}}' % config.APP_NAME
    )
    kubectl(["patch", "deployment", config.APP_NAME, "--type", "strategic",
             "-p", patch], check=True)
    return {
        "kind": "resource_limits_changed",
        "field": "spec.template.spec.containers[0].resources",
        "old_memory_limit": "128Mi",
        "new_memory_limit": "4Mi",
        "change_reason": "cost-optimisation PR",
    }


def _bad_readiness_probe() -> dict:
    # Point the readiness probe at a path that does not exist -> pod runs but never Ready.
    patch = (
        '{"spec":{"template":{"spec":{"containers":[{"name":"%s",'
        '"readinessProbe":{"httpGet":{"path":"/healthz-nonexistent","port":80},'
        '"initialDelaySeconds":2,"periodSeconds":3}}]}}}}' % config.APP_NAME
    )
    kubectl(["patch", "deployment", config.APP_NAME, "--type", "strategic",
             "-p", patch], check=True)
    return {
        "kind": "readiness_probe_changed",
        "field": "spec.template.spec.containers[0].readinessProbe.httpGet.path",
        "old_path": "/",
        "new_path": "/healthz-nonexistent",
        "change_reason": "health-check standardisation PR",
    }


def _bad_command() -> dict:
    # Override the container command with a broken nginx directive -> the process
    # exits immediately -> CrashLoopBackOff. No pattern the rule brain recognizes;
    # the fix value is intentionally NOT in the diff, so the agent must reason.
    patch = (
        '{"spec":{"template":{"spec":{"containers":[{"name":"%s",'
        '"command":["nginx","-g","daemXon off;"]}]}}}}' % config.APP_NAME
    )
    kubectl(["patch", "deployment", config.APP_NAME, "--type", "strategic",
             "-p", patch], check=True)
    return {
        "kind": "command_changed",
        "field": "spec.template.spec.containers[0].command",
        "change_reason": "startup-hardening PR",
    }
