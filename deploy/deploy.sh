#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
test -f .env || { echo "deploy/.env missing (copy .env.example)"; exit 1; }
test -s secrets/vultr_inference_key || { echo "deploy/secrets/vultr_inference_key missing"; exit 1; }
chmod 600 secrets/vultr_inference_key
docker build -q -t repro-sandbox:latest ../sandbox
docker compose up -d --build
docker compose ps
