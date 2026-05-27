import time

import click
from googleapiclient.discovery import build

from config import YOUTUBE_API_KEY
from stages.spotify_scraper import scrape_spotify_leads
from stages.youtube import find_channel, get_shorts_gap
from utils import calculate_gap_score
from writer import write_csv


def _retry_find_channel(youtube, name: str, retries: int = 3):
    for attempt in range(retries):
        try:
            return find_channel(youtube, podcast_name=name, podcast_website='')
        except Exception as exc:
            if '429' in str(exc) and attempt < retries - 1:
                wait = 60 * (attempt + 1)
                click.echo(f'\n  [rate limited, waiting {wait}s...]', nl=False)
                time.sleep(wait)
            else:
                raise


@click.command()
@click.option('--keywords', default='entrepreneurship,coaching,marketing,investing,business,founder',
              show_default=True, help='Comma-separated Spotify search keywords')
@click.option('--max-emails', default=50, show_default=True,
              help='Max emails to fetch per Apify run')
@click.option('--output', default='prospects.csv', show_default=True,
              help='Output CSV path')
def main(keywords: str, max_emails: int, output: str):
    keyword_list = [k.strip() for k in keywords.split(',')]
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    prospects = []

    click.echo(f'Scraping Spotify for keywords: {", ".join(keyword_list)} (max {max_emails} emails)...')
    leads = scrape_spotify_leads(keywords=keyword_list, max_emails=max_emails)
    click.echo(f'Got {len(leads)} leads with emails. Checking YouTube gaps...\n')

    for i, lead in enumerate(leads, 1):
        name = lead['podcast_name']
        email = lead['email']
        click.echo(f'[{i}/{len(leads)}] {name}', nl=False)

        try:
            channel = _retry_find_channel(youtube, name)
            if not channel:
                click.echo(' — no YouTube match, skipping')
                continue

            gap = get_shorts_gap(youtube, uploads_playlist_id=channel['uploads_playlist_id'])

            if gap['yt_videos_90d'] == 0:
                click.echo(' — no recent YouTube videos, skipping')
                continue

            score = calculate_gap_score(
                videos=gap['yt_videos_90d'],
                shorts=gap['yt_shorts_90d'],
                episodes=50,
            )

            prospects.append({
                'podcast_name': name,
                'host_email': email,
                'youtube_channel_url': channel['channel_url'],
                'yt_videos_90d': gap['yt_videos_90d'],
                'yt_shorts_90d': gap['yt_shorts_90d'],
                'gap_score': round(score, 2),
                'keyword': lead['keyword'],
                'spotify_url': lead['spotify_url'],
            })
            click.echo(f' — gap score {score:.1f} ✓')

        except Exception as exc:
            click.echo(f' — error ({type(exc).__name__}: {exc}), skipping')
        finally:
            time.sleep(2)  # YouTube search quota: ~30 req/min safe limit

    prospects.sort(key=lambda p: p['gap_score'], reverse=True)
    click.echo(f'\n{len(prospects)} qualified prospects found.')
    write_csv(prospects, output)


if __name__ == '__main__':
    main()
