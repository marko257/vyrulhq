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
