"""Tests for video information handling."""

from datetime import date
import pytest
from kids_yearly_video_compiler.yearly_video_generator import VideoInfo, get_timelapse_text

def test_video_info_default_values():
    """Test VideoInfo default values."""
    video = VideoInfo()
    assert video.date_taken == date.today()
    assert video.base_name == ""
    assert video.file_path == ""
    assert video.duration == 0.0
    assert video.width == 0
    assert video.height == 0
    assert video.hdr is False
    assert video.probe_info is None

def test_video_info_custom_values():
    """Test VideoInfo with custom values."""
    test_date = date(2023, 1, 1)
    video = VideoInfo(
        date_taken=test_date,
        base_name="test_video.mp4",
        file_path="/path/to/test_video.mp4",
        duration=60.0,
        width=1920,
        height=1080,
        hdr=True,
        probe_info={"test": "info"}
    )
    assert video.date_taken == test_date
    assert video.base_name == "test_video.mp4"
    assert video.file_path == "/path/to/test_video.mp4"
    assert video.duration == 60.0
    assert video.width == 1920
    assert video.height == 1080
    assert video.hdr is True
    assert video.probe_info == {"test": "info"}

def test_get_timelapse_text():
    """Test timelapse text generation."""
    # Test day 0
    video = VideoInfo(date_taken=date(2023, 3, 23))  # Birthday
    assert get_timelapse_text(video) == "Day 0"

    # Test week 1
    video = VideoInfo(date_taken=date(2023, 3, 30))  # 1 week after birthday
    assert get_timelapse_text(video) == "Week 1"

    # Test year 1
    video = VideoInfo(date_taken=date(2024, 3, 23))  # 1 year after birthday
    assert get_timelapse_text(video) == "Year 1"

    # Test year 1 week 1
    video = VideoInfo(date_taken=date(2024, 3, 30))  # 1 year 1 week after birthday
    assert get_timelapse_text(video) == "Year 1 / Week 1"
