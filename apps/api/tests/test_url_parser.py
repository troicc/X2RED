import pytest

from app.services.url_parser import extract_x_post_id


def test_extracts_supported_urls() -> None:
    assert extract_x_post_id("https://x.com/a/status/123456") == "123456"
    assert extract_x_post_id("https://twitter.com/a/status/123456/") == "123456"
    assert extract_x_post_id("https://fixupx.com/a/status/123456") == "123456"


def test_rejects_unknown_host() -> None:
    with pytest.raises(ValueError):
        extract_x_post_id("https://example.com/a/status/123456")
