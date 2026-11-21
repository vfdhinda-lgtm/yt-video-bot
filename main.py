"""Daily AI video bot:
topic -> script -> consistent-character images -> voice -> pro editing (subtitles, chapters, SFX, music)
-> thumbnail -> YouTube upload. Reports every step to your admin panel."""
import json
import os
import random
import shutil
import sys
import traceback

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

from bot import config, images, panel, script_gen, thumbnail, video, voice  # noqa: E402


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def topic_from_files():
    done = read_lines("done.txt")
    done_low = {d.lower() for d in done}
    for t in read_lines("topics.txt"):
        if t.lower() not in done_low:
            return t
    return script_gen.new_topic(done)


def main():
    no_upload = "--no-upload" in sys.argv or os.environ.get("UPLOAD", "true").lower() == "false"
    trigger = os.environ.get("TRIGGER", "manual")
    job_id, topic = None, None

    if panel.enabled():
        job = panel.next_job(trigger)
        if not job.get("ok"):
            print(f"Nothing to do: {job.get('reason', 'panel did not answer')}")
            return
        job_id = job["job_id"]
        config.load(job.get("settings"))
        topic = (job.get("topic") or "").strip()
        if not topic:
            topic = script_gen.new_topic(job.get("done", []))
        panel.download_music()
    else:
        config.load()
        topic = topic_from_files()

    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL')}/{os.environ.get('GITHUB_REPOSITORY')}"
                   f"/actions/runs/{os.environ['GITHUB_RUN_ID']}")

    def progress(msg):
        print(f">> {msg}")
        panel.update(job_id, status="running", message=msg)

    panel.update(job_id, status="running", message="Writing script", title=topic, run_url=run_url)
    print(f"TOPIC: {topic}")

    work = os.path.join(ROOT, "output", "work")
    final = os.path.join(ROOT, "output", "final")
    shutil.rmtree(os.path.join(ROOT, "output"), ignore_errors=True)
    os.makedirs(work)
    os.makedirs(final)

    try:
        meta = script_gen.write_script(topic)
        progress(f"Script ready: {len(meta['scenes'])} scenes, {len(meta['characters'])} characters")

        seed = random.randint(1, 5_000_000)
        imgs = images.make_all(meta, work, seed, progress)
        thumb_src = os.path.join(work, "thumb_src.jpg")
        tp = meta.get("thumbnail_prompt") or meta["scenes"][0]["image_prompt"]
        if not images.make_image(images.build_prompt(tp, meta["characters"]), thumb_src,
                                 images.scene_seed({"characters": ["YOU"]}, seed, 0)):
            thumb_src = imgs[0]
        thumb = thumbnail.make(thumb_src, meta.get("thumbnail_text") or topic,
                               os.path.join(final, "thumbnail.jpg"))

        voices = voice.make_all(meta["scenes"], work, progress)
        out = os.path.join(final, "video.mp4")
        starts = video.build(meta, imgs, voices, work, out, progress)
        chapters = video.youtube_chapters(meta, starts)
        if chapters:
            meta["description"] = f"{meta.get('description', '').strip()}\n\n{chapters}"
        minutes = video.duration(out) / 60
        print(f"Video ready: {out} ({minutes:.1f} min)")
        with open(os.path.join(final, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        vid = ""
        if not no_upload:
            progress("Uploading to YouTube")
            from bot import upload
            vid = upload.upload(out, thumb, meta, progress)

        panel.update(job_id, status="done", title=meta["title"], youtube_id=vid,
                     message=f"Done: {minutes:.1f} min video" + ("" if vid else " (not uploaded, download from GitHub)"))
        if not panel.enabled():
            with open("done.txt", "a", encoding="utf-8") as f:
                f.write(topic + "\n")
        shutil.rmtree(work, ignore_errors=True)
        print("ALL DONE")
    except Exception as e:
        traceback.print_exc()
        panel.update(job_id, status="failed", message=f"{type(e).__name__}: {e}"[:1500])
        sys.exit(1)


if __name__ == "__main__":
    main()
