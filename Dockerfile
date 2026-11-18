FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv sync --no-dev --no-install-project
COPY . .
RUN uv sync --no-dev

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data /app/secrets \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8090
CMD ["uv", "run", "confhub", "serve", "--host", "0.0.0.0"]
