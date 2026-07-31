from app.services.normalizer import choose_video_variant


def test_choose_video_variant_prefers_best_h264_under_1080p() -> None:
    result = choose_video_variant(
        [
            {"url": "low", "container": "mp4", "codec": "h264", "height": 360, "bitrate": 500},
            {"url": "best", "container": "mp4", "codec": "h264", "height": 1080, "bitrate": 3000},
            {"url": "too-high", "container": "mp4", "codec": "h264", "height": 2160, "bitrate": 9000},
            {"url": "vp9", "container": "webm", "codec": "vp9", "height": 1080, "bitrate": 4000},
        ]
    )
    assert result is not None
    assert result["url"] == "best"
