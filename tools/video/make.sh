#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
WORK=${WORK:-$HOME/repro-video}
VOICE_URL=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high
AVAIL=$(free -g | awk '/^Mem:/{print $7}')
[ "$AVAIL" -ge 12 ] || { echo "only ${AVAIL}G available, need 12G"; exit 3; }
mkdir -p "$WORK/voice" "$WORK/out"
for f in en_US-ljspeech-high.onnx en_US-ljspeech-high.onnx.json; do
  [ -s "$WORK/voice/$f" ] || curl -sfL -o "$WORK/voice/$f" "$VOICE_URL/$f"
done
docker build -q --cpu-quota=300000 --memory=4g -t repro-video:1 "$ROOT/tools/video" >/dev/null
RUN=(docker run --rm --network host --memory=4g --cpus=3 -e PYTHONDONTWRITEBYTECODE=1 -v "$ROOT":/src:ro -v "$WORK":/w repro-video:1)
STEP=${1:-all}
shift || true
case "$STEP" in
  narrate|all) "${RUN[@]}" python3 /src/tools/video/narrate.py /w/voice/en_US-ljspeech-high.onnx /w/tts ;;&
  record|all) "${RUN[@]}" sh -c 'rm -rf /w/rec && python3 /src/tools/video/record.py /w/rec /w/tts "$@"' sh "$@" ;;&
  render|all) "${RUN[@]}" python3 /src/tools/video/render.py /w /w/out/repro-demo.mp4 ;;
esac
