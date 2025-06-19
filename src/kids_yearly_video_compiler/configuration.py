import os
from dataclasses import dataclass, field
from datetime import date
from typing import Tuple, Any
import yaml

@dataclass
class KidInfo:
    name: str = "Jane Doe"
    birthday: date = date.fromisoformat("2023-03-23")

@dataclass
class Directories:
    input_videos: str = "./functional_tests/input/"
    output_video: str = "./functional_tests/output/"
    scratch: str = "./functional_tests/scratch/"

@dataclass
class TimelapseVideo:
    length: str = "15s"
    max_width: int = 1920
    max_height: int = 1080
    instagram_style: bool = True

    def get_length_in_seconds(self) -> float:
        """Parse time string (e.g., '5m', '15s', '1h30m') into seconds."""
        import re

        # Handle simple cases like "15" (assume seconds)
        if self.length.isdigit():
            return float(self.length)

        # Parse time units
        total_seconds = 0.0

        # Find hours
        hours_match = re.search(r'(\d+(?:\.\d+)?)h', self.length.lower())
        if hours_match:
            total_seconds += float(hours_match.group(1)) * 3600

        # Find minutes
        minutes_match = re.search(r'(\d+(?:\.\d+)?)m', self.length.lower())
        if minutes_match:
            total_seconds += float(minutes_match.group(1)) * 60

        # Find seconds
        seconds_match = re.search(r'(\d+(?:\.\d+)?)s', self.length.lower())
        if seconds_match:
            total_seconds += float(seconds_match.group(1))

        # If no units found, treat as seconds
        if total_seconds == 0.0:
            try:
                total_seconds = float(self.length)
            except ValueError:
                raise ValueError(f"Invalid time format: {self.length}")

        return total_seconds

@dataclass
class TimelapseOptions:
    reverse: bool = False
    list_weeks_centered: bool = True
    speed_up_factor: float = 1 / 7.5
    head_tail_ratio: Tuple[int, int] = (2, 1)
    video_stabilization: bool = False

@dataclass
class TimelapseStabilizationOptions:
    shakiness: int = 5  # 1-10
    smoothing: int = 10  # number of forwards and backwards frames +1 to use for smoothing

@dataclass
class CompilerOptions:
    show_ffmpeg_commands: bool = False
    list_weeks: bool = False

@dataclass
class Configuration:
    kid_info: KidInfo = field(default_factory=KidInfo)
    directories: Directories = field(default_factory=Directories)
    timelapse_video: TimelapseVideo = field(default_factory=TimelapseVideo)
    timelapse_options: TimelapseOptions = field(default_factory=TimelapseOptions)
    timelapse_stabilization_options: TimelapseStabilizationOptions = field(default_factory=TimelapseStabilizationOptions)
    compiler_options: CompilerOptions = field(default_factory=CompilerOptions)

    @staticmethod
    def from_dict(data: dict) -> 'Configuration':
        kid_info_data = data.get('kid_info', {})
        if 'birthday' in kid_info_data and isinstance(kid_info_data['birthday'], str):
            kid_info_data['birthday'] = date.fromisoformat(kid_info_data['birthday'])
        directories_data = data.get('directories', {})
        timelapse_video_data = data.get('timelapse_video', {})
        timelapse_options_data = data.get('timelapse_options', {})
        timelapse_stabilization_options_data =  data.get('timelapse_stabilization_options', {})
        compiler_options_data = data.get('compiler_options', {})

        # yaml to python conversion
        if 'head_tail_ratio' in timelapse_options_data and isinstance(timelapse_options_data['head_tail_ratio'], list):
            timelapse_options_data['head_tail_ratio'] = tuple(timelapse_options_data['head_tail_ratio'])
        if 'speed_up_factor' in timelapse_options_data and isinstance(timelapse_options_data['speed_up_factor'], float):
            timelapse_options_data['speed_up_factor'] = 1.0/float(timelapse_options_data['speed_up_factor'])


        return Configuration(
            kid_info=KidInfo(**kid_info_data),
            directories=Directories(**directories_data),
            timelapse_video=TimelapseVideo(**timelapse_video_data),
            timelapse_options=TimelapseOptions(**timelapse_options_data),
            timelapse_stabilization_options=TimelapseStabilizationOptions(**timelapse_stabilization_options_data),
            compiler_options=CompilerOptions(**compiler_options_data),
        )

def load_configuration(config_path: str = None) -> Configuration:
    if config_path is not None and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            user_config = yaml.safe_load(f) or {}
        return Configuration.from_dict(user_config)
    return Configuration()
