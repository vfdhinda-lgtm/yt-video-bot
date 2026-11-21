"""All settings in one place. Panel settings (if any) override environment variables."""
import os

STYLES = {
    "illustration": "detailed 2D digital illustration, clean line art, painterly shading, consistent "
                    "character design, warm cinematic lighting, historically accurate clothing and setting",
    "painting": "cinematic semi-realistic digital painting, soft warm natural light, highly detailed, "
                "historically accurate clothing and setting, documentary mood",
    "realistic": "photorealistic cinematic film still, 35mm, natural light, shallow depth of field, "
                 "historically accurate clothing and setting",
}

DEFAULTS = {
    "voice": "en-US-AndrewNeural",
    "voice_rate": "-5%",
    "words": "1800",
    "scenes": "45",
    "style": "illustration",
    "subtitles": "1",
    "sfx": "1",
    "music_volume": "0.10",
    "sfx_volume": "0.25",
    "publish_hour_utc": "15",
    "privacy": "public",
}

_cfg = {}


def load(panel_settings=None):
    _cfg.clear()
    for k, v in DEFAULTS.items():
        _cfg[k] = os.environ.get(k.upper(), v)
    for k, v in (panel_settings or {}).items():
        if v is not None and str(v) != "":
            _cfg[k] = str(v)


def get(key):
    if not _cfg:
        load()
    return _cfg.get(key, DEFAULTS.get(key, ""))


def on(key):
    return get(key).lower() in ("1", "true", "yes", "on")


def style_text():
    s = get("style")
    return STYLES.get(s, s)  # a custom style sentence is also allowed
