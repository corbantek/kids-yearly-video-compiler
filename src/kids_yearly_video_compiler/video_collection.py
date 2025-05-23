import sys
from typing import Sequence

from kids_yearly_video_compiler.video_inspector import VideoInfo

class VideoCollection:
    def __init__(self, videos: Sequence[VideoInfo]):
        self.videos = videos
        self.min_width, self.max_width = sys.maxsize, 0
        self.min_height, self.max_height = sys.maxsize, 0
        self.total_duration = 0
        for video in videos:
            self.total_duration += video.duration
            self.min_width, self.max_width = min(self.min_width, video.width), max(
                self.max_width, video.width
            )
            self.min_height, self.max_height = min(self.min_height, video.height), max(
                self.max_height, video.height
            )
        self.average_duration = (self.total_duration / self.size())

    def size(self) -> int:
        return len(self.videos)

    def sorted(self, reverse: bool = False) -> Sequence[VideoInfo]:
        return sorted(self.videos, key=lambda x: x.base_name, reverse=reverse)

    def print_info(self) -> None:
        print(f"video collection info:")
        print(f"\tnumber of videos: {self.size()}")
        print(f"\ttotal duration: {self.total_duration/60} minutes")
        print(f"\taverage duration: {self.average_duration} seconds")
        print(f"\tmin width/height: {self.min_width} / {self.min_height}")
        print(f"\tmax width/height: {self.max_width} / {self.max_height}")
