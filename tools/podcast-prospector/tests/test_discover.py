from unittest.mock import patch, Mock
from stages.discover import search_podcasts

MOCK_ITUNES_RESPONSE = {
    'resultCount': 2,
    'results': [
        {
            'collectionId': 123456,
            'collectionName': 'The Business Podcast',
            'feedUrl': 'https://feeds.example.com/business',
            'trackCount': 120,
            'primaryGenreName': 'Business',
        },
        {
            'collectionId': 789012,
            'collectionName': 'Tiny Show',
            'feedUrl': 'https://feeds.example.com/tiny',
            'trackCount': 10,  # below MIN_EPISODES=50, should be filtered
            'primaryGenreName': 'Business',
        },
    ],
}


def mock_get(response_data):
    m = Mock()
    m.json.return_value = response_data
    m.status_code = 200
    m.raise_for_status = Mock()
    return m


def test_filters_out_podcasts_below_episode_threshold():
    with patch('requests.get', return_value=mock_get(MOCK_ITUNES_RESPONSE)):
        results = search_podcasts(categories=['business'], limit=10)
    assert len(results) == 1
    assert results[0]['podcast_name'] == 'The Business Podcast'


def test_result_contains_required_fields():
    with patch('requests.get', return_value=mock_get(MOCK_ITUNES_RESPONSE)):
        results = search_podcasts(categories=['business'], limit=10)
    r = results[0]
    assert r['podcast_name'] == 'The Business Podcast'
    assert r['rss_url'] == 'https://feeds.example.com/business'
    assert r['episode_count'] == 120
    assert r['category'] == 'business'


def test_skips_items_with_no_feed_url():
    response = {
        'resultCount': 1,
        'results': [{'collectionId': 1, 'collectionName': 'No Feed', 'feedUrl': '', 'trackCount': 100}],
    }
    with patch('requests.get', return_value=mock_get(response)):
        results = search_podcasts(categories=['business'], limit=10)
    assert len(results) == 0


def test_deduplicates_across_categories():
    with patch('requests.get', return_value=mock_get(MOCK_ITUNES_RESPONSE)):
        results = search_podcasts(categories=['business', 'entrepreneurship'], limit=10)
    names = [r['podcast_name'] for r in results]
    assert len(names) == len(set(names))
