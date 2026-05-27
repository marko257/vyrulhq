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
