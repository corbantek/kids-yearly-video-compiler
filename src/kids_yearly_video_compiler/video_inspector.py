from datetime import date
from dataclasses import dataclass
import os
import re
from typing import List
import ffmpeg


@dataclass
class VideoInfo:
    date_taken: date = date.today()
    base_name: str = ""
    file_path: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    probe_info: dict = None
    hdr: bool = False

    def get_since_birthday(self, birthday: date) -> str:
        days = self.date_taken - birthday
        week = days.days // 7
        if week < 52:
            if week == 0:
                return f"Day {days.days}"
            return f"Week {week}"
        year = week // 52
        week = week % 52
        if week == 0:
            return f"Year {year}"
        else:
            return f"Year {year} / Week {week}"


def get_all_video_info(path: str) -> List[VideoInfo]:
    video_file_names = [
        video_file_name
        for video_file_name in os.listdir(path)
        if os.path.isfile(path + "/" + video_file_name)
        and not video_file_name.startswith(".")
    ]
    return [
        get_video_info(path, video_file_name) for video_file_name in video_file_names
    ]


def get_video_info(path: str, video_file_name: str, base_name: str = None) -> VideoInfo:
    video_file_path = os.path.join(path, video_file_name)
    try:
        probe = ffmpeg.probe(video_file_path)
    except ffmpeg.Error as e:
        print(f"error probing {video_file_name}: {e}")
        print(f"ffprobe error: {e.stderr.decode('utf-8')}")
        exit(1)

    video = next(
        (stream for stream in probe["streams"] if stream["codec_type"] == "video"), None
    )
    video_date = date.today()
    regex = re.match(r".*?PXL_(\d\d\d\d)(\d\d)(\d\d).*", video_file_name)
    if regex:
        video_date = date.fromisoformat(
            f"{regex.group(1)}-{regex.group(2)}-{regex.group(3)}"
        )
    if not video:
        return VideoInfo()
    return VideoInfo(
        date_taken=video_date,
        base_name=base_name or video_file_name.split(".")[0],
        file_path=video_file_path,
        duration=float(video["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        hdr=video["color_primaries"] == "bt2020",  # "bt709" is for normal videos
        probe_info=video,
    )
