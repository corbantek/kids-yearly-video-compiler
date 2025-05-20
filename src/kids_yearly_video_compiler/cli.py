"""Command-line interface for the Kids Yearly Video Compiler."""

import argparse
from .yearly_video_generator import main

def cli():
    parser = argparse.ArgumentParser(description='Generate a yearly video timelapse.')
    parser.add_argument('--config', type=str, help='Path to the configuration file (default: default-config.yaml)')
    args = parser.parse_args()
    config_path = args.config if args.config else None
    main(config_path)

if __name__ == "__main__":
    cli()
