"""Command-line interface for the Kids Yearly Video Compiler."""

import argparse

from kids_yearly_video_compiler.configuration import load_configuration
from kids_yearly_video_compiler.video_collection import VideoCollection
from kids_yearly_video_compiler.video_collection_compiler import VideoCollectionCompiler
from kids_yearly_video_compiler.video_inspector import get_all_video_info

def cli():
    parser = argparse.ArgumentParser(description='Generate a yearly video timelapse.')
    parser.add_argument('--config', type=str, help='Path to the configuration file (default: default-config.yaml)')
    args = parser.parse_args()
    config_path = args.config if args.config else None
    kids_yearly_video_compiler(config_path)

def kids_yearly_video_compiler(config_path=None) -> None:
    global config
    config = load_configuration(config_path)

    print(f"loading videos from {config.directories.input_videos}")
    videos = get_all_video_info(config.directories.input_videos)

    video_collection = VideoCollection(videos)
    video_collection.print_info()

    if config.compiler_options.list_weeks:
        print(f"please verify any missing weeks for {config.kid_info.name} since {config.kid_info.birthday}")
        for video in video_collection.sorted():
            print(
                f"\t{video.get_since_birthday(config.kid_info.birthday)}\t {video.base_name} "
            )

    video_collection_compiler = VideoCollectionCompiler(config, video_collection)
    video_collection_compiler.compile()
    video_collection_compiler.save()

if __name__ == "__main__":
    cli()
