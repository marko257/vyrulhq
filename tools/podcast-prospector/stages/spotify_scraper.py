import time

import requests
from config import APIFY_API_KEY, APIFY_ACTOR_ID

APIFY_BASE = 'https://api.apify.com/v2'


def scrape_spotify_leads(keywords: list[str], max_emails: int) -> list[dict]:
    """
    Runs the Spotify Email Scraper actor on Apify and returns deduplicated leads.
    Each lead: {podcast_name, email, spotify_url, keyword}
    """
    run_id = _start_run(keywords, max_emails)
    dataset_id = _wait_for_run(run_id)
    items = _fetch_items(dataset_id)
    return _deduplicate(items)


def _start_run(keywords: list[str], max_emails: int) -> str:
    payload = {
        'keywords': keywords,
        'location': '',
        'customDomains': [
            '@gmail.com', '@yahoo.com', '@outlook.com', '@hotmail.com',
            '@icloud.com', '@me.com', '@protonmail.com', '@hey.com',
            # custom domains — actor matches any string so use a short suffix
            '.com', '.co', '.io', '.fm', '.net', '.org',
        ],
        'maxEmails': max_emails,
    }
    resp = requests.post(
        f'{APIFY_BASE}/acts/{APIFY_ACTOR_ID}/runs',
        params={'token': APIFY_API_KEY},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['data']['id']


def _wait_for_run(run_id: str, poll_interval: int = 5, timeout: int = 300) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(
            f'{APIFY_BASE}/actor-runs/{run_id}',
            params={'token': APIFY_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        run = resp.json()['data']
        status = run['status']
        if status == 'SUCCEEDED':
            return run['defaultDatasetId']
        if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
            raise RuntimeError(f'Apify run {run_id} ended with status: {status}')
        time.sleep(poll_interval)
    raise RuntimeError(f'Apify run {run_id} did not finish within {timeout}s')


def _fetch_items(dataset_id: str) -> list[dict]:
    resp = requests.get(
        f'{APIFY_BASE}/datasets/{dataset_id}/items',
        params={'token': APIFY_API_KEY, 'clean': 'true'},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _deduplicate(items: list[dict]) -> list[dict]:
    seen_emails = set()
    seen_names = set()
    results = []
    for item in items:
        url = item.get('url', '')
        # Skip individual episode URLs — we want podcast show pages only
        if '/episode/' in url:
            continue

        email = (item.get('email') or '').strip().lower()
        if not email or email in seen_emails:
            continue

        name = item.get('title', '').strip()
        # Strip Spotify-appended suffixes that break YouTube matching
        for suffix in (' | Podcast on Spotify', ' • A podcast on Spotify', ' - Podcast on Spotify'):
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
                break

        name_key = name.lower()
        if name_key in seen_names:
            continue

        seen_emails.add(email)
        seen_names.add(name_key)
        results.append({
            'podcast_name': name,
            'email': email,
            'spotify_url': url,
            'keyword': item.get('keyword', ''),
        })
    return results
