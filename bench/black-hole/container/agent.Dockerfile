FROM node:22.20.0-bookworm-slim
ARG CODEX_VERSION=0.159.0
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    python3 git ripgrep ca-certificates procps \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --ignore-scripts --no-audit --no-fund @openai/codex@${CODEX_VERSION} \
    && useradd --create-home --uid 1001 bench
COPY cell.py /opt/benchmark/cell.py
USER bench
WORKDIR /home/bench
ENTRYPOINT ["python3", "/opt/benchmark/cell.py"]
