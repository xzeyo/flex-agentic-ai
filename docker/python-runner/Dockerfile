FROM python:3.12.12-slim-bookworm
RUN pip install --no-cache-dir pytest==8.4.2 ruff==0.14.1 \
    && groupadd --gid 10001 runner \
    && useradd --uid 10001 --gid runner --no-create-home runner \
    && mkdir /input /workspace /runner \
    && chmod 755 /input /workspace /runner
COPY execute.py pytest.ini /runner/
USER 10001:10001
WORKDIR /workspace
CMD ["python", "-I", "/runner/execute.py", "test"]
