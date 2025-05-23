from datetime import datetime
import os
from typing import List

import ffmpeg
from ffmpeg.nodes import Stream
from kids_yearly_video_compiler.configuration import Configuration
from kids_yearly_video_compiler.video_collection import VideoCollection
from kids_yearly_video_compiler.video_inspector import VideoInfo, get_video_info


class VideoCollectionCompiler:
    def __init__(self, config: Configuration, video_collection: VideoCollection):
        self.config = config
        self.video_collection = video_collection

        self.scratch_video_collection: VideoCollection = None

    def save(self):
        output_video_path = f"{self.config.directories.output_video}/{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}-{self.config.kid_info.name.replace(' ', '-')}.mp4"
        print(f"saving final video to {output_video_path}")
        (
            ffmpeg.concat(
                *[
                    ffmpeg.input(scratch_video.file_path)
                    for scratch_video in self.scratch_video_collection.sorted(
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

        scratch_videos: List[VideoInfo] = []
        for video in self.video_collection.sorted():
            output_file_name = f"scratch_{video.base_name}"
            output_file_path = f"{self.config.directories.scratch}{output_file_name}"

            print(f"compiling scratch video for {video.base_name}")
            if os.path.isfile(output_file_path):
                print(f"\tskipping {video.base_name} because it already exists")
                scratch_videos.append(
                    get_video_info(self.config.directories.scratch, output_file_name)
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
                if video.hdr:
                    print(f"\tfixing contrast for hdr video {video.base_name}")
                    video_head = self._hdr_to_sdr_filter(video_head)
                    video_tail = self._hdr_to_sdr_filter(video_tail)

                if self.config.timelapse_options.instagram_style:
                    video_head = self._instagram_style_filter(video_head)
                    video_tail = self._instagram_style_filter(video_tail)

                video_head = self._draw_birthday_week(
                    video_head, video, self.config.timelapse_options.list_weeks_centered
                )
                video_tail = self._draw_birthday_week(
                    video_tail, video, self.config.timelapse_options.list_weeks_centered
                )

                self._save(ffmpeg.concat(video_head, video_tail), output_file_path)
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
                if video.hdr:
                    video_full = self._hdr_to_sdr_filter(video_full)

                if self.config.timelapse_options.instagram_style:
                    video_full = self._instagram_style_filter(video_full)

                video_full = self._draw_birthday_week(
                    video_full, video, self.config.timelapse_options.list_weeks_centered
                )

                self._save(video_full, output_file_path)
            scratch_videos.append(
                get_video_info(self.config.directories.scratch, output_file_name)
            )
        # store our scratch videos in a collection so we can combine them into a final video
        self.scratch_video_collection = VideoCollection(scratch_videos)

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
            self.config.directories.output_video.height * (9 / 16),
            self.config.directories.output_video.height,
            (
                self.config.directories.output_video.width
                - (self.config.directories.output_video.height * (9 / 16))
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
