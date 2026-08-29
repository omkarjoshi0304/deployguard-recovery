"""Central constants shared across the harness."""

# Cluster / provider
CLUSTER_NAME = "recovery"
CONTEXT = f"kind-{CLUSTER_NAME}"
PROVIDER = "podman"  # kind uses KIND_EXPERIMENTAL_PROVIDER=podman

# The app under test
NAMESPACE = "default"
APP_NAME = "web"
APP_LABEL = "app=web"

# A real, small, known-good image. Faults move the deployment away from this;
# a correct fix restores compatibility (not necessarily this exact tag).
GOOD_IMAGE = "nginx:1.27-alpine"

# Rollout wait budget (seconds)
ROLLOUT_TIMEOUT = 60

# The set of faults we know how to inject + score.
# Training faults (used for the learning loop)
FAULTS = ["bad_image", "missing_secret", "oom_kill", "bad_readiness_probe", "bad_command"]

# Held-out fault (NEVER touched during training — only used in final eval).
# bad_command has no matching rule branch, so the rule-based baseline (A) fails it
# while the LLM (B/C) reason a fix — this is what breaks the A=B=C tie.
HELD_OUT_FAULT = "bad_command"

# Training-only faults (exclude the held-out one)
TRAINING_FAULTS = [f for f in FAULTS if f != HELD_OUT_FAULT]
