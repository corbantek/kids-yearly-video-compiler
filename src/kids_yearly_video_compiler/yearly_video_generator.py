import os
from typing import List
import ffmpeg
from kids_yearly_video_compiler.video_collection import VideoCollection
from kids_yearly_video_compiler.configuration import load_configuration
from kids_yearly_video_compiler.video_inspector import (
    VideoInfo,
    get_all_video_info,
    get_video_info,
)


def main(config_path=None) -> None:
    global config
    config = load_configuration(config_path)

    videos = get_all_video_info(config.directories.input_videos)
    video_collection = VideoCollection(videos)
    video_collection.print_info()

    if config.timelapse_options.constant_speed_up_algo:
        constant_speed_up_algorithm(video_collection)
    if config.compiler_options.list_weeks:
        for video in video_collection.sorted():
            print(
                f"{video.get_since_birthday(config.kid_info.birthday)}\t {video.base_name} "
            )


def constant_speed_up_algorithm(video_collection: VideoCollection) -> None:
    scrap_video_collection = timelapse_partial_videos(video_collection)
    combine_timelapase_video(scrap_video_collection)


def timelapse_partial_videos(video_collection: VideoCollection) -> VideoCollection:
    max_video_length = (
        config.timelapse_video.length / video_collection.size()
    ) / config.timelapse_options.speed_up_factor
    head_length = (
        max_video_length
        / (
            config.timelapse_options.head_tail_ratio[0]
            + config.timelapse_options.head_tail_ratio[1]
        )
    ) * config.timelapse_options.head_tail_ratio[0]
    tail_length = (
        max_video_length
        / (
            config.timelapse_options.head_tail_ratio[0]
            + config.timelapse_options.head_tail_ratio[1]
        )
    ) * config.timelapse_options.head_tail_ratio[1]

    scrap_videos: List[VideoInfo] = []
    for video in video_collection.sorted():
        output_file_name = f"timelapse_{video.base_name}"
        output_file_path = f"{config.directories.scratch}{output_file_name}"
        timelapse_text = video.get_since_birthday(config.kid_info.birthday)
        if os.path.isfile(output_file_path):
            print(f"skipping {video.base_name} because it already exists")
            scrap_videos.append(
                get_video_info(config.directories.scratch, output_file_name)
            )
            continue

        if video.duration > max_video_length:
            video_head = (
                ffmpeg.input(video.file_path, **{"noautorotate": None})
                .trim(duration=head_length)
                .filter(
                    "setpts", str(config.timelapse_options.speed_up_factor) + "*PTS"
                )
                .filter("scale", config.timelapse_video.max_width, -1)
            )
            video_tail = (
                ffmpeg.input(
                    video.file_path,
                    **{"noautorotate": None},
                    ss=video.duration - tail_length,
                )
                .trim(duration=tail_length)
                .filter(
                    "setpts", str(config.timelapse_options.speed_up_factor) + "*PTS"
                )
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
                video_head = video_head.filter(
                    "crop",
                    config.timelapse_video.max_height * (9 / 16),
                    config.timelapse_video.max_height,
                    (
                        config.timelapse_video.max_width
                        - (config.timelapse_video.max_height * (9 / 16))
                    )
                    / 2,
                    0,
                )
                video_tail = video_tail.filter(
                    "crop",
                    config.timelapse_video.max_height * (9 / 16),
                    config.timelapse_video.max_height,
                    (
                        config.timelapse_video.max_width
                        - (config.timelapse_video.max_height * (9 / 16))
                    )
                    / 2,
                    0,
                )
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
                    fontcolor="white",
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
                    fontcolor="white",
                )
            (
                ffmpeg.concat(video_head, video_tail)
                .output(
                    output_file_path,
                    r="30000/1001",
                    vcodec="libx264",
                    pix_fmt="yuv420p",
                )
                .run(quiet=True)
            )
        else:
            speed_up_factor = (
                config.directories.timelapse_options.speed_up_factor * max_video_length
            ) / video.duration
            if speed_up_factor > 1.0:
                speed_up_factor = 1.0
            video_full = (
                ffmpeg.input(video.file_path, **{"noautorotate": None})
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
                video_full = video_full.filter(
                    "crop",
                    config.directories.output_video.height * (9 / 16),
                    config.directories.output_video.height,
                    (
                        config.directories.output_video.width
                        - (config.directories.output_video.height * (9 / 16))
                    )
                    / 2,
                    0,
                )
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

            (
                video_full.output(
                    output_file_path,
                    r="30000/1001",
                    vcodec="libx264",
                    pix_fmt="yuv420p",
                ).run(quiet=True)
            )
        scrap_videos.append(
            get_video_info(config.directories.scratch, output_file_name)
        )
    return VideoCollection(scrap_videos)


def combine_timelapase_video(scrap_video_collection: VideoCollection) -> None:
    (
        ffmpeg.concat(
            *[
                ffmpeg.input(scrap_video.file_path)
                for scrap_video in scrap_video_collection.sorted(
                    reverse=config.timelapse_options.reverse
                )
            ]
        )
        .output(f"{config.directories.output_video}timelapse.mp4")
        .overwrite_output()
        .run(quiet=True)
    )
