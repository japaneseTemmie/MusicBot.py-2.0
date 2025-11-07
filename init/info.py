""" Various helpers for discord.py bot init """

from init.constants import VALID_ACTIVITY_TYPES, VALID_STATUSES
from init.logutils import log, separator
from init.config import correct_type

import discord
from typing import Any
from types import NoneType
from os.path import dirname
from os import name
from platform import python_implementation, python_version, system
from sys import exit as sysexit
from random import choice

def get_directory(file: str | None=None) -> str:
    """ Return the directory path of `file`. 
    
    If `file` is None, return directory path of the file this function is in. """
    
    return dirname(__file__ if file is None else file)

def get_python() -> tuple[str, str]:
    """ Return the running Python implementation & version. """
    
    return python_implementation(), python_version()

def get_os() -> tuple[str, str, str | None]:
    """ Return OS info as a tuple with OS pretty name (e.g Linux), name (e.g posix), and kernel version (if available). """

    os = system()

    if name == "posix":
        from os import uname
        kernel = uname().release
    else:
        kernel = None

    return os, name, kernel

def get_activity_data(config: dict[str, Any]) -> tuple[str | None, str, str | None, str | None]:
    """ Get bot metadata to send to the Discord API. """
    
    activity_enabled = correct_type(config.get("enable_activity", False), bool, False)
    status = correct_type(config.get("default_status", None), (str, NoneType), None)
    activity_name = correct_type(config.get("activity_name", "with the API"), str, "with the API")
    activity_type = correct_type(config.get("activity_type", None), VALID_ACTIVITY_TYPES, None, "in")
    
    return activity_enabled, status, activity_name, activity_type

def get_activity(activity_enabled: bool, activity_name: str, activity_type: str) -> discord.Activity | None:
    """ Return a bot activity, if enabled. """
    
    if activity_enabled:
        return discord.Activity(
            name=activity_name,
            type=VALID_ACTIVITY_TYPES.get(activity_type, discord.ActivityType.playing)
        )

    return None

def get_status(status_type: str | None) -> discord.Status:
    """ Return a discord Status based on `status_type`. """
    
    return choice((discord.Status.online, discord.Status.idle, discord.Status.do_not_disturb)) if status_type is None else\
    VALID_STATUSES.get(status_type, discord.Status.online)

def handle_which_ff_output(os: str, output: str | None, ff_type: str="mpeg") -> None:
    """ Print information on how to install ffmpeg if not found. """
    
    if output is None:
        log(f"FF{ff_type} not found!")
        
        if os == "posix":
            log(f"If you're running a Debian/Ubuntu based Linux distro, install the full binary set with 'sudo apt install ffmpeg'.\nOtherwise, check your distro's repositories or compile it from source.")
        else:
            log(f"If you're running Windows, make sure the FF{ff_type} executable is in the PATH environment variable.")
    
        sysexit(1)
    
    log(f"Found FF{ff_type} at {output}")
    separator()
