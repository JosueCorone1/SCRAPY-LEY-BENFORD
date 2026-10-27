"""Instagram cookie settings and Gemini configuration (secrets stay local)."""
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv():
    path = ROOT / '.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))


_load_dotenv()


def _seconds_setting(name, default, minimum=0.0):
    try:
        value = float(os.environ.get(name, default))
    except (ValueError, TypeError):
        return float(default)
    return max(minimum, value) if math.isfinite(value) else float(default)


INSTAGRAM_REQUEST_INTERVAL_SECONDS = _seconds_setting('INSTAGRAM_REQUEST_INTERVAL_SECONDS', 2.0, 1.0)
INSTAGRAM_RATE_LIMIT_COOLDOWN_SECONDS = _seconds_setting('INSTAGRAM_RATE_LIMIT_COOLDOWN_SECONDS', 900, 1.0)


def instagram_cookies():
    return os.environ.get('INSTAGRAM_COOKIES', '').strip() or None


def gemini_api_key():
    return (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or '').strip()


def gemini_model():
    return os.environ.get('GEMINI_MODEL', 'gemini-flash-latest').strip() or 'gemini-flash-latest'


def playwright_headless():
    return os.environ.get('PLAYWRIGHT_HEADLESS', 'false').casefold() in {'1', 'true', 'yes'}


def playwright_max_scrolls():
    return int(_seconds_setting('PLAYWRIGHT_MAX_SCROLLS', 300, 1))
