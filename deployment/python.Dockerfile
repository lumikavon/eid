FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
ARG EID_SOURCE_FINGERPRINT
LABEL io.eid.source-fingerprint="${EID_SOURCE_FINGERPRINT}"
RUN groupadd --system eid && useradd --system --gid eid --create-home eid
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY edw-api/pyproject.toml edw-api/pyproject.toml
COPY edw-worker/pyproject.toml edw-worker/pyproject.toml
COPY edw-api/src edw-api/src
COPY edw-worker/src edw-worker/src
RUN --mount=type=cache,target=/root/.cache pip install uv==0.11.23 && uv sync --frozen --no-dev
USER eid
ENV PATH="/workspace/.venv/bin:$PATH" PYTHONPATH="/workspace/edw-api/src:/workspace/edw-worker/src"
