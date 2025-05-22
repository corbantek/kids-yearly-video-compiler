import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from typing import Dict, Sequence
import yaml
import ffmpeg
from .configuration import load_configuration, Configuration
import argparse
from .video_inspector import VideoInfo, get_all_video_info, get_video_info

def main(config_path=None) -> None:
    global config
    config = load_configuration(config_path)
    # gather video information
    print(f"Gathering Video Information... Input Directory: {config.directories.input_videos}")
    videos = get_all_video_info(config.directories.input_videos)
    video_aggregation_info = get_video_aggregation_info(list(videos.values()))
    output_video_aggregation_info(video_aggregation_info)

    if config.timelapse_options.constant_speed_up_algo:
        constant_speed_up_algorithm(videos, video_aggregation_info)
    if config.compiler_options.list_weeks:
        for video_key in sorted(videos.keys()):
            print(f"{video_key} - {videos[video_key].get_since_birthday(config.kid_info.birthday)}")

@dataclass
class VideoAggregation:
    n_videos: int = 0
    average_duration: float = 0.0
    total_duration: float = 0.0
    min_width: int = 0
    max_width: int = 0
    min_height: int = 0
    max_height: int = 0

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

def timelapse_partial_videos(
        video_aggregation_info: VideoAggregation, videos: Dict[str, VideoInfo]
) -> Dict[str, VideoInfo]:
    max_video_length = (config.timelapse_video.length / video_aggregation_info.n_videos) / config.timelapse_options.speed_up_factor
    head_length = (max_video_length / (config.timelapse_options.head_tail_ratio[0]+config.timelapse_options.head_tail_ratio[1])) * config.timelapse_options.head_tail_ratio[0]
    tail_length = (max_video_length / (config.timelapse_options.head_tail_ratio[0]+config.timelapse_options.head_tail_ratio[1])) * config.timelapse_options.head_tail_ratio[1]
    for key in sorted(videos.keys()):
        video = videos[key]
        output_file_name = f"timelapse_{video.base_name}"
        output_file_path = f"{config.directories.scratch}{output_file_name}"
        timelapse_text = video.get_since_birthday(config.kid_info.birthday)
        if not os.path.isfile(output_file_path):
            if video.duration > max_video_length:
                video_head = (
                    ffmpeg.input(video.file_path, **{'noautorotate':None})
                    .trim(duration=head_length)
                    .filter("setpts", str(config.timelapse_options.speed_up_factor) + "*PTS")
                    .filter("scale", config.timelapse_video.max_width, -1)
                    )
                video_tail = (
                    ffmpeg.input(video.file_path, **{'noautorotate':None}, ss=video.duration-tail_length)
                    .trim(duration=tail_length)
                    .filter("setpts", str(config.timelapse_options.speed_up_factor) + "*PTS")
                    .filter("scale", config.timelapse_video.max_width, -1)
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
                if config.timelapse_options.instagram_style:
                    video_head = video_head.filter("crop", config.timelapse_video.max_height*(9/16),config.timelapse_video.max_height,(config.timelapse_video.max_width-(config.timelapse_video.max_height*(9/16)))/2,0)
                    video_tail = video_tail.filter("crop", config.timelapse_video.max_height*(9/16),config.timelapse_video.max_height,(config.timelapse_video.max_width-(config.timelapse_video.max_height*(9/16)))/2,0)
                if not config.timelapse_options.list_weeks_centered:
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
                speed_up_factor = (config.directories.timelapse_options.speed_up_factor * max_video_length) / video.duration
                if speed_up_factor > 1.0:
                    speed_up_factor = 1.0
                video_full = (
                    ffmpeg.input(video.file_path, **{'noautorotate':None})
                    .filter("setpts", str(speed_up_factor) + "*PTS")
                    .filter("scale", config.directories.output_video.width, -1)
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
                if config.timelapse_options.instagram_style:
                    video_full = video_full.filter("crop", config.directories.output_video.height*(9/16),config.directories.output_video.height,(config.directories.output_video.width-(config.directories.output_video.height*(9/16)))/2,0)
                if not config.timelapse_options.list_weeks_centered:
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
        videos[key] = get_video_info(config.directories.scratch, output_file_name)
    return videos



def combine_timelapase_video(videos: Dict[str, VideoInfo]) -> None:
    (
        ffmpeg.concat(
            *[
                ffmpeg.input(videos[video_key].file_path)
                for video_key in sorted(videos.keys(), reverse=config.timelapse_options.reverse)
            ]
        )
        .output(f"{config.directories.output_video}timelapse.mp4")
        .overwrite_output()
        .run()
    )

def constant_speed_up_algorithm(videos: Dict[str, VideoInfo], video_aggregation_info: VideoAggregation) -> None:
    # create timelapse video
    timelapse_partial_videos(video_aggregation_info, videos)
    combine_timelapase_video(videos)
