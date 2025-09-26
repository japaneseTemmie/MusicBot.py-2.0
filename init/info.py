""" Various helpers for discord.py bot init """

from init.constants import VALID_ACTIVITY_TYPES, VALID_STATUSES
from init.logutils import log, separator

import discord
from os.path import join, dirname
from os import name
from platform import python_implementation, python_version, system
from sys import exit as sysexit
from random import choice

def get_current_directory(file: str | None=None) -> str:
    path = dirname(__file__ if file is None else file)
    log(f"Working directory: {path}")
    separator()

    return path

def get_python() -> tuple[str, str]:
    implementation, ver = python_implementation(), python_version()
    
    log(f"Running in {implementation} version {ver}")
    separator()

    return implementation, ver

def get_os() -> str:
    os = system()

    if name == "posix":
        from os import uname
        kernel = uname()
    else:
        kernel = None

    log(f"OS: {name} Pretty name: {os}")
    log(f"Kernel: {os + ' ' + kernel.release if kernel is not None else 'Unknown'}")
    separator()

    return os

def get_activity_data(config: dict) -> tuple[str | None, str, str | None, str | None]:
    """ Get data to send to the API. """
    
    activity_enabled = config.get("enable_activity", False)
    status = config.get("default_status", None)
    activity_name = config.get("activity_name", "with the API")
    activity_type = config.get("activity_type", None)

    return activity_enabled, status, activity_name, activity_type

def get_activity(activity_enabled: bool, activity_name: str, activity_type: str) -> discord.Activity | None:
    if activity_enabled:
        log("Activity is enabled")
        separator()

        return discord.Activity(
            name=activity_name,
            type=VALID_ACTIVITY_TYPES.get(activity_type, discord.ActivityType.playing)
        )

    log("Activity is disabled.")
    separator()

    return None

def get_status(status_type: str) -> discord.Status:
    return choice((discord.Status.online, discord.Status.idle, discord.Status.do_not_disturb)) if status_type is None else\
    VALID_STATUSES.get(status_type, discord.Status.online)

def handle_ffmpeg_path_output(os: str, output: str | None) -> None:
    if output is None:
        log(f"FFmpeg not found!")
        
        if os == "Linux":
            log(f"If you're running a Debian/Ubuntu based Linux distro, install it with 'sudo apt install ffmpeg'.\nOtherwise, check your distro's repositories or compile it from source.")
        elif os == "Windows":
            log(f"If you're running Windows, make sure the FFmpeg executable is in the PATH environment variable.")
    
        sysexit(1)
    
    log(f"Found FFmpeg at {output}")
    separator()
