FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates build-essential procps nodejs npm \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 1000 --create-home --home-dir /home/repro --shell /bin/bash repro \
 && git config --system safe.directory '*' \
 && git config --system advice.detachedHead false \
 && git config --system init.defaultBranch main
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 GPG_KEY="" PYTHON_SHA256=""
USER repro
WORKDIR /work
CMD ["sleep", "infinity"]
