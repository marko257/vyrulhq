import requests
from config import MIN_EPISODES, LISTEN_NOTES_BASE_URL, MAX_PAGES

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
    pages_fetched = 0

    while len(results) < limit and pages_fetched < MAX_PAGES:
        pages_fetched += 1
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
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(
                f"Listen Notes API error {response.status_code}: {exc}"
            ) from exc
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

        next_off = data.get('next_offset')
        if next_off is None or not data.get('results'):
            break
        if next_off == offset:
            break
        offset = next_off

    return results[:limit]
