import pytest
from datetime import date
from kids_yearly_video_compiler.configuration import Configuration

def test_configuration_from_dict():
    config_dict = {
        'kid_info': {
            'name': 'Test Kid',
            'birthday': '2020-01-01',
        },
        'directories': {
            'input_videos': '/input/',
            'output_video': '/output/',
            'scratch': '/scratch/',
        },
        'timelapse_video': {
            'length': 10,
            'max_width': 1280,
            'max_height': 720,
            'instagram_style': False,
        },
        'timelapse_options': {
            'reverse': True,
            'list_weeks_centered': False,
            'speed_up_factor': 5.0,
            'head_tail_ratio': [3, 2],
        },
        'compiler_options': {
            'list_weeks': False,
        },
    }
    config = Configuration.from_dict(config_dict)
    assert config.kid_info.name == 'Test Kid'
    assert config.kid_info.birthday == date(2020, 1, 1)
    assert config.directories.input_videos == '/input/'
    assert config.directories.output_video == '/output/'
    assert config.directories.scratch == '/scratch/'
    assert config.timelapse_video.length == 10
    assert config.timelapse_video.max_width == 1280
    assert config.timelapse_video.max_height == 720
    assert config.timelapse_video.instagram_style is False
    assert config.timelapse_options.reverse is True
    assert config.timelapse_options.list_weeks_centered is False
    assert config.timelapse_options.speed_up_factor == 1 / 5.0
    assert config.timelapse_options.head_tail_ratio == (3, 2)
    assert config.compiler_options.list_weeks is False
