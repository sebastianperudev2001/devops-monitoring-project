from api_gateway import RateLimiter


def test_allows_requests_under_the_limit():
    limiter = RateLimiter(limit=3, window_seconds=10)

    first = limiter.is_allowed("1.2.3.4", now=0)
    second = limiter.is_allowed("1.2.3.4", now=1)
    third = limiter.is_allowed("1.2.3.4", now=2)

    assert first is True
    assert second is True
    assert third is True


def test_rejects_requests_over_the_limit_within_window():
    limiter = RateLimiter(limit=2, window_seconds=10)

    first = limiter.is_allowed("1.2.3.4", now=0)
    second = limiter.is_allowed("1.2.3.4", now=1)
    third = limiter.is_allowed("1.2.3.4", now=2)

    assert first is True
    assert second is True
    assert third is False


def test_allows_again_after_window_expires():
    limiter = RateLimiter(limit=1, window_seconds=10)

    within_limit = limiter.is_allowed("1.2.3.4", now=0)
    still_in_window = limiter.is_allowed("1.2.3.4", now=5)
    new_window = limiter.is_allowed("1.2.3.4", now=11)

    assert within_limit is True
    assert still_in_window is False
    assert new_window is True


def test_tracks_separate_clients_independently():
    limiter = RateLimiter(limit=1, window_seconds=10)

    first_client = limiter.is_allowed("1.1.1.1", now=0)
    second_client = limiter.is_allowed("2.2.2.2", now=0)

    assert first_client is True
    assert second_client is True
