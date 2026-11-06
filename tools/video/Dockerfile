FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg fonts-inter && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --break-system-packages playwright==1.55.0 piper-tts==1.3.0 numpy
