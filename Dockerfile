# leadaro-api — FastAPI service (services/api).
#
# Committed so Teploy uses THIS instead of auto-detecting: with no Dockerfile at
# the repo root it defaulted to its generic "static site" nginx template and
# tried to run `pip install ...` inside a container with no Python/pip at all
# (sh: pip: not found). This image actually has Python + the API's deps.
#
# routers/calls.py reaches INTO services/agent/dialer.py (for the compliance
# gate shared with the dialer — is_suppressed), and dialer.py reaches back into
# services/api/db.py via Path(__file__).resolve().parents[1] — both sides
# resolve the sibling directory by real file location, not by a Python package
# path. So the image must keep services/agent and services/api as siblings
# under services/, exactly like the local checkout, or the API 500s on import
# with "ModuleNotFoundError: No module named 'dialer'" the moment /calls loads.
# dialer.py's only third-party deps (dotenv, livekit.api) are already in
# services/api/requirements.txt, so nothing extra to install for it.

FROM python:3.12-slim

WORKDIR /app

COPY services/api/requirements.txt services/api/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt

COPY services/api/ services/api/
COPY services/agent/dialer.py services/agent/dialer.py

WORKDIR /app/services/api

# Respect a platform-injected $PORT; fall back to 8000 (matches local dev and
# API_BASE_URL=http://localhost:8000 in .env.example) if none is set.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
