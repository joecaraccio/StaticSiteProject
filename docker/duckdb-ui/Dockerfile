# DuckDB's built-in web UI, exposed outside the container.
#
# The UI's HTTP server binds 127.0.0.1, so socat forwards 0.0.0.0:4213 to it.
# That is the only reason this image differs from the pipeline image.
FROM usually-late/pipeline:dev AS base

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends socat curl \
    && rm -rf /var/lib/apt/lists/*

COPY docker/duckdb-ui/serve.py /opt/duckdb-ui/serve.py
COPY docker/duckdb-ui/entrypoint.sh /opt/duckdb-ui/entrypoint.sh
RUN chmod +x /opt/duckdb-ui/entrypoint.sh \
    && mkdir -p /duckdb-extensions \
    && chown -R pipeline:pipeline /duckdb-extensions /opt/duckdb-ui

USER pipeline
EXPOSE 4213
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:4213/ >/dev/null || exit 1
ENTRYPOINT ["/opt/duckdb-ui/entrypoint.sh"]
