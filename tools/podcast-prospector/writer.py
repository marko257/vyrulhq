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
    'category',
    'episode_count',
]


def write_csv(prospects: list[dict], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(prospects)
    if not prospects:
        click.echo(f'Warning: 0 prospects found. CSV written with header only to {path}')
    else:
        click.echo(f'Wrote {len(prospects)} prospects to {path}')
