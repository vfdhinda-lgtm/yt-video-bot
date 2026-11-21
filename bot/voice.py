"""Free natural voice with Microsoft Edge TTS (no account needed)."""
import asyncio
import os
import time

import edge_tts

from bot import config


async def _say(text, path):
    await edge_tts.Communicate(text, config.get("voice"), rate=config.get("voice_rate")).save(path)


def make_voice(text, path):
    for attempt in range(5):
        try:
            asyncio.run(_say(text, path))
            if os.path.getsize(path) > 1000:
                return
        except Exception as e:  # noqa: BLE001
            print(f"  voice try {attempt + 1} failed ({e})")
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("Voice could not be made")


def make_all(scenes, folder, progress=None):
    paths = []
    for i, s in enumerate(scenes):
        p = os.path.join(folder, f"voice_{i:03d}.mp3")
        print(f"Voice {i + 1}/{len(scenes)}")
        if progress and i % 10 == 0:
            progress(f"Voice {i + 1}/{len(scenes)}")
        make_voice(s["narration"].strip(), p)
        paths.append(p)
    return paths
