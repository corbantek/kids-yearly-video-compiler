from datetime import datetime
import os
from typing import Callable, List, Tuple

import ffmpeg
import re
import subprocess
from tqdm import tqdm
from ffmpeg.nodes import Stream
from kids_yearly_video_compiler.configuration import Configuration
from kids_yearly_video_compiler.video_collection import VideoCollection
from kids_yearly_video_compiler.video_inspector import VideoInfo, get_video_info


class VideoCollectionCompiler:
    def __init__(self, config: Configuration, video_collection: VideoCollection):
        self.config = config
        self.video_collection = video_collection

        self.compiled_video_collection: VideoCollection = None

    def _print_ffmpeg_command(self, command: Stream):
        if self.config.compiler_options.show_ffmpeg_commands:
            print("ffmpeg command:", " ".join(command.compile()))

    def _get_transformed_video_file_path(
        self, transform_name: str, video: VideoInfo
    ) -> Tuple[str, str]:
        transformed_file_name = f"{video.base_name}-{transform_name}.mp4"
        return (
            transformed_file_name,
            f"{self.config.directories.scratch}/{transformed_file_name}",
        )

    # TODO move this to video collection
    def _transform(
        self,
        transform_name: str,
        video_collection: VideoCollection,
        transform_video_function: Callable[[VideoInfo, str, dict], Stream],
        transform_argument_functions: dict[Callable, str] = {},
    ) -> VideoCollection:
        transformed_videos: List[VideoInfo] = []
        print(f"applying {transform_name} to {video_collection.size()} videos")
        with tqdm(video_collection.sorted(), desc=f"applying {transform_name}", unit="video", colour="green") as pbar:
            for video in pbar:
                (
                    transformed_file_name,
                    transformed_file_path,
                ) = self._get_transformed_video_file_path(transform_name, video)
                if os.path.isfile(transformed_file_path):
                    transformed_videos.append(
                        get_video_info(
                            self.config.directories.scratch,
                            transformed_file_name,
                            video.base_name,
                        )
                    )
                    continue

                command = transform_video_function(
                    video, transformed_file_path, transform_argument_functions
                )
                self._print_ffmpeg_command(command)
                duration = video.duration
                if "duration" in transform_argument_functions:
                    duration = transform_argument_functions["duration"]
                self.run_ffmpeg_with_progress(command.compile(), duration, f"processing {video.base_name}")

                transformed_videos.append(
                    get_video_info(
                        self.config.directories.scratch,
                        transformed_file_name,
                        video.base_name,
                    )
                )

        return VideoCollection(transformed_videos)

    def run_ffmpeg_with_progress(self, command: List[str], duration: float = None, description: str = "Processing"):
        """
        Run FFmpeg command with progress bar

        Args:
            command: FFmpeg command as list of strings
            duration: Total duration of processing time in seconds
            description: Description for progress bar
        """

        # Start FFmpeg process
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        # Create progress bar
        with tqdm(
            total=duration,
            desc=description,
            unit="s",
            #bar_format='{l_bar}{bar}| {n:.1f}/{total:.1f}s [{elapsed}<{remaining}, {rate_fmt}]'
        ) as pbar:

            # Monitor stderr for progress
            for line in process.stderr:
                # Look for time= in FFmpeg output
                time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                if time_match:
                    hours, minutes, seconds = time_match.groups()
                    current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

                    # Update progress bar (but don't exceed total)
                    pbar.n = min(current_time, duration)
                    pbar.refresh()

                # Also capture any errors
                if "Error" in line or "error" in line:
                    pbar.write(f"FFmpeg error: {line.strip()}")
            pbar.n = duration
            pbar.refresh()

        # Wait for process to complete
        return_code = process.wait()

        if return_code != 0:
            # Get any remaining error output
            stderr_output = process.stderr.read()
            raise RuntimeError(f"FFmpeg failed with return code {return_code}: {stderr_output}")

        return return_code

    def save(self):
        output_video_name = f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}-{self.config.kid_info.name.replace(' ', '-')}.mp4"
        output_video_path = os.path.join(self.config.directories.output_video, output_video_name)
        print(f"saving final video to {output_video_path}")
        command = (
            ffmpeg.concat(
                *[
                    ffmpeg.input(scratch_video.file_path)
                    for scratch_video in self.compiled_video_collection.sorted(
                        reverse=self.config.timelapse_options.reverse
                    )
                ]
            )
            .output(output_video_path)
            .overwrite_output()
        )
        self._print_ffmpeg_command(command)

        # Calculate total duration for all videos being concatenated
        total_duration = sum(video.duration for video in self.compiled_video_collection.videos)
        self.run_ffmpeg_with_progress(command.compile(), total_duration, f"writing {output_video_name}")

    def compile(self):
        # apply head-tail algorithm
        head_tail_algorithm_collection = self._apply_head_tail_algorithm(self.video_collection)

        # apply video stabilization
        pre_filtered_video_collection = (
            self._apply_video_stabilization(head_tail_algorithm_collection)
            if self.config.timelapse_options.video_stabilization
            else head_tail_algorithm_collection
        )

        # apply video filters
        self.compiled_video_collection = self._transform(
            "video-filters", pre_filtered_video_collection, self._transform_video_filters
        )

    def _transform_head_tail_algorithm(self, video: VideoInfo, output_file_path: str, transform_arguments: dict = {}) -> Stream:
        if (
            video.duration > transform_arguments["max_video_length"]
        ):  # TODO this calculation is wrong, we need to take into account the speed up factor
            # video length is longer than max_video_length, we need to split it into head and tail
            video_head = (
                ffmpeg.input(video.file_path, **{"noautorotate": None})
                .trim(duration=transform_arguments["head_length"])
                .filter(
                    "setpts",
                    str(self.config.timelapse_options.speed_up_factor) + "*PTS",
                )
                .filter("scale", self.config.timelapse_video.max_width, -1)
            )
            video_tail = (
                ffmpeg.input(
                    video.file_path,
                    **{"noautorotate": None},
                    ss=video.duration - transform_arguments["tail_length"],
                )
                .trim(duration=transform_arguments["tail_length"])
                .filter(
                    "setpts",
                    str(self.config.timelapse_options.speed_up_factor) + "*PTS",
                )
                .filter("scale", self.config.timelapse_video.max_width, -1)
            )
            return self._save(
                ffmpeg.concat(video_head, video_tail), output_file_path
            )
        else:
            # sped up video length is shorter than max_video_length, we can speed up the entire video to fit the max length
            speed_up_factor = (
                self.config.directories.timelapse_options.speed_up_factor
                * transform_arguments["max_video_length"]
            ) / video.duration
            # if the speed up factor is greater than 1.0, we need to set it to 1.0 so we aren't in slow motion
            # (its okay if the video is shorter than the max length)
            if speed_up_factor > 1.0:
                speed_up_factor = 1.0
            video_full = (
                ffmpeg.input(video.file_path, **{"noautorotate": None})
                .filter("setpts", str(speed_up_factor) + "*PTS")
                .filter("scale", self.config.directories.output_video.width, -1)
            )
            return self._save(video_full, output_file_path)

    def _apply_head_tail_algorithm(self, original_video_collection: VideoCollection) -> VideoCollection:
        duration = (
            self.config.timelapse_video.get_length_in_seconds() / self.video_collection.size()
        )
        # max_video_length is the length is the max length each video **will** be after being sped up and speed up factor
        max_video_length = duration / self.config.timelapse_options.speed_up_factor

        video_parts = (
            self.config.timelapse_options.head_tail_ratio[0]
            + self.config.timelapse_options.head_tail_ratio[1]
        )
        video_part_length = max_video_length / video_parts

        head_length = (
            video_part_length * self.config.timelapse_options.head_tail_ratio[0]
        )
        tail_length = (
            video_part_length * self.config.timelapse_options.head_tail_ratio[1]
        )

        return self._transform(
            "head-tail-algorithm", original_video_collection, self._transform_head_tail_algorithm, {"duration": duration, "max_video_length": max_video_length, "head_length": head_length, "tail_length": tail_length}
        )

    def _transform_video_filters(
        self, video: VideoInfo, output_file_path: str, transform_arguments: dict = {}
    ) -> Stream:
        stream = ffmpeg.input(video.file_path)
        stream = self._apply_filters(stream, video)
        return self._save(stream, output_file_path)

    def _apply_filters(self, stream: Stream, video: VideoInfo) -> Stream:
        if video.hdr:
            #print(f"\tfixing contrast for hdr video {video.file_path}")
            stream = self._hdr_to_sdr_filter(stream)

        if self.config.timelapse_video.instagram_style:
            stream = self._instagram_style_filter(stream)

        stream = self._draw_birthday_week(
            stream, video, self.config.timelapse_options.list_weeks_centered
        )
        return stream

    def _hdr_to_sdr_filter(self, stream: Stream) -> Stream:
        return (
            stream.filter("zscale", t="linear", npl=100)
            .filter("format", pix_fmts="gbrpf32le")
            .filter("zscale", p="bt709")
            .filter("tonemap", tonemap="hable", desat=0)
            .filter("zscale", t="bt709", m="bt709", r="tv")
            .filter("format", pix_fmts="yuv420p")
        )

    def _instagram_style_filter(self, stream: Stream) -> Stream:
        return stream.filter(
            "crop",
            self.config.timelapse_video.max_height * (9 / 16),
            self.config.timelapse_video.max_height,
            (
                self.config.timelapse_video.max_width
                - (self.config.timelapse_video.max_height * (9 / 16))
            )
            / 2,
            0,
        )

    def _draw_birthday_week(
        self, stream: Stream, video: VideoInfo, centered: bool = True
    ) -> Stream:
        timelapse_text = video.get_since_birthday(self.config.kid_info.birthday)
        if centered:
            return stream.drawtext(
                text=timelapse_text,
                x="(w-text_w)/2",
                y="h-th-20",
                fontsize=36,
                fontcolor="white",
            )
        else:
            return stream.drawtext(
                text=timelapse_text,
                x="w-tw-10",
                y="h-th-10",
                fontsize=36,
                fontcolor="white",
            )

    def _save(self, stream: Stream, output_file_path: str) -> Stream:
        return stream.output(
            output_file_path,
            r="30000/1001",
            vcodec="libx264",
            pix_fmt="yuv420p",
        )

    def _get_unstabilized_video_file_path(self, video: VideoInfo) -> Tuple[str, str]:
        unstabilized_file_name = f"{video.base_name}-unstabilized.mp4"
        return (
            unstabilized_file_name,
            f"{self.config.directories.scratch}/{unstabilized_file_name}",
        )

    def _get_stabilization_data_file_path(self, video: VideoInfo) -> str:
        return (
            f"{self.config.directories.scratch}/{video.base_name}-stabilized-data.trf"
        )


    def _apply_video_stabilization(
        self, unstabilized_video_collection: VideoCollection
    ) -> VideoCollection:
        print(f"detecting video stabilization for {unstabilized_video_collection.size()} videos")
        with tqdm(unstabilized_video_collection.sorted(), desc="detecting video stabilization", unit="video", colour="green") as pbar:
            for video in pbar:
                stabilization_data_file_path = self._get_stabilization_data_file_path(video)
                if os.path.isfile(stabilization_data_file_path):
                    continue

                command = (
                    ffmpeg.input(video.file_path)
                    .filter(
                        "vidstabdetect",
                        shakiness=self.config.timelapse_stabilization_options.shakiness,
                        result=stabilization_data_file_path,
                    )
                    .output("-", f="null")
                )
                self._print_ffmpeg_command(command)
                ffmpeg_command = command.compile()
                self.run_ffmpeg_with_progress(ffmpeg_command, video.duration, f"processing {video.base_name}...")

        return self._transform(
            "stabilized",
            unstabilized_video_collection,
            self._transform_video_stabilization,
            {"stabilization_data_file_path": self._get_stabilization_data_file_path},
        )

    def _transform_video_stabilization(
        self, video: VideoInfo, output_file_path: str, transform_arguments: dict = {}
    ) -> Stream:
        return (
            ffmpeg.input(video.file_path)
            .filter(
                "vidstabtransform",
                smoothing=self.config.timelapse_stabilization_options.smoothing,
                input=transform_arguments["stabilization_data_file_path"](video),
            )
            .output(output_file_path)
        )
