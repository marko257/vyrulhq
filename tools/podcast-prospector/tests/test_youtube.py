from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta
from stages.youtube import find_channel, get_shorts_gap


def make_yt(search_items=None, channel_items=None, playlist_items=None, video_items=None):
    yt = MagicMock()
    yt.search.return_value.list.return_value.execute.return_value = {
        'items': search_items or []
    }
    yt.channels.return_value.list.return_value.execute.return_value = {
        'items': channel_items or []
    }
    yt.playlistItems.return_value.list.return_value.execute.return_value = {
        'items': playlist_items or [],
        'nextPageToken': None,
    }
    yt.videos.return_value.list.return_value.execute.return_value = {
        'items': video_items or []
    }
    return yt


def test_find_channel_returns_none_when_no_results():
    yt = make_yt(search_items=[])
    result = find_channel(yt, podcast_name='Test Podcast', podcast_website='https://test.com')
    assert result is None


def test_find_channel_matches_by_domain():
    search_items = [{'id': {'channelId': 'UC123'}, 'snippet': {'title': 'Test Podcast'}}]
    channel_items = [{
        'id': 'UC123',
        'brandingSettings': {'channel': {'website': 'https://test.com/about'}},
        'contentDetails': {'relatedPlaylists': {'uploads': 'UU123'}},
    }]
    yt = make_yt(search_items=search_items, channel_items=channel_items)
    result = find_channel(yt, podcast_name='Test Podcast', podcast_website='https://test.com')
    assert result == {
        'channel_id': 'UC123',
        'channel_url': 'https://www.youtube.com/channel/UC123',
        'uploads_playlist_id': 'UU123',
    }


def test_find_channel_returns_none_on_domain_mismatch():
    search_items = [{'id': {'channelId': 'UC999'}, 'snippet': {'title': 'Unrelated'}}]
    channel_items = [{
        'id': 'UC999',
        'brandingSettings': {'channel': {'website': 'https://unrelated.com'}},
        'contentDetails': {'relatedPlaylists': {'uploads': 'UU999'}},
    }]
    yt = make_yt(search_items=search_items, channel_items=channel_items)
    result = find_channel(yt, podcast_name='Test Podcast', podcast_website='https://test.com')
    assert result is None


def test_get_shorts_gap_counts_videos_and_shorts():
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    playlist_items = [
        {'contentDetails': {'videoId': 'v1', 'videoPublishedAt': recent}},
        {'contentDetails': {'videoId': 'v2', 'videoPublishedAt': recent}},
    ]
    video_items = [
        {'id': 'v1', 'contentDetails': {'duration': 'PT45S'}, 'snippet': {'title': 'Short clip'}},
        {'id': 'v2', 'contentDetails': {'duration': 'PT30M'}, 'snippet': {'title': 'Full episode'}},
    ]
    yt = make_yt(playlist_items=playlist_items, video_items=video_items)
    gap = get_shorts_gap(yt, uploads_playlist_id='UU123')
    assert gap['yt_videos_90d'] == 2
    assert gap['yt_shorts_90d'] == 1


def test_get_shorts_gap_excludes_videos_older_than_90_days():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=100)).strftime('%Y-%m-%dT%H:%M:%SZ')
    playlist_items = [
        {'contentDetails': {'videoId': 'v1', 'videoPublishedAt': old}},
    ]
    yt = make_yt(playlist_items=playlist_items, video_items=[])
    gap = get_shorts_gap(yt, uploads_playlist_id='UU123')
    assert gap['yt_videos_90d'] == 0
    assert gap['yt_shorts_90d'] == 0


def test_get_shorts_gap_returns_zeros_for_empty_channel():
    yt = make_yt(playlist_items=[], video_items=[])
    gap = get_shorts_gap(yt, uploads_playlist_id='UU123')
    assert gap == {'yt_videos_90d': 0, 'yt_shorts_90d': 0}
