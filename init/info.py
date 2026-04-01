""" OS info helper functions for discord.py bot """

from init.constants import VALID_ACTIVITY_TYPES, VALID_STATUSES
from init.logutils import log, separator
from helpers.confighelpers import ConfigCategory, get_config_value, correct_type, correct_value_in

import discord
from os import name
from platform import python_implementation, python_version, system
from random import choice
from typing import Any
from types import NoneType

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

def get_activity_data(config: dict[str, Any]) -> dict[str, Any]:
    """ Get bot activity metadata to send to the Discord API based on given configuration. 
    
    Return value has the following available keys: `status_type`, `activity_enabled`, `activity_name`, `activity_type` and `activity_state`. """
    
    data = {
        "status_type": correct_type(get_config_value(config, "status_type", ConfigCategory.ACTIVITY.value), (str, NoneType), None),
        "activity_enabled": correct_type(get_config_value(config, "enable_activity", ConfigCategory.ACTIVITY.value), bool, False),
        "activity_name": correct_type(get_config_value(config, "activity_name", ConfigCategory.ACTIVITY.value), str, "with the API"),
        "activity_type": correct_value_in(get_config_value(config, "activity_type", ConfigCategory.ACTIVITY.value), VALID_ACTIVITY_TYPES, "playing")
    }

    if data["activity_type"] in ("playing", "listening"):
        data["activity_state"] = correct_type(get_config_value(config, "activity_state", ConfigCategory.ACTIVITY.value), (str, NoneType), None)
    else:
        data["activity_state"] = None
    
    return data

def get_activity(data: dict[str, Any]) -> discord.Activity | None:
    """ Return a bot activity, if enabled. 
    
    `data` must be retreived using the `get_activity_data()` function first. """
    
    if data["activity_enabled"]:
        return discord.Activity(
            name=data["activity_name"],
            type=VALID_ACTIVITY_TYPES.get(data["activity_type"], discord.ActivityType.playing),
            state=data["activity_state"]
        )

    return None

def get_status(status_type: str | None) -> discord.Status:
    """ Return a discord Status based on `status_type`. 
    
    If `status_type` None, a random one will be chosen. Otherwise, if invalid, `discord.Status.online` is returned. """
    
    return choice((discord.Status.online, discord.Status.idle, discord.Status.do_not_disturb)) if status_type is None else\
    VALID_STATUSES.get(status_type, discord.Status.online)

def handle_which_ff_output(os: str, output: str | None, ff_type: str="mpeg") -> bool:
    """ Check output from which() and assess whether or not ffmpeg is installed. 
    
    Additionally, print information on how to install ffmpeg if not found. 
    
    Return a success value. """
    
    if output is None:
        log(f"FF{ff_type} not found!")
        log("Please visit the project's GitHub repository for detailed installation instructions.")
        
        if os == "posix":
            log(f"If you're running a Debian/Ubuntu based Linux distro, install the full binary set with 'sudo apt install ffmpeg'.\nOtherwise, check your distro's repositories or compile it from source.")
        else:
            log(f"If you're running Windows, make sure the FF{ff_type} executable is in the PATH environment variable.")
    
        return False
    
    log(f"Found FF{ff_type} at {output}")
    separator()

    return True