# leadaro agent workers (services/agent) — ONE image, three roles.
#
# worker.py / dialer.py / post_call.py share almost all deps and both live in
# services/agent, so they build from a single image and pick their role at
# runtime from the AGENT_ROLE env var (Teploy can always set an env var, even
# where it can't set a custom Dockerfile path or start command).
#
# These are background loops with NO HTTP server, so each Teploy app running
# this image must have "Skip health check" ticked — an HTTP health probe would
# never succeed and the deploy would hang at "deploying".
#
# Sibling layout is load-bearing: worker/dialer/post_call resolve services/api
# (shared db.py + llm.py) via Path(__file__).resolve().parents[1] / "api", so
# services/agent and services/api must sit side by side under /app/services,
# exactly like the repo.

FROM python:3.12-slim

# onnxruntime (pulled in by livekit-plugins-silero for VAD) needs libgomp.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/agent/requirements.txt services/agent/requirements.txt
RUN pip install --no-cache-dir -r services/agent/requirements.txt

COPY services/agent/ services/agent/
COPY services/api/ services/api/

WORKDIR /app/services/agent

# Default role; override per Teploy app:
#   AGENT_ROLE=worker     -> LiveKit voice worker (handles live calls)
#   AGENT_ROLE=dialer     -> outbound dialer loop
#   AGENT_ROLE=post_call  -> after-call analysis + stale-call reaper
ENV AGENT_ROLE=worker

CMD case "$AGENT_ROLE" in \
      worker)    exec python worker.py start ;; \
      dialer)    exec python dialer.py ;; \
      post_call) exec python post_call.py ;; \
      *) echo "AGENT_ROLE must be worker|dialer|post_call, got '$AGENT_ROLE'" >&2; exit 1 ;; \
    esac
