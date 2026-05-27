import re
from typing import Optional
from urllib.parse import urlparse


def parse_duration_seconds(iso_duration: str) -> int:
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def is_short(duration_seconds: int, title: str) -> bool:
    if duration_seconds <= 60:
        return True
    return '#shorts' in title.lower()


def calculate_gap_score(videos: int, shorts: int, episodes: int) -> float:
    ratio = videos / max(shorts, 1)
    maturity = min(episodes / 10, 1)
    return ratio * maturity


def extract_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        return hostname.removeprefix('www.') or None
    except Exception:
        return None
