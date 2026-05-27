from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
from utils import parse_duration_seconds, is_short, extract_domain
from config import LOOKBACK_DAYS


def find_channel(youtube, podcast_name: str, podcast_website: str) -> Optional[dict]:
    podcast_domain = extract_domain(podcast_website)

    search_result = youtube.search().list(
        q=f'{podcast_name} podcast',
        type='channel',
        part='snippet',
        maxResults=3,
    ).execute()

    for item in search_result.get('items', []):
        channel_id = item['id']['channelId']

        channel_result = youtube.channels().list(
            id=channel_id,
            part='brandingSettings,contentDetails',
        ).execute()

        if not channel_result.get('items'):
            continue

        channel = channel_result['items'][0]
        channel_website = (
            channel.get('brandingSettings', {})
            .get('channel', {})
            .get('website', '')
        )
        channel_domain = extract_domain(channel_website)

        if podcast_domain and channel_domain and podcast_domain == channel_domain:
            uploads_playlist_id = (
                channel['contentDetails']['relatedPlaylists']['uploads']
            )
            return {
                'channel_id': channel_id,
                'channel_url': f'https://www.youtube.com/channel/{channel_id}',
                'uploads_playlist_id': uploads_playlist_id,
            }

    return None


def get_shorts_gap(youtube, uploads_playlist_id: str) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    recent_video_ids = []
    next_page_token = None

    while True:
        kwargs = {
            'playlistId': uploads_playlist_id,
            'part': 'contentDetails',
            'maxResults': 50,
        }
        if next_page_token:
            kwargs['pageToken'] = next_page_token

        playlist_result = youtube.playlistItems().list(**kwargs).execute()

        for item in playlist_result.get('items', []):
            published_str = item['contentDetails'].get('videoPublishedAt', '')
            if not published_str:
                continue
            published = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
            if published < cutoff:
                return _count_shorts(youtube, recent_video_ids)
            recent_video_ids.append(item['contentDetails']['videoId'])

        next_page_token = playlist_result.get('nextPageToken')
        if not next_page_token:
            break

    return _count_shorts(youtube, recent_video_ids)


def _count_shorts(youtube, video_ids: list) -> dict:
    if not video_ids:
        return {'yt_videos_90d': 0, 'yt_shorts_90d': 0}

    shorts_count = 0
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        details = youtube.videos().list(
            id=','.join(batch),
            part='contentDetails,snippet',
        ).execute()
        for video in details.get('items', []):
            duration = parse_duration_seconds(video['contentDetails']['duration'])
            title = video['snippet']['title']
            if is_short(duration_seconds=duration, title=title):
                shorts_count += 1

    return {
        'yt_videos_90d': len(video_ids),
        'yt_shorts_90d': shorts_count,
    }
