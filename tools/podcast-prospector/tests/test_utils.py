import pytest
from utils import parse_duration_seconds, is_short, calculate_gap_score, extract_domain


class TestParseDurationSeconds:
    def test_parse_hours_only(self):
        assert parse_duration_seconds('PT2H') == 7200

    def test_parse_minutes_only(self):
        assert parse_duration_seconds('PT30M') == 1800

    def test_parse_seconds_only(self):
        assert parse_duration_seconds('PT45S') == 45

    def test_parse_hours_minutes_seconds(self):
        assert parse_duration_seconds('PT1H30M45S') == 5445

    def test_parse_zero_duration(self):
        assert parse_duration_seconds('PT0S') == 0

    def test_parse_invalid_format_returns_zero(self):
        assert parse_duration_seconds('INVALID') == 0

    def test_parse_empty_string_returns_zero(self):
        assert parse_duration_seconds('') == 0

    def test_parse_invalid_string_returns_zero(self):
        assert parse_duration_seconds('PT5M_GARBAGE') == 0


class TestIsShort:
    def test_duration_under_60_seconds_is_short(self):
        assert is_short(30, 'random title') is True

    def test_duration_exactly_60_seconds_is_short(self):
        assert is_short(60, 'random title') is True

    def test_duration_over_60_without_hashtag_is_not_short(self):
        assert is_short(120, 'random title') is False

    def test_duration_over_60_with_shorts_hashtag_is_short(self):
        assert is_short(120, 'Check this out #shorts') is True

    def test_duration_over_60_with_shorts_hashtag_mixed_case_is_short(self):
        assert is_short(120, 'Check this out #SHORTS') is True

    def test_duration_zero_is_short(self):
        assert is_short(0, 'random title') is True


class TestCalculateGapScore:
    def test_high_ratio_low_maturity(self):
        result = calculate_gap_score(videos=10, shorts=1, episodes=5)
        assert result == 5.0

    def test_low_ratio_high_maturity(self):
        result = calculate_gap_score(videos=10, shorts=10, episodes=200)
        assert result == 1.0

    def test_zero_shorts_defaults_to_one(self):
        result = calculate_gap_score(videos=5, shorts=0, episodes=5)
        assert result == 5.0

    def test_low_episodes_reduces_score(self):
        result = calculate_gap_score(videos=10, shorts=2, episodes=1)
        assert result == 0.5

    def test_max_maturity_at_100_episodes(self):
        result = calculate_gap_score(videos=10, shorts=2, episodes=100)
        assert result == 5.0


class TestExtractDomain:
    def test_extract_domain_from_url(self):
        assert extract_domain('https://www.example.com') == 'example.com'

    def test_extract_domain_removes_www(self):
        assert extract_domain('https://www.github.com/user/repo') == 'github.com'

    def test_extract_domain_without_www(self):
        assert extract_domain('https://github.com/user/repo') == 'github.com'

    def test_extract_domain_none_input(self):
        assert extract_domain(None) is None

    def test_extract_domain_empty_string(self):
        assert extract_domain('') is None

    def test_extract_domain_invalid_url(self):
        assert extract_domain('not a url') is None

    def test_extract_domain_with_port(self):
        assert extract_domain('https://localhost:8080') == 'localhost'
