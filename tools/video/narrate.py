import json
import subprocess
import sys
import wave
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "narration.json"
MODEL = sys.argv[1]
OUT = Path(sys.argv[2])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    timings = {}
    for scene, lines in json.loads(SPEC.read_text()).items():
        for k, line in enumerate(lines):
            wav = OUT / f"{scene}_{k}.wav"
            subprocess.run([sys.executable, "-m", "piper", "-m", MODEL, "-f", str(wav), "--length-scale", "0.95", "--sentence-silence", "0.15"],
                           input=line.get("say", line["text"]), text=True, check=True, capture_output=True)
            with wave.open(str(wav)) as w:
                timings[f"{scene}_{k}"] = round(w.getnframes() / w.getframerate(), 3)
    (OUT / "timings.json").write_text(json.dumps(timings, indent=1))
    print("narration seconds", round(sum(timings.values()), 1), "lines", len(timings))


if __name__ == "__main__":
    main()
