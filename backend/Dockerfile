FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 ghost
WORKDIR /srv
COPY requirements.txt requirements-dev.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# docker build --target test . runs the suite on Linux, where symlink tests are not skipped.
FROM base AS test
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY app ./app
COPY tests ./tests
USER ghost
ENV HOME=/home/ghost
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider"]

FROM base AS runtime
COPY app ./app
RUN mkdir -p /data && chown ghost:ghost /data
USER ghost
ENV GHOSTREPO_DATABASE_URL=sqlite:////data/ghostrepo.db \
    GHOSTREPO_WORKSPACE_ROOT=/workspace
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request as u; u.urlopen(u.Request('http://localhost:8000/api/health'), timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
