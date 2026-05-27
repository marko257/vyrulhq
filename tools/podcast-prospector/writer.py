import csv
from pathlib import Path

import click

FIELDNAMES = [
    'podcast_name',
    'host_email',
    'youtube_channel_url',
    'yt_videos_90d',
    'yt_shorts_90d',
    'gap_score',
    'keyword',
    'spotify_url',
]


def write_csv(prospects: list[dict], output_path: str) -> None:
    """Write full prospects list (overwrites). Used for header-only init and final sorted write."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(prospects)


def append_csv(prospect: dict, output_path: str) -> None:
    """Append a single prospect row — called immediately when a prospect qualifies."""
    path = Path(output_path)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writerow(prospect)
