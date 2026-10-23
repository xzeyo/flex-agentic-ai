FROM python:3.12.12-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.33
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH" TEAM_DATA_DIR=/data OTEL_SDK_DISABLED=true CREWAI_TRACING_ENABLED=false
# The trusted controller needs Docker access; generated code runs in separate non-root containers.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "75"]
