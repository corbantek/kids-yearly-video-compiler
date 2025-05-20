import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from typing import Dict, Sequence
import yaml

import ffmpeg

# Move all constants into a dictionary for YAML config
DEFAULT_PREFERENCES = {
    'OUTPUT_VIDEO_DIR': "./functional_tests/output/",
    'INPUT_VIDEO_DIR': "./functional_tests/input/",
    'SCRATCH_DIR': "./functional_tests/scratch/",
    'TIMELAPSE_LENGTH': 15,
    'OUTPUT_WIDTH': 1920,
    'OUTPUT_HEIGHT': 1080,
    'BIRTHDAY': "2023-03-23",
    'REVERSE': False,
    'LIST_WEEKS': True,
    'LIST_WEEKS_CENTERED': True,
    'NORMALIZE_ALGO': False,
    'CONSTANT_SPEED_UP_ALGO': True,
    'SPEED_UP_FACTOR': 1 / 7.5,
    'HEAD_TAIL_RATIO': [2, 1],
    'INSTAGRAM_STYLE': True,
}

PREFERENCES_PATH = os.path.join(os.path.dirname(__file__), 'preferences.yaml')

# Load preferences from YAML if available
if os.path.exists(PREFERENCES_PATH):
    with open(PREFERENCES_PATH, 'r') as f:
        user_prefs = yaml.safe_load(f)
    PREFERENCES = {**DEFAULT_PREFERENCES, **(user_prefs or {})}
else:
    PREFERENCES = DEFAULT_PREFERENCES

# Assign variables from preferences
globals().update(PREFERENCES)
# Special handling for BIRTHDAY (convert from string to date)
if isinstance(BIRTHDAY, str):
    BIRTHDAY = date.fromisoformat(BIRTHDAY)
# Special handling for HEAD_TAIL_RATIO (convert to tuple)
if isinstance(HEAD_TAIL_RATIO, list):
    HEAD_TAIL_RATIO = tuple(HEAD_TAIL_RATIO)

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


@dataclass
class VideoAggregation:
    n_videos: int = 0
    average_duration: float = 0.0
    total_duration: float = 0.0
    min_width: int = 0
    max_width: int = 0
    min_height: int = 0
    max_height: int = 0

#def rename_videos(videos: List[VideoInfo]) -> None:

def get_video_info(path: str, video_file_name: str) -> VideoInfo:
    video_file_path = f"{path}{video_file_name}"
    probe = ffmpeg.probe(video_file_path)
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
        base_name=video_file_name,
        file_path=video_file_path,
        duration=float(video["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        hdr=video["color_primaries"] == "bt2020", #"bt709",
        probe_info=video,
    )


def get_timelapse_text(video: VideoInfo) -> str:
    days = video.date_taken - BIRTHDAY
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


def get_video_aggregation_info(videos: Sequence[VideoInfo]) -> VideoAggregation:
    # TODO Calculate Standard Deviation
    min_width, max_width = sys.maxsize, 0
    min_height, max_height = sys.maxsize, 0
    total_duration = 0
    for video in videos:
        total_duration += video.duration
        min_width, max_width = min(min_width, video.width), max(max_width, video.width)
        min_height, max_height = min(min_height, video.height), max(
            max_height, video.height
        )
    return VideoAggregation(
        n_videos=len(videos),
        average_duration=total_duration / len(videos),
        total_duration=total_duration,
        min_width=min_width,
        max_width=max_width,
        min_height=min_height,
        max_height=max_height,
    )


def output_video_aggregation_info(video_aggregation_info: VideoAggregation) -> None:
    print(f"number of videos: {video_aggregation_info.n_videos}")
    print(f"total duration: {video_aggregation_info.total_duration/60} minutes")
    print(f"average duration: {video_aggregation_info.average_duration} seconds")
    print(
        f"min width/height: {video_aggregation_info.min_width} / {video_aggregation_info.min_height}"
    )
    print(
        f"max width/height: {video_aggregation_info.max_width} / {video_aggregation_info.max_height}"
    )


def normalize_video_length(
    video_aggregation_info: VideoAggregation, video: VideoInfo
) -> VideoInfo:
    average_target_length: float = video_aggregation_info.average_duration
    if video.duration < average_target_length:
        return video
    output_file_name = f"scaled_adjusted_length_{video.base_name}"
    output_file_path = f"{SCRATCH_DIR}{output_file_name}"
    if not os.path.isfile(output_file_path):
        # Try to speed up the middle of the video to reduce the length to the target length
        if video.duration * (2 / 3) < average_target_length:
            # Speed up only the middle third
            third_length = video.duration / 3
            speed_up_factor = (average_target_length - (video.duration * (2 / 3))) / (
                video.duration / 3
            )
            (
                ffmpeg.concat(
                    ffmpeg.input(video.file_path)
                    .trim(duration=third_length)
                    .filter("scale", OUTPUT_WIDTH, -1),
                    ffmpeg.input(video.file_path, ss=third_length)
                    .trim(duration=third_length)
                    .filter("setpts", str(speed_up_factor) + "*PTS")
                    .filter("scale", OUTPUT_WIDTH, -1),
                    ffmpeg.input(video.file_path, ss=third_length * 2).filter(
                        "scale", OUTPUT_WIDTH, -1
                    ),
                )
                .output(output_file_path, r="30000/1001")
                .run()
            )
        elif video.duration * (2 / 5) < average_target_length:
            # Speed up the middle 3/5ths
            fifth_length = int(video.duration / 5)
            speed_up_factor = (average_target_length - (video.duration * (2 / 5))) / (
                video.duration * (3 / 5)
            )
            (
                ffmpeg.concat(
                    ffmpeg.input(video.file_path)
                    .trim(duration=fifth_length)
                    .filter("scale", OUTPUT_WIDTH, -1),
                    ffmpeg.input(video.file_path, ss=fifth_length)
                    .trim(duration=fifth_length * 3)
                    .filter("setpts", str(speed_up_factor) + "*PTS")
                    .filter("scale", OUTPUT_WIDTH, -1),
                    ffmpeg.input(video.file_path, ss=fifth_length * 4).filter(
                        "scale", OUTPUT_WIDTH, -1
                    ),
                )
                .output(output_file_path, r="30000/1001")
                .run()
            )
        else:
            print(f"Unable to reduce video: {video.file_path}")
            exit(1)
    return get_video_info(SCRATCH_DIR, output_file_name)


def timelapse_full_videos(
    video_aggregation_info: VideoAggregation, videos: Dict[str, VideoInfo]
) -> Dict[str, VideoInfo]:
    speed_up_factor: float = TIMELAPSE_LENGTH / video_aggregation_info.total_duration
    for key, video in videos.items():
        output_file_name = f"timelapse_{video.base_name}"
        output_file_path = f"{SCRATCH_DIR}{output_file_name}"
        if not os.path.isfile(output_file_path):
            (
                ffmpeg.input(video.file_path)
                .filter("setpts", str(speed_up_factor) + "*PTS")
                .filter("scale", OUTPUT_WIDTH, -1)
                .drawtext(
                    text=get_timelapse_text(video),
                    x="w-tw-10",
                    y="h-th-10",
                    fontsize=36,
                    fontcolor="white",
                )
                .output(output_file_path, r="30000/1001")
                .run()
            )
        videos[key] = get_video_info(SCRATCH_DIR, output_file_name)
    return videos

def timelapse_partial_videos(
        video_aggregation_info: VideoAggregation, videos: Dict[str, VideoInfo]
) -> Dict[str, VideoInfo]:
    max_video_length = (TIMELAPSE_LENGTH / video_aggregation_info.n_videos) / SPEED_UP_FACTOR
    head_length = (max_video_length / (HEAD_TAIL_RATIO[0]+HEAD_TAIL_RATIO[1])) * HEAD_TAIL_RATIO[0]
    tail_length = (max_video_length / (HEAD_TAIL_RATIO[0]+HEAD_TAIL_RATIO[1])) * HEAD_TAIL_RATIO[1]
    for key in sorted(videos.keys()):
        video = videos[key]
        output_file_name = f"timelapse_{video.base_name}"
        output_file_path = f"{SCRATCH_DIR}{output_file_name}"
        timelapse_text = get_timelapse_text(video)
        if not os.path.isfile(output_file_path):
            if video.duration > max_video_length:
                video_head = (
                    ffmpeg.input(video.file_path, **{'noautorotate':None})
                    .trim(duration=head_length)
                    .filter("setpts", str(SPEED_UP_FACTOR) + "*PTS")
                    .filter("scale", OUTPUT_WIDTH, -1)
                    )
                video_tail = (
                    ffmpeg.input(video.file_path, **{'noautorotate':None}, ss=video.duration-tail_length)
                    .trim(duration=tail_length)
                    .filter("setpts", str(SPEED_UP_FACTOR) + "*PTS")
                    .filter("scale", OUTPUT_WIDTH, -1)
                )
                if video.hdr:
                    print(f"Fixing Contrast for {video.base_name}\n\n")
                    # Fix Contrast with HDR to SDR Conversion
                    video_head = (
                        video_head
                        # HDR to SDR Conversion
                        .filter("zscale", t="linear", npl=100)
                        .filter("format", pix_fmts="gbrpf32le")
                        .filter("zscale", p="bt709")
                        .filter("tonemap", tonemap="hable", desat=0)
                        .filter("zscale", t="bt709", m="bt709", r="tv")
                        .filter("format", pix_fmts="yuv420p")
                    )
                    video_tail = (
                        video_tail
                        # HDR to SDR Conversion
                        .filter("zscale", t="linear", npl=100)
                        .filter("format", pix_fmts="gbrpf32le")
                        .filter("zscale", p="bt709")
                        .filter("tonemap", tonemap="hable", desat=0)
                        .filter("zscale", t="bt709", m="bt709", r="tv")
                        .filter("format", pix_fmts="yuv420p")
                    )
                if INSTAGRAM_STYLE:
                    video_head = video_head.filter("crop", OUTPUT_HEIGHT*(9/16),OUTPUT_HEIGHT,(OUTPUT_WIDTH-(OUTPUT_HEIGHT*(9/16)))/2,0)
                    video_tail = video_tail.filter("crop", OUTPUT_HEIGHT*(9/16),OUTPUT_HEIGHT,(OUTPUT_WIDTH-(OUTPUT_HEIGHT*(9/16)))/2,0)
                if not LIST_WEEKS_CENTERED:
                    video_head = video_head.drawtext(
                        text=timelapse_text,
                        x="w-tw-10",
                        y="h-th-10",
                        fontsize=36,
                        fontcolor="white",
                    )
                    video_tail = video_tail.drawtext(
                        text=timelapse_text,
                        x="w-tw-10",
                        y="h-th-10",
                        fontsize=36,
                        fontcolor="white"
                    )
                else:
                    video_head = video_head.drawtext(
                        text=timelapse_text,
                        x="(w-text_w)/2",
                        y="h-th-20",
                        fontsize=36,
                        fontcolor="white",
                    )
                    video_tail = video_tail.drawtext(
                        text=timelapse_text,
                        x="(w-text_w)/2",
                        y="h-th-20",
                        fontsize=36,
                        fontcolor="white"
                    )
                (   ffmpeg.concat(video_head, video_tail)
                    .output(output_file_path, r="30000/1001", vcodec="libx264", pix_fmt="yuv420p")
                    .run()
                )
            else:
                speed_up_factor = (SPEED_UP_FACTOR * max_video_length) / video.duration
                if speed_up_factor > 1.0:
                    speed_up_factor = 1.0
                video_full = (
                    ffmpeg.input(video.file_path, **{'noautorotate':None})
                    .filter("setpts", str(speed_up_factor) + "*PTS")
                    .filter("scale", OUTPUT_WIDTH, -1)
                )
                if video.hdr:
                    # Fix Contrast with HDR to SDR Conversion
                    video_full = (
                        video_full
                        # HDR to SDR Conversion
                        # Could also try this SDR="zscale=transfer=linear,tonemap=tonemap=clip:param=1.0:desat=2:peak=0,zscale=transfer=bt709,format=yuv420p"
                        .filter("zscale", t="linear", npl=100)
                        .filter("format", pix_fmts="gbrpf32le")
                        .filter("zscale", p="bt709")
                        .filter("tonemap", tonemap="hable", desat=0)
                        .filter("zscale", t="bt709", m="bt709", r="tv")
                        .filter("format", pix_fmts="yuv420p")
                    )
                if INSTAGRAM_STYLE:
                    video_full = video_full.filter("crop", OUTPUT_HEIGHT*(9/16),OUTPUT_HEIGHT,(OUTPUT_WIDTH-(OUTPUT_HEIGHT*(9/16)))/2,0)
                if not LIST_WEEKS_CENTERED:
                    video_full = video_full.drawtext(
                        text=timelapse_text,
                        x="w-tw-10",
                        y="h-th-10",
                        fontsize=36,
                        fontcolor="white",
                    )
                else:
                    video_full = video_full.drawtext(
                        text=timelapse_text,
                        x="(w-text_w)/2",
                        y="h-th-20",
                        fontsize=36,
                        fontcolor="white",
                    )

                (   video_full
                    .output(output_file_path, r="30000/1001", vcodec="libx264", pix_fmt="yuv420p")
                    .run()
                )
        videos[key] = get_video_info(SCRATCH_DIR, output_file_name)
    return videos



def combine_timelapase_video(videos: Dict[str, VideoInfo]) -> None:
    (
        ffmpeg.concat(
            *[
                ffmpeg.input(videos[video_key].file_path)
                for video_key in sorted(videos.keys(), reverse=REVERSE)
            ]
        )
        .output(f"{OUTPUT_VIDEO_DIR}timelapse.mp4")
        .overwrite_output()
        .run()
    )

def main() -> None:
    # gather video information
    print(f"Gathering Video Information... Input Directory: {INPUT_VIDEO_DIR}")
    video_file_names = [
        video_file_name
        for video_file_name in os.listdir(INPUT_VIDEO_DIR)
        if os.path.isfile(INPUT_VIDEO_DIR + "/" + video_file_name)
        and not video_file_name.startswith(".")
    ]
    videos = {
        video_file_name: get_video_info(INPUT_VIDEO_DIR, video_file_name)
        for video_file_name in video_file_names
    }
    video_aggregation_info = get_video_aggregation_info(list(videos.values()))
    output_video_aggregation_info(video_aggregation_info)

    if NORMALIZE_ALGO:
        normalize_video_algorithm(videos, video_aggregation_info)
    if CONSTANT_SPEED_UP_ALGO:
        constant_speed_up_algorithm(videos, video_aggregation_info)
    if LIST_WEEKS:
        for video_key in sorted(videos.keys()):
            print(f"{video_key} - {get_timelapse_text(videos[video_key])}")
            #print(f"{videos[video_key].probe_info}\n")


def normalize_video_algorithm(videos: Dict[str, VideoInfo], video_aggregation_info: VideoAggregation) -> None:
    # normalize video length (reduce excessively long videos)
    videos = {
        video_file_name: normalize_video_length(video_aggregation_info, video)
        for video_file_name, video in videos.items()
    }
    # update the video aggreation info
    video_aggregation_info = get_video_aggregation_info(list(videos.values()))
    output_video_aggregation_info(video_aggregation_info)
    # create timelapse video
    timelapse_full_videos(video_aggregation_info, videos)
    combine_timelapase_video(videos)

def constant_speed_up_algorithm(videos: Dict[str, VideoInfo], video_aggregation_info: VideoAggregation) -> None:
    # create timelapse video
    timelapse_partial_videos(video_aggregation_info, videos)
    combine_timelapase_video(videos)
