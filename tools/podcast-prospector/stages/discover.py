import requests
from config import MIN_EPISODES

ITUNES_SEARCH_URL = 'https://itunes.apple.com/search'

# Maps category slug to (search_term, apple_genre_id)
CATEGORY_MAP = {
    'business':         ('business', 1321),
    'entrepreneurship': ('entrepreneurship', 1321),
    'self-improvement': ('self improvement', 1410),
    'marketing':        ('marketing', 1321),
    'investing':        ('investing', 1321),
    'health':           ('health', 1512),
    'coaching':         ('coaching', 1321),
}


def search_podcasts(categories: list[str], limit: int) -> list[dict]:
    results = []
    seen_ids = set()

    for category in categories:
        if len(results) >= limit:
            break

        term, genre_id = CATEGORY_MAP.get(category, (category, None))
        params = {
            'term': term,
            'entity': 'podcast',
            'limit': min(200, limit - len(results) + 50),  # fetch extra to account for filtering
        }
        if genre_id:
            params['genreId'] = genre_id

        try:
            response = requests.get(ITUNES_SEARCH_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"iTunes Search API error: {exc}") from exc

        for item in data.get('results', []):
            collection_id = item.get('collectionId')
            if not collection_id or collection_id in seen_ids:
                continue
            if item.get('trackCount', 0) < MIN_EPISODES:
                continue
            feed_url = item.get('feedUrl', '')
            if not feed_url:
                continue

            seen_ids.add(collection_id)
            results.append({
                'podcast_name': item.get('collectionName', ''),
                'rss_url': feed_url,
                'website': '',  # iTunes doesn't expose podcast website URL
                'episode_count': item.get('trackCount', 0),
                'category': category,
            })

            if len(results) >= limit:
                break

    return results[:limit]
