import click
from googleapiclient.discovery import build

from config import LISTEN_NOTES_API_KEY, YOUTUBE_API_KEY
from stages.discover import search_podcasts
from stages.extract_email import extract_email
from stages.youtube import find_channel, get_shorts_gap
from utils import calculate_gap_score
from writer import write_csv


@click.command()
@click.option('--categories', default='business,entrepreneurship', show_default=True,
              help='Comma-separated category slugs: business, entrepreneurship, self-improvement, marketing, investing, health, coaching')
@click.option('--limit', default=100, show_default=True,
              help='Max podcasts to discover')
@click.option('--output', default='prospects.csv', show_default=True,
              help='Output CSV path')
def main(categories: str, limit: int, output: str):
    category_list = [c.strip() for c in categories.split(',')]
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    prospects = []

    click.echo(f'Discovering up to {limit} podcasts in: {", ".join(category_list)}')
    podcasts = search_podcasts(categories=category_list, limit=limit, api_key=LISTEN_NOTES_API_KEY)
    click.echo(f'Found {len(podcasts)} podcasts. Processing...\n')

    for i, podcast in enumerate(podcasts, 1):
        name = podcast['podcast_name']
        click.echo(f'[{i}/{len(podcasts)}] {name}', nl=False)

        email = extract_email(podcast['rss_url'])
        if not email:
            click.echo(' — no email, skipping')
            continue

        channel = find_channel(youtube, podcast_name=name, podcast_website=podcast['website'])
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
            episodes=podcast['episode_count'],
        )

        prospects.append({
            'podcast_name': name,
            'host_email': email,
            'youtube_channel_url': channel['channel_url'],
            'yt_videos_90d': gap['yt_videos_90d'],
            'yt_shorts_90d': gap['yt_shorts_90d'],
            'gap_score': round(score, 2),
            'category': podcast['category'],
            'episode_count': podcast['episode_count'],
        })
        click.echo(f' — gap score {score:.1f} ✓')

    prospects.sort(key=lambda p: p['gap_score'], reverse=True)
    click.echo(f'\n{len(prospects)} qualified prospects found.')
    write_csv(prospects, output)


if __name__ == '__main__':
    main()
