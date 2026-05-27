import time

import click
from googleapiclient.discovery import build

from config import YOUTUBE_API_KEY
from stages.spotify_scraper import scrape_spotify_leads
from stages.youtube import find_channel, get_shorts_gap
from utils import calculate_gap_score
from writer import write_csv, append_csv


class QuotaExhausted(Exception):
    """YouTube daily quota has been used up — no point retrying."""


def _retry_find_channel(youtube, name: str, retries: int = 3):
    for attempt in range(retries):
        try:
            return find_channel(youtube, podcast_name=name, podcast_website='')
        except Exception as exc:
            msg = str(exc)
            # Both daily and per-minute limits return rateLimitExceeded — tell them apart by message
            if 'per day' in msg or 'quotaExceeded' in msg:
                raise QuotaExhausted('YouTube daily quota exhausted') from exc
            if ('rateLimitExceeded' in msg or '429' in msg) and attempt < retries - 1:
                wait = 30 * (attempt + 1)
                click.echo(f'\n  [rate limited, waiting {wait}s...]', nl=False)
                time.sleep(wait)
            else:
                raise


@click.command()
@click.option('--keywords', default='entrepreneurship,coaching,marketing,investing,business,founder,podcaster',
              show_default=True, help='Comma-separated Spotify search keywords')
@click.option('--max-emails', default=200, show_default=True,
              help='Max emails to fetch per Apify run')
@click.option('--output', default='prospects.csv', show_default=True,
              help='Output CSV path')
def main(keywords: str, max_emails: int, output: str):
    keyword_list = [k.strip() for k in keywords.split(',')]
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    prospects = []
    checked = 0

    click.echo(f'Scraping Spotify for keywords: {", ".join(keyword_list)} (max {max_emails} emails)...')
    leads = scrape_spotify_leads(keywords=keyword_list, max_emails=max_emails)
    click.echo(f'Got {len(leads)} leads with emails. Checking YouTube gaps...\n')

    # Write header immediately so the file exists even if we stop early
    write_csv([], output)

    for i, lead in enumerate(leads, 1):
        name = lead['podcast_name']
        email = lead['email']
        click.echo(f'[{i}/{len(leads)}] {name}', nl=False)

        try:
            channel = _retry_find_channel(youtube, name)
            checked += 1

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

            prospect = {
                'podcast_name': name,
                'host_email': email,
                'youtube_channel_url': channel['channel_url'],
                'yt_videos_90d': gap['yt_videos_90d'],
                'yt_shorts_90d': gap['yt_shorts_90d'],
                'gap_score': round(score, 2),
                'keyword': lead['keyword'],
                'spotify_url': lead['spotify_url'],
            }
            prospects.append(prospect)
            append_csv(prospect, output)  # write immediately — don't lose progress
            click.echo(f' — gap score {score:.1f} ✓')

        except QuotaExhausted:
            click.echo(f'\n\nYouTube daily quota exhausted after {checked} checks.')
            click.echo(f'{len(prospects)} prospects saved to {output}. Run again tomorrow for the rest.')
            return

        except Exception as exc:
            click.echo(f' — error ({type(exc).__name__}: {exc}), skipping')

        finally:
            time.sleep(3)  # ~20 req/min — under YouTube's per-minute search limit

    click.echo(f'\n{len(prospects)} qualified prospects found.')
    click.echo(f'Wrote to {output}')


if __name__ == '__main__':
    main()
