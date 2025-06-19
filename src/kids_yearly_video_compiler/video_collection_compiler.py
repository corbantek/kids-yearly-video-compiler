from datetime import datetime
import os
from typing import Callable, List, Tuple

import ffmpeg
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
        for video in video_collection.sorted():
            print(f"\tapplying {transform_name} to {video.file_path}")
            (
                transformed_file_name,
                transformed_file_path,
            ) = self._get_transformed_video_file_path(transform_name, video)
            if os.path.isfile(transformed_file_path):
                print(f"\tskipping {transformed_file_name} because it already exists")
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
            command.run(quiet=True)

            transformed_videos.append(
                get_video_info(
                    self.config.directories.scratch,
                    transformed_file_name,
                    video.base_name,
                )
            )
        return VideoCollection(transformed_videos)

    def save(self):
        output_video_path = os.path.join(self.config.directories.output_video, f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}-{self.config.kid_info.name.replace(' ', '-')}.mp4")
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
        command.run(quiet=True)

    def compile(self):
        # max_video_length is the length is the max length each video **will** be after being sped up
        max_video_length = (
            self.config.timelapse_video.get_length_in_seconds() / self.video_collection.size()
        ) / self.config.timelapse_options.speed_up_factor

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

        unstabilized_videos: List[VideoInfo] = []
        for video in self.video_collection.sorted():
            (
                unstabilized_file_name,
                unstabilized_file_path,
            ) = self._get_unstabilized_video_file_path(video)

            print(f"compiling unstabilized video for {video.base_name}")
            if os.path.isfile(unstabilized_file_path):
                print(f"\tskipping {unstabilized_file_name} because it already exists")
                unstabilized_videos.append(
                    get_video_info(
                        self.config.directories.scratch,
                        unstabilized_file_name,
                        video.base_name,
                    )
                )
                continue

            if (
                video.duration > max_video_length
            ):  # TODO this calculation is wrong, we need to take into account the speed up factor
                # video length is longer than max_video_length, we need to split it into head and tail
                video_head = (
                    ffmpeg.input(video.file_path, **{"noautorotate": None})
                    .trim(duration=head_length)
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
                        ss=video.duration - tail_length,
                    )
                    .trim(duration=tail_length)
                    .filter(
                        "setpts",
                        str(self.config.timelapse_options.speed_up_factor) + "*PTS",
                    )
                    .filter("scale", self.config.timelapse_video.max_width, -1)
                )
                self._save(
                    ffmpeg.concat(video_head, video_tail), unstabilized_file_path
                ).run(quiet=True)
            else:
                # sped up video length is shorter than max_video_length, we can speed up the entire video
                speed_up_factor = (
                    self.config.directories.timelapse_options.speed_up_factor
                    * max_video_length
                ) / video.duration
                if speed_up_factor > 1.0:
                    speed_up_factor = 1.0
                video_full = (
                    ffmpeg.input(video.file_path, **{"noautorotate": None})
                    .filter("setpts", str(speed_up_factor) + "*PTS")
                    .filter("scale", self.config.directories.output_video.width, -1)
                )
                self._save(video_full, unstabilized_file_path).run(quiet=True)

            unstabilized_videos.append(
                get_video_info(
                    self.config.directories.scratch,
                    unstabilized_file_name,
                    video.base_name,
                )
            )
        # store our scratch videos in a collection so we can combine them into a final video
        unstabilized_video_collection = VideoCollection(unstabilized_videos)

        pre_filtered_video_collection = (
            self._apply_video_stabilization(unstabilized_video_collection)
            if self.config.timelapse_options.video_stabilization
            else unstabilized_video_collection
        )
        self.compiled_video_collection = self._transform(
            "compiled", pre_filtered_video_collection, self._transform_video_filters
        )


    def _transform_video_filters(
        self, video: VideoInfo, output_file_path: str, transform_arguments: dict = {}
    ) -> Stream:
        stream = ffmpeg.input(video.file_path)
        stream = self._apply_filters(stream, video)
        return self._save(stream, output_file_path)

    def _apply_filters(self, stream: Stream, video: VideoInfo) -> Stream:
        if video.hdr:
            print(f"\tfixing contrast for hdr video {video.file_path}")
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
        for video in unstabilized_video_collection.sorted():
            print(f"detecting video stabilization for {video.file_path}")
            stabilization_data_file_path = self._get_stabilization_data_file_path(video)
            if os.path.isfile(stabilization_data_file_path):
                print(
                    f"\tskipping detection of {video.file_path} stabilization because it already exists"
                )
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
            command.run(quiet=True)

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
