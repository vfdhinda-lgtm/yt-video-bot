"""Free natural voice with Microsoft Edge TTS (no account needed).
If a scene fails, it cleans the text, tries backup voices, and finally reads it sentence by sentence."""
import asyncio
import os
import re
import subprocess
import time

import edge_tts

from bot import config

BACKUP_VOICES = ["en-US-ChristopherNeural", "en-US-GuyNeural", "en-US-BrianNeural"]


async def _say(text, path, voice):
    await edge_tts.Communicate(text, voice, rate=config.get("voice_rate")).save(path)


def clean(text):
    t = (text.replace("&", " and ").replace("—", ", ").replace("–", ", ").replace("…", "...")
             .replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"'))
    t = re.sub(r"[<>{}\[\]*_#~|\\^`]", " ", t)
    t = re.sub(r"[^\x20-\x7E]", " ", t)          # drop emojis / unusual symbols
    return re.sub(r"\s+", " ", t).strip()


def _try(text, path, voice):
    try:
        asyncio.run(_say(text, path, voice))
        return os.path.exists(path) and os.path.getsize(path) > 1000
    except Exception as e:  # noqa: BLE001
        print(f"  voice failed ({voice}): {str(e)[:120]}")
        return False


def _by_sentences(text, path, voice):
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if re.search(r"[A-Za-z0-9]", p)]
    files = []
    for i, p in enumerate(parts):
        f = f"{path}.part{i}.mp3"
        if not (_try(p, f, voice) or _try(p, f, BACKUP_VOICES[0])):
            return False
        files.append(f)
        time.sleep(0.5)
    if not files:
        return False
    lst = f"{path}.txt"
    with open(lst, "w") as fh:
        fh.writelines(f"file '{os.path.abspath(f)}'\n" for f in files)
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", path])
    return r.returncode == 0 and os.path.getsize(path) > 1000


def make_voice(text, path):
    main = config.get("voice")
    cleaned = clean(text)
    plan = [(text, main), (cleaned, main)]
    for attempt in range(3):
        for t, v in plan + [(cleaned, b) for b in BACKUP_VOICES if b != main]:
            if t and _try(t, path, v):
                return
        print("  trying sentence by sentence...")
        if _by_sentences(cleaned, path, main):
            return
        time.sleep(20 * (attempt + 1))   # maybe Microsoft is limiting requests; wait and retry
    raise RuntimeError(f"Voice could not be made for: {text[:150]}")


def make_all(scenes, folder, progress=None):
    paths = []
    for i, s in enumerate(scenes):
        p = os.path.join(folder, f"voice_{i:03d}.mp3")
        print(f"Voice {i + 1}/{len(scenes)}")
        if progress and i % 10 == 0:
            progress(f"Voice {i + 1}/{len(scenes)}")
        make_voice(s["narration"].strip(), p)
        paths.append(p)
        time.sleep(0.7)   # small gap so Microsoft does not block us
    return paths
