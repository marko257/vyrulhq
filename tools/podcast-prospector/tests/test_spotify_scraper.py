from unittest.mock import patch, Mock
from stages.spotify_scraper import scrape_spotify_leads, _deduplicate


def make_response(data, status=200):
    m = Mock()
    m.status_code = status
    m.json.return_value = data
    m.raise_for_status = Mock()
    return m


MOCK_ITEMS = [
    {'title': 'Podcast A', 'email': 'host@podcasta.com', 'url': 'https://open.spotify.com/show/1', 'keyword': 'coaching'},
    {'title': 'Podcast B', 'email': 'hello@podcastb.com', 'url': 'https://open.spotify.com/show/2', 'keyword': 'coaching'},
    {'title': 'Podcast A Dupe', 'email': 'host@podcasta.com', 'url': 'https://open.spotify.com/show/3', 'keyword': 'marketing'},
    {'title': 'No Email', 'email': '', 'url': 'https://open.spotify.com/show/4', 'keyword': 'coaching'},
]


def test_deduplicates_by_email():
    results = _deduplicate(MOCK_ITEMS)
    emails = [r['email'] for r in results]
    assert len(emails) == len(set(emails))


def test_skips_empty_emails():
    results = _deduplicate(MOCK_ITEMS)
    assert all(r['email'] for r in results)


def test_returns_expected_fields():
    results = _deduplicate(MOCK_ITEMS[:1])
    r = results[0]
    assert 'podcast_name' in r
    assert 'email' in r
    assert 'spotify_url' in r
    assert 'keyword' in r


def test_scrape_spotify_leads_full_flow():
    run_data = {'data': {'id': 'run123'}}
    status_data = {'data': {'status': 'SUCCEEDED', 'defaultDatasetId': 'ds456'}}
    items_data = [
        {'title': 'Test Pod', 'email': 'test@pod.com', 'url': 'https://open.spotify.com/show/x', 'keyword': 'coaching'},
    ]

    responses = [
        make_response(run_data),
        make_response(status_data),
        make_response(items_data),
    ]

    with patch('requests.post', return_value=responses[0]), \
         patch('requests.get', side_effect=responses[1:]):
        results = scrape_spotify_leads(keywords=['coaching'], max_emails=10)

    assert len(results) == 1
    assert results[0]['email'] == 'test@pod.com'
    assert results[0]['podcast_name'] == 'Test Pod'
