"""Automatic professional editing with FFmpeg:
slow zoom/pan, cinematic vignette, chapter titles ("AGE 7"), subtitles, fade transitions between
life stages, sound effects under each scene, background music, and YouTube chapters."""
import glob
import os
import random
import re
import subprocess

from bot import config, sfx

FPS = 24
PAUSE = 0.45   # breath after each scene (seconds)
FADE = 0.35    # dip-to-black between life stages

ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,56,&H00FFFFFF,&H000000FF,&H00101010,&H96000000,-1,0,0,0,100,100,0,0,1,4,2,2,160,160,70,1
Style: Chap,DejaVu Serif,120,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,6,0,1,5,4,5,100,100,0,1
Style: Sub,DejaVu Sans,46,&H0040D4FF,&H000000FF,&H00000000,&H00000000,-1,1,0,0,100,100,2,0,1,3,2,5,100,100,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}...\n{r.stderr[-1500:]}")


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    return float(out.stdout.strip())


def _t(sec):
    sec = max(sec, 0)
    h, m = int(sec // 3600), int(sec % 3600 // 60)
    return f"{h}:{m:02d}:{sec % 60:05.2f}"


def _esc(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _chunks(text, max_words=7):
    words, out, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or (len(cur) >= 3 and re.search(r"[.!?;:,]$", w)):
            out.append(" ".join(cur))
            cur = []
    if cur:
        if out and len(cur) <= 2:
            out[-1] += " " + " ".join(cur)
        else:
            out.append(" ".join(cur))
    return out


def scene_ass(path, scene, speech_sec, index, total):
    lines = [ASS_HEAD]
    if config.on("subtitles"):
        parts = _chunks(scene["narration"])
        weights = [len(p) + 3 for p in parts]
        t, total_w = 0.05, sum(weights)
        for p, w in zip(parts, weights):
            d = speech_sec * w / total_w
            lines.append(f"Dialogue: 0,{_t(t)},{_t(t + d)},Cap,,0,0,0,,{_esc(p)}\n")
            t += d
    chap = scene.get("chapter", "")
    if chap:
        end = min(3.2, total - 0.2)
        lines.append(f"Dialogue: 1,{_t(0.25)},{_t(end)},Chap,,0,0,0,,"
                     f"{{\\fad(450,450)\\pos(960,500)}}{_esc(chap.upper())}\n")
        lines.append(f"Dialogue: 1,{_t(0.45)},{_t(end)},Sub,,0,0,0,,"
                     f"{{\\fad(450,450)\\pos(960,600)}}━━━━━━━\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _motion(i, frames):
    inc = 0.13 / frames
    kind = i % 4
    if kind == 0:   # zoom in
        return f"1+{inc}*on", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if kind == 1:   # zoom out
        return f"1.13-{inc}*on", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if kind == 2:   # pan left to right
        return "1.13", f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"
    return "1.13", f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-(ih/zoom/2)"


def scene_clip(i, img, seconds, ass_name, fade_in, fade_out, out, work):
    frames = max(int(round(seconds * FPS)), FPS)
    z, x, y = _motion(i, frames)
    vf = (f"scale=2880:1620,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s=1920x1080:fps={FPS},"
          f"vignette=angle=PI/6,ass={ass_name}")
    if fade_in:
        vf += f",fade=t=in:st=0:d={FADE}"
    if fade_out:
        vf += f",fade=t=out:st={frames / FPS - FADE:.3f}:d={FADE}"
    vf += ",format=yuv420p"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.abspath(img), "-vf", vf,
         "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-r", str(FPS), os.path.abspath(out)], cwd=work)


def scene_audio(mp3, effect, out):
    speech = duration(mp3)
    total = speech + PAUSE
    if effect:
        vol = config.get("sfx_volume")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-i", effect, "-filter_complex",
             f"[0:a]aresample=44100,apad=pad_dur={PAUSE}[v];"
             f"[1:a]aresample=44100,atrim=0:{total:.3f},volume={vol},afade=t=in:d=0.4,"
             f"afade=t=out:st={max(total - 1.0, 0):.3f}:d=1.0[s];"
             f"[v][s]amix=inputs=2:duration=first:normalize=0",
             "-ar", "44100", "-ac", "2", out])
    else:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-af", f"apad=pad_dur={PAUSE}",
             "-ar", "44100", "-ac", "2", out])
    return speech, duration(out)


def build(meta, images, voices, work, out_path, progress=None):
    """Returns the start time (seconds) of every scene."""
    scenes = meta["scenes"]
    wavs, clips, starts, t = [], [], [], 0.0
    for i, (sc, img, mp3) in enumerate(zip(scenes, images, voices)):
        if progress and i % 5 == 0:
            progress(f"Editing scene {i + 1}/{len(scenes)}")
        effect = sfx.get(sc.get("sfx"), work) if config.on("sfx") else None
        wav = os.path.join(work, f"a_{i:03d}.wav")
        speech, sec = scene_audio(mp3, effect, wav)
        ass_name = f"s_{i:03d}.ass"
        scene_ass(os.path.join(work, ass_name), sc, speech, i, sec)
        nxt = scenes[i + 1] if i + 1 < len(scenes) else None
        clip = os.path.join(work, f"v_{i:03d}.mp4")
        print(f"Editing scene {i + 1}/{len(scenes)} ({sec:.1f}s){' +sfx' if effect else ''}")
        scene_clip(i, img, sec, ass_name, fade_in=(i == 0 or bool(sc.get("chapter"))),
                   fade_out=(nxt is None or bool(nxt.get("chapter"))), out=clip, work=work)
        starts.append(t)
        t += round(sec * FPS) / FPS
        wavs.append(wav)
        clips.append(clip)

    def concat_list(files, name):
        p = os.path.join(work, name)
        with open(p, "w") as f:
            for c in files:
                f.write(f"file '{os.path.abspath(c)}'\n")
        return p

    if progress:
        progress("Joining scenes + music")
    video = os.path.join(work, "video_only.mp4")
    narration = os.path.join(work, "narration.wav")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", concat_list(clips, "clips.txt"), "-c", "copy", video])
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", concat_list(wavs, "wavs.txt"), "-c", "copy", narration])

    music = sorted(glob.glob("music/*.mp3") + glob.glob("music/*.m4a") + glob.glob("music/*.wav"))
    nd = duration(narration)
    if music:
        track = random.choice(music)
        print(f"Background music: {track}")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", narration,
             "-stream_loop", "-1", "-i", track, "-filter_complex",
             f"[2:a]aresample=44100,volume={config.get('music_volume')},afade=t=in:d=2,"
             f"afade=t=out:st={max(nd - 4, 0):.2f}:d=4[m];"
             f"[1:a][m]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", "-movflags", "+faststart", out_path])
    else:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", narration,
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", "-movflags", "+faststart", out_path])
    return starts


def youtube_chapters(meta, starts):
    """'0:00 Intro / 0:35 Birth / ...' for the description (YouTube needs 3+, each 10s+)."""
    items = [(0.0, "Intro" if not meta["scenes"][0].get("chapter") else meta["scenes"][0]["chapter"])]
    for sc, st in zip(meta["scenes"][1:], starts[1:]):
        if sc.get("chapter") and st - items[-1][0] >= 10:
            items.append((st, sc["chapter"]))
    if len(items) < 3:
        return ""

    def fmt(s):
        s = int(s)
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"

    return "Chapters:\n" + "\n".join(f"{fmt(s)} {name}" for s, name in items)
