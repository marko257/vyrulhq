# Podcast Outreach Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI script that discovers podcasters with YouTube video content but no Shorts, extracts their contact email from RSS, and writes a ranked prospect CSV ready for GMass cold outreach.

**Architecture:** Five sequential stages run as a single Python script — Listen Notes discovery → RSS email extraction → YouTube channel match → Shorts gap check → CSV output. Pure functions are extracted to `utils.py` and tested independently. Each stage is a focused module in `stages/`.

**Tech Stack:** Python 3.11+, Click (CLI), requests (HTTP), google-api-python-client (YouTube Data API v3), python-dotenv (config), pytest (testing)

---

## File Structure

```
tools/podcast-prospector/
  .env.example           # API key template (committed)
  .env                   # Actual API keys (gitignored)
  config.py              # Loads env vars, exposes constants
  requirements.txt       # Python dependencies
  scrape.py              # CLI entry point — wires all stages
  writer.py              # CSV output
  utils.py               # Pure functions: duration, gap score, domain
  stages/
    __init__.py
    discover.py          # Stage 1: Listen Notes search
    extract_email.py     # Stage 2: RSS email extraction
    youtube.py           # Stages 3+4: YouTube match + Shorts gap check
  tests/
    __init__.py
    test_utils.py
    test_extract_email.py
    test_discover.py
    test_youtube.py
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `tools/podcast-prospector/requirements.txt`
- Create: `tools/podcast-prospector/.env.example`
- Create: `tools/podcast-prospector/config.py`
- Create: `tools/podcast-prospector/stages/__init__.py`
- Create: `tools/podcast-prospector/tests/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p tools/podcast-prospector/stages
mkdir -p tools/podcast-prospector/tests
touch tools/podcast-prospector/stages/__init__.py
touch tools/podcast-prospector/tests/__init__.py
```

- [ ] **Step 2: Create requirements.txt**

Create `tools/podcast-prospector/requirements.txt`:
```
requests==2.31.0
google-api-python-client==2.118.0
python-dotenv==1.0.1
click==8.1.7
pytest==8.1.1
```

- [ ] **Step 3: Create .env.example**

Create `tools/podcast-prospector/.env.example`:
```
LISTEN_NOTES_API_KEY=your_listen_notes_key_here
YOUTUBE_API_KEY=your_youtube_data_api_key_here
```

- [ ] **Step 4: Create config.py**

Create `tools/podcast-prospector/config.py`:
```python
import os
from dotenv import load_dotenv

load_dotenv()

LISTEN_NOTES_API_KEY = os.environ['LISTEN_NOTES_API_KEY']
YOUTUBE_API_KEY = os.environ['YOUTUBE_API_KEY']

LISTEN_NOTES_BASE_URL = 'https://listen-api.listennotes.com/api/v2'
YOUTUBE_SHORTS_MAX_SECONDS = 60
LOOKBACK_DAYS = 90
MIN_EPISODES = 50
```

- [ ] **Step 5: Update .gitignore**

Add to the root `.gitignore`:
```
tools/podcast-prospector/.env
tools/podcast-prospector/prospects.csv
```

- [ ] **Step 6: Install dependencies**

```bash
cd tools/podcast-prospector && pip install -r requirements.txt
```

Expected: All packages install without errors.

- [ ] **Step 7: Commit**

```bash
git add tools/podcast-prospector/
git commit -m "feat: scaffold podcast-prospector tool"
```

---

### Task 2: Pure Utilities

**Files:**
- Create: `tools/podcast-prospector/utils.py`
- Create: `tools/podcast-prospector/tests/test_utils.py`

- [ ] **Step 1: Write failing tests**

Create `tools/podcast-prospector/tests/test_utils.py`:
```python
import pytest
from utils import parse_duration_seconds, is_short, calculate_gap_score, extract_domain


# --- parse_duration_seconds ---

def test_parse_seconds_only():
    assert parse_duration_seconds('PT45S') == 45

def test_parse_minutes_and_seconds():
    assert parse_duration_seconds('PT1M30S') == 90

def test_parse_hours_minutes_seconds():
    assert parse_duration_seconds('PT1H2M3S') == 3723

def test_parse_minutes_only():
    assert parse_duration_seconds('PT5M') == 300

def test_parse_empty_returns_zero():
    assert parse_duration_seconds('PT') == 0


# --- is_short ---

def test_short_by_duration_under_60():
    assert is_short(duration_seconds=45, title='Normal title') is True

def test_short_at_exactly_60_seconds():
    assert is_short(duration_seconds=60, title='Normal title') is True

def test_not_short_at_61_seconds():
    assert is_short(duration_seconds=61, title='Normal title') is False

def test_short_by_hashtag_regardless_of_duration():
    assert is_short(duration_seconds=300, title='My video #Shorts') is True

def test_short_by_lowercase_hashtag():
    assert is_short(duration_seconds=300, title='My video #shorts') is True

def test_not_short_long_video_no_hashtag():
    assert is_short(duration_seconds=3600, title='Full podcast episode') is False


# --- calculate_gap_score ---

def test_high_videos_zero_shorts_gives_max():
    assert calculate_gap_score(videos=10, shorts=0, episodes=100) == 10.0

def test_equal_videos_and_shorts_gives_one():
    assert calculate_gap_score(videos=10, shorts=10, episodes=100) == 1.0

def test_low_episode_count_dampens_score():
    assert calculate_gap_score(videos=10, shorts=0, episodes=5) == pytest.approx(5.0)

def test_zero_videos_gives_zero():
    assert calculate_gap_score(videos=0, shorts=0, episodes=100) == 0.0

def test_episode_count_caps_multiplier_at_one():
    score_100 = calculate_gap_score(videos=10, shorts=0, episodes=100)
    score_200 = calculate_gap_score(videos=10, shorts=0, episodes=200)
    assert score_100 == score_200


# --- extract_domain ---

def test_extract_domain_simple():
    assert extract_domain('https://mypodcast.com') == 'mypodcast.com'

def test_extract_domain_strips_www():
    assert extract_domain('https://www.mypodcast.com') == 'mypodcast.com'

def test_extract_domain_strips_path():
    assert extract_domain('https://mypodcast.com/episodes/123') == 'mypodcast.com'

def test_extract_domain_none_input():
    assert extract_domain(None) is None

def test_extract_domain_empty_string():
    assert extract_domain('') is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd tools/podcast-prospector && python -m pytest tests/test_utils.py -v
```

Expected: `ModuleNotFoundError: No module named 'utils'`

- [ ] **Step 3: Implement utils.py**

Create `tools/podcast-prospector/utils.py`:
```python
import re
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


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        return hostname.removeprefix('www.') or None
    except Exception:
        return None
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd tools/podcast-prospector && python -m pytest tests/test_utils.py -v
```

Expected: All 20 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/podcast-prospector/utils.py tools/podcast-prospector/tests/test_utils.py
git commit -m "feat: add pure utilities with tests (duration, gap score, domain)"
```

---

### Task 3: Email Extractor

**Files:**
- Create: `tools/podcast-prospector/stages/extract_email.py`
- Create: `tools/podcast-prospector/tests/test_extract_email.py`

- [ ] **Step 1: Write failing tests**

Create `tools/podcast-prospector/tests/test_extract_email.py`:
```python
from unittest.mock import patch, Mock
from stages.extract_email import extract_email

RSS_WITH_ITUNES_EMAIL = '''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>My Podcast</title>
    <itunes:email>host@example.com</itunes:email>
  </channel>
</rss>'''

RSS_WITH_MANAGING_EDITOR = '''<?xml version="1.0" encoding="UTF-8"?>
<rss>
  <channel>
    <title>My Podcast</title>
    <managingEditor>editor@example.com (Editor Name)</managingEditor>
  </channel>
</rss>'''

RSS_NO_EMAIL = '''<?xml version="1.0" encoding="UTF-8"?>
<rss>
  <channel>
    <title>My Podcast</title>
  </channel>
</rss>'''


def make_response(text, status=200):
    m = Mock()
    m.text = text
    m.status_code = status
    m.raise_for_status = Mock()
    return m


def test_extracts_itunes_email():
    with patch('requests.get', return_value=make_response(RSS_WITH_ITUNES_EMAIL)):
        assert extract_email('http://fake.rss/feed') == 'host@example.com'


def test_falls_back_to_managing_editor():
    with patch('requests.get', return_value=make_response(RSS_WITH_MANAGING_EDITOR)):
        assert extract_email('http://fake.rss/feed') == 'editor@example.com'


def test_returns_none_when_no_email():
    with patch('requests.get', return_value=make_response(RSS_NO_EMAIL)):
        assert extract_email('http://fake.rss/feed') is None


def test_returns_none_on_network_error():
    with patch('requests.get', side_effect=Exception('Connection refused')):
        assert extract_email('http://fake.rss/feed') is None


def test_itunes_email_takes_priority():
    rss = RSS_WITH_ITUNES_EMAIL.replace(
        '</channel>',
        '<managingEditor>other@example.com</managingEditor></channel>'
    )
    with patch('requests.get', return_value=make_response(rss)):
        assert extract_email('http://fake.rss/feed') == 'host@example.com'
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd tools/podcast-prospector && python -m pytest tests/test_extract_email.py -v
```

Expected: `ModuleNotFoundError: No module named 'stages.extract_email'`

- [ ] **Step 3: Implement extract_email.py**

Create `tools/podcast-prospector/stages/extract_email.py`:
```python
import re
import requests
import xml.etree.ElementTree as ET

ITUNES_NS = 'http://www.itunes.com/dtds/podcast-1.0.dtd'


def extract_email(rss_url: str) -> str | None:
    try:
        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        channel = root.find('channel')
        if channel is None:
            return None

        itunes_email = channel.find(f'{{{ITUNES_NS}}}email')
        if itunes_email is not None and itunes_email.text:
            return itunes_email.text.strip()

        managing_editor = channel.find('managingEditor')
        if managing_editor is not None and managing_editor.text:
            match = re.match(r'([^\s(]+)', managing_editor.text.strip())
            return match.group(1) if match else None

        return None
    except Exception:
        return None
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd tools/podcast-prospector && python -m pytest tests/test_extract_email.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/podcast-prospector/stages/extract_email.py tools/podcast-prospector/tests/test_extract_email.py
git commit -m "feat: add RSS email extractor with tests"
```

---

### Task 4: Listen Notes Discovery

**Files:**
- Create: `tools/podcast-prospector/stages/discover.py`
- Create: `tools/podcast-prospector/tests/test_discover.py`

- [ ] **Step 1: Write failing tests**

Create `tools/podcast-prospector/tests/test_discover.py`:
```python
from unittest.mock import patch, Mock
from stages.discover import search_podcasts

MOCK_RESPONSE = {
    'results': [
        {
            'title_original': 'The Business Podcast',
            'rss': 'https://feeds.example.com/business',
            'website': 'https://businesspodcast.com',
            'total_episodes': 120,
            'genre_ids': [93],
            'latest_pub_date_ms': 1716000000000,
        },
        {
            'title_original': 'Tiny Show',
            'rss': 'https://feeds.example.com/tiny',
            'website': 'https://tiny.com',
            'total_episodes': 10,  # below MIN_EPISODES=50, should be filtered
            'genre_ids': [93],
            'latest_pub_date_ms': 1716000000000,
        },
    ],
    'next_offset': None,
}


def mock_get(response_data):
    m = Mock()
    m.json.return_value = response_data
    m.status_code = 200
    m.raise_for_status = Mock()
    return m


def test_filters_out_podcasts_below_episode_threshold():
    with patch('requests.get', return_value=mock_get(MOCK_RESPONSE)):
        results = search_podcasts(categories=['business'], limit=10, api_key='test-key')
    assert len(results) == 1
    assert results[0]['podcast_name'] == 'The Business Podcast'


def test_result_contains_required_fields():
    with patch('requests.get', return_value=mock_get(MOCK_RESPONSE)):
        results = search_podcasts(categories=['business'], limit=10, api_key='test-key')
    r = results[0]
    assert r['podcast_name'] == 'The Business Podcast'
    assert r['rss_url'] == 'https://feeds.example.com/business'
    assert r['website'] == 'https://businesspodcast.com'
    assert r['episode_count'] == 120
    assert r['category'] == 'business'
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd tools/podcast-prospector && python -m pytest tests/test_discover.py -v
```

Expected: `ModuleNotFoundError: No module named 'stages.discover'`

- [ ] **Step 3: Implement discover.py**

Create `tools/podcast-prospector/stages/discover.py`:
```python
import requests
from config import MIN_EPISODES, LISTEN_NOTES_BASE_URL

GENRE_SLUGS = {
    'business': 93,
    'entrepreneurship': 67,
    'self-improvement': 111,
    'marketing': 97,
    'investing': 98,
    'health': 88,
    'coaching': 111,
}


def search_podcasts(categories: list[str], limit: int, api_key: str) -> list[dict]:
    genre_ids = [str(GENRE_SLUGS[c]) for c in categories if c in GENRE_SLUGS]
    results = []
    offset = 0

    while len(results) < limit:
        params = {
            'q': 'podcast',
            'type': 'podcast',
            'language': 'English',
            'offset': offset,
        }
        if genre_ids:
            params['genre_ids'] = ','.join(genre_ids)

        response = requests.get(
            f'{LISTEN_NOTES_BASE_URL}/search',
            headers={'X-ListenAPI-Key': api_key},
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        for item in data.get('results', []):
            if item.get('total_episodes', 0) < MIN_EPISODES:
                continue
            results.append({
                'podcast_name': item.get('title_original', ''),
                'rss_url': item.get('rss', ''),
                'website': item.get('website', ''),
                'episode_count': item.get('total_episodes', 0),
                'category': categories[0] if categories else '',
            })
            if len(results) >= limit:
                break

        if not data.get('next_offset') or not data.get('results'):
            break
        offset = data['next_offset']

    return results[:limit]
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd tools/podcast-prospector && python -m pytest tests/test_discover.py -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/podcast-prospector/stages/discover.py tools/podcast-prospector/tests/test_discover.py
git commit -m "feat: add Listen Notes podcast discovery with tests"
```

---

### Task 5: YouTube Channel Matcher + Shorts Gap Checker

**Files:**
- Create: `tools/podcast-prospector/stages/youtube.py`
- Create: `tools/podcast-prospector/tests/test_youtube.py`

- [ ] **Step 1: Write failing tests**

Create `tools/podcast-prospector/tests/test_youtube.py`:
```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd tools/podcast-prospector && python -m pytest tests/test_youtube.py -v
```

Expected: `ModuleNotFoundError: No module named 'stages.youtube'`

- [ ] **Step 3: Implement stages/youtube.py**

Create `tools/podcast-prospector/stages/youtube.py`:
```python
from datetime import datetime, timezone, timedelta
from utils import parse_duration_seconds, is_short, extract_domain
from config import LOOKBACK_DAYS


def find_channel(youtube, podcast_name: str, podcast_website: str) -> dict | None:
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


def _count_shorts(youtube, video_ids: list[str]) -> dict:
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd tools/podcast-prospector && python -m pytest tests/test_youtube.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd tools/podcast-prospector && python -m pytest -v
```

Expected: All tests across all modules PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/podcast-prospector/stages/youtube.py tools/podcast-prospector/tests/test_youtube.py
git commit -m "feat: add YouTube channel matcher and Shorts gap checker with tests"
```

---

### Task 6: CSV Writer + CLI Orchestrator

**Files:**
- Create: `tools/podcast-prospector/writer.py`
- Create: `tools/podcast-prospector/scrape.py`

- [ ] **Step 1: Create writer.py**

Create `tools/podcast-prospector/writer.py`:
```python
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
```

- [ ] **Step 2: Create scrape.py**

Create `tools/podcast-prospector/scrape.py`:
```python
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
```

- [ ] **Step 3: Set up .env with real API keys**

```bash
cd tools/podcast-prospector && cp .env.example .env
```

Fill in `.env` with real keys:
- **Listen Notes:** Sign up free at listennotes.com → API → copy key
- **YouTube Data API:** Go to console.cloud.google.com → New Project → Enable "YouTube Data API v3" → Credentials → Create API Key → copy

- [ ] **Step 4: Smoke test with small batch**

```bash
cd tools/podcast-prospector && python scrape.py --limit 5 --categories "business"
```

Expected output (approximately):
```
Discovering up to 5 podcasts in: business
Found 5 podcasts. Processing...

[1/5] The Entrepreneur's Journey — gap score 8.3 ✓
[2/5] Startup Stories — no YouTube match, skipping
[3/5] Business Mastery — no email, skipping
[4/5] The Growth Podcast — gap score 4.1 ✓
[5/5] Money Moves — no recent YouTube videos, skipping

2 qualified prospects found.
Wrote 2 prospects to prospects.csv
```

- [ ] **Step 5: Verify CSV structure**

Open `tools/podcast-prospector/prospects.csv`. Confirm:
- Header row has all 8 columns: `podcast_name,host_email,youtube_channel_url,yt_videos_90d,yt_shorts_90d,gap_score,category,episode_count`
- Rows are sorted by `gap_score` descending
- `host_email` values are valid email addresses
- `youtube_channel_url` values are `https://www.youtube.com/channel/UC...` format

- [ ] **Step 6: Commit**

```bash
git add tools/podcast-prospector/writer.py tools/podcast-prospector/scrape.py
git commit -m "feat: add CLI orchestrator and CSV writer — pipeline complete"
```

---

## GMass Import Instructions

Once `prospects.csv` is generated:

1. Upload to Google Sheets (File → Import)
2. Open GMass in Gmail → Connect to sheet
3. Write cold email template:
   - Subject: `{{podcast_name}} — you're sitting on clips.`
   - Body: reference `{{youtube_channel_url}}` and the Shorts gap
4. Set follow-up: 1 follow-up at day 4 if no reply
5. Send to top 20–30 prospects by gap score first — test response rate before full send

Keep a "contacted" sheet and deduplicate before each new batch import.
