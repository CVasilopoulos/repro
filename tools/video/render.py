import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

WORK = Path(sys.argv[1])
FINAL = Path(sys.argv[2])
REC = WORK / "rec"
TTS = WORK / "tts"
SR = 22050
FPS = 30


def main():
    tl = json.loads((REC / "timeline.json").read_text())
    frames = tl["frames"]
    start, end = tl["start"], tl["end"]
    fast = tl["fast"]

    def out_time(t):
        total = t - start
        for a, b, speed in fast:
            if t > a:
                total -= (min(t, b) - a) * (1 - 1 / speed)
        return total

    frames = [f for f in frames if start <= f["ts"] <= end]
    total = out_time(end)
    with open(REC / "concat.txt", "w") as f:
        for cur, nxt in zip(frames, frames[1:] + [{"ts": end}]):
            f.write(f"file '{REC / 'frames' / cur['file']}'\nduration {max(out_time(nxt['ts']) - out_time(cur['ts']), 0.001):.4f}\n")
        f.write(f"file '{REC / 'frames' / frames[-1]['file']}'\n")
    audio = np.zeros(int(total * SR) + SR, dtype=np.float32)
    srt = []
    for line in tl["lines"]:
        with wave.open(str(TTS / f"{line['id']}.wav")) as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
            dur = w.getnframes() / w.getframerate()
        at = out_time(line["t"])
        i = int(at * SR)
        audio[i:i + len(data)] += data[:len(audio) - i]
        srt.append((at, at + dur + 0.25, line["text"]))
    wav = WORK / "out_audio.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio[:int(total * SR)], -1, 1) * 32767).astype(np.int16).tobytes())
    FINAL.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(REC / "concat.txt"), "-i", str(wav),
                    "-vf", f"scale=1920:1080:flags=lanczos,fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-threads", "3", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                    "-movflags", "+faststart", "-shortest", str(FINAL)], check=True)

    def stamp(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    with open(FINAL.with_suffix(".srt"), "w") as f:
        for i, (a, b, text) in enumerate(srt, 1):
            f.write(f"{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n\n")
    print("video seconds", round(total, 1), "frames", len(frames), "bytes", FINAL.stat().st_size)


if __name__ == "__main__":
    main()
