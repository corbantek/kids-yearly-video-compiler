from datetime import datetime
import os
from typing import List, Tuple

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

    def save(self):
        output_video_path = f"{self.config.directories.output_video}/{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}-{self.config.kid_info.name.replace(' ', '-')}.mp4"
        print(f"saving final video to {output_video_path}")
        (
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
            .run(quiet=True)
        )

    def compile(self):
        # max_video_length is the length is the max length each video **will** be after being sped up
        max_video_length = (
            self.config.timelapse_video.length / self.video_collection.size()
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
                )
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
                self._save(video_full, unstabilized_file_path)

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
        self.compiled_video_collection = self._apply_video_filters(
            pre_filtered_video_collection
        )

    def _apply_video_filters(
        self, video_collection: VideoCollection
    ) -> VideoCollection:
        compiled_videos: List[VideoInfo] = []
        for video in video_collection.sorted():
            print(f"applying filters to {video.file_path}")
            compiled_file_name, compiled_file_path = self._get_compiled_video_file_path(
                video
            )
            if os.path.isfile(compiled_file_path):
                print(f"\tskipping {compiled_file_name} because it already exists")
                compiled_videos.append(
                    get_video_info(
                        self.config.directories.scratch,
                        compiled_file_name,
                        video.base_name,
                    )
                )
                continue
            stream = ffmpeg.input(video.file_path)
            stream = self._apply_filters(stream, video)
            self._save(stream, compiled_file_path)
            compiled_videos.append(
                get_video_info(
                    self.config.directories.scratch, compiled_file_name, video.base_name
                )
            )
        return VideoCollection(compiled_videos)

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
        (
            stream.output(
                output_file_path,
                r="30000/1001",
                vcodec="libx264",
                pix_fmt="yuv420p",
            ).run(quiet=True)
        )

    def _get_compiled_video_file_path(self, video: VideoInfo) -> Tuple[str, str]:
        compiled_file_name = f"{video.base_name}-compiled.mp4"
        return (
            compiled_file_name,
            f"{self.config.directories.scratch}/{compiled_file_name}",
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

    def _get_stabilized_video_file_path(self, video: VideoInfo) -> Tuple[str, str]:
        stabilized_file_name = f"{video.base_name}-stabilized.mp4"
        return (
            stabilized_file_name,
            f"{self.config.directories.scratch}/{stabilized_file_name}",
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
            # command = ffmpeg.input(video.file_path).output(
            #     "-",
            #     vf=f"vidstabdetect=shakiness={self.config.timelapse_stabilization_options.shakiness}:result='{self._get_stabilization_data_file_path(video)}'",
            #     f="null",
            # )
            self._print_ffmpeg_command(command)
            command.run(quiet=True)

        stabilized_videos: List[VideoInfo] = []
        for video in unstabilized_video_collection.sorted():
            (
                stabilized_file_name,
                stabilized_file_path,
            ) = self._get_stabilized_video_file_path(video)
            print(f"stabilizing video {video.file_path}")
            if os.path.isfile(stabilized_file_path):
                print(
                    f"\tskipping {stabilized_file_name} stabilization because it already exists"
                )
                stabilized_videos.append(
                    get_video_info(
                        self.config.directories.scratch,
                        stabilized_file_name,
                        video.base_name,
                    )
                )
                continue

            command = (
                ffmpeg.input(video.file_path)
                .filter(
                    "vidstabtransform",
                    smoothing=self.config.timelapse_stabilization_options.smoothing,
                    input=self._get_stabilization_data_file_path(video),
                )
                .output(stabilized_file_path)
            )
            self._print_ffmpeg_command(command)
            command.run(quiet=True)
            stabilized_videos.append(
                get_video_info(
                    self.config.directories.scratch,
                    stabilized_file_name,
                    video.base_name,
                )
            )
        return VideoCollection(stabilized_videos)
