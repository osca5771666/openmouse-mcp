FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MOUSE_MCP_ENV=cloud \
    MOUSE_MCP_CLOUD_BROWSER=on \
    MOUSE_MCP_CLOUD_HEADLESS=1 \
    MOUSE_MCP_BRIDGE_HOST=127.0.0.1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir ".[cloud]"

EXPOSE 8766

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8766/healthz', timeout=3)"

CMD ["python", "-m", "mouse_mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8766", "--http-path", "/mcp", "--cloud-browser"]
