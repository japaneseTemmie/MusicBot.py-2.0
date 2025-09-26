""" Log setup helpers for discord.py bot """

from init.constants import VALID_LOG_LEVELS
from init.logutils import log, separator

from logging import FileHandler, Formatter, Logger, getLogger, INFO
from os.path import join, exists
from os import remove
from typing import Any

def set_up_logging(dir: str, config: dict[str, Any]) -> tuple[FileHandler, Formatter, Logger, str]:
    log("Logging enabled")
    separator()
    log("Setting up logging...")

    path = join(dir, "discord.log")

    handler = FileHandler(path, "w", "utf-8")

    log(f"Created log file at {path}")
    
    formatter = Formatter("[{asctime}] | {levelname:<8} {name}: {message}", "%d/%m/%Y @ %H:%M:%S", style="{")
    level = config.get("log_level", "normal").strip()
    
    log(f"Log level found: {level}, actual: {VALID_LOG_LEVELS.get(level, INFO)}")
    separator()

    logger = getLogger("discord")

    return handler, formatter, logger, level

def remove_log(dir: str) -> tuple[None, None, None, None]:
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
