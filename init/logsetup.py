""" Log setup helpers for discord.py bot """

from init.constants import VALID_LOG_LEVELS
from init.logutils import log, separator
from helpers.confighelpers import ConfigCategory, get_config_value, correct_type

from logging import FileHandler, Formatter, Logger, getLogger, INFO
from typing import Any
from os.path import join, exists
from os import remove

def set_up_logging(dir: str, config: dict[str, Any]) -> tuple[FileHandler, Formatter, Logger, str]:
    """ Set up logging to the `discord.log` file in the `dir` root directory. """
    
    log("Logging enabled")
    separator()
    log("Setting up logging...")

    path = join(dir, "discord.log")

    handler = FileHandler(path, "w", "utf-8")

    log(f"Created log file at {path}")
    
    formatter = Formatter("[{asctime}] | {levelname:<8} {name}: {message}", "%d/%m/%Y @ %H:%M:%S", style="{")
    
    level = correct_type(get_config_value(config, "log_level", ConfigCategory.OTHER.value), str, "normal").strip()
    
    log(f"Log level found: {level}, actual: {VALID_LOG_LEVELS.get(level, INFO)}")
    separator()

    logger = getLogger("discord")

    return handler, formatter, logger, level

def remove_log(dir: str) -> tuple[None, None, None, None]:
    """ Remove the `discord.log` file from the `dir` root folder. """
    
    log(f"Logging disabled")
    
    path = join(dir, "discord.log")

    if exists(path):
        try:
            remove(path)
            log(f"Removed {path}")
        except OSError as e:
            log(f"An error occurred while removing {path}.\nErr: {e}")
    separator()

    return None, None, None, None
