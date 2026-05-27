import csv
from pathlib import Path

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
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(prospects)
    print(f'Wrote {len(prospects)} prospects to {path}')
