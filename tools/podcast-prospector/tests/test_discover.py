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
