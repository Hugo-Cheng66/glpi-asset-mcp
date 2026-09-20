FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GLPI_REPORTS_DIR=/app/reports \
    GLPI_MCP_HTTP_HOST=0.0.0.0 \
    GLPI_MCP_HTTP_PORT=8000

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY glpi_asset_mcp ./glpi_asset_mcp
COPY pyproject.toml README.md ./

RUN mkdir -p /app/reports && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

CMD ["python", "-m", "glpi_asset_mcp.http_server"]

