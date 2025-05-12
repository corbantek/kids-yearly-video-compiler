"""Tests for video aggregation functionality."""

import pytest
from kids_yearly_video_compiler.yearly_video_generator import (
    VideoInfo,
    VideoAggregation,
    get_video_aggregation_info,
    output_video_aggregation_info
)

def test_video_aggregation_default_values():
    """Test VideoAggregation default values."""
    agg = VideoAggregation()
    assert agg.n_videos == 0
    assert agg.average_duration == 0.0
    assert agg.total_duration == 0.0
    assert agg.min_width == 0
    assert agg.max_width == 0
    assert agg.min_height == 0
    assert agg.max_height == 0

def test_get_video_aggregation_info():
    """Test video aggregation info calculation."""
    videos = [
        VideoInfo(duration=60.0, width=1920, height=1080),
        VideoInfo(duration=30.0, width=1280, height=720),
        VideoInfo(duration=45.0, width=3840, height=2160)
    ]

    agg = get_video_aggregation_info(videos)

    assert agg.n_videos == 3
    assert agg.total_duration == 135.0
    assert agg.average_duration == 45.0
    assert agg.min_width == 1280
    assert agg.max_width == 3840
    assert agg.min_height == 720
    assert agg.max_height == 2160

def test_output_video_aggregation_info(capsys):
    """Test video aggregation info output."""
    agg = VideoAggregation(
        n_videos=2,
        total_duration=120.0,
        average_duration=60.0,
        min_width=1280,
        max_width=1920,
        min_height=720,
        max_height=1080
    )

    output_video_aggregation_info(agg)
    captured = capsys.readouterr()

    assert "number of videos: 2" in captured.out
    assert "total duration: 2.0 minutes" in captured.out
    assert "average duration: 60.0 seconds" in captured.out
    assert "min width/height: 1280 / 720" in captured.out
    assert "max width/height: 1920 / 1080" in captured.out
