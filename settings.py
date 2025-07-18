""" General settings configuration for discord.py bot.\n
config.json values docs:\n
- ydl_opts: Options passed to the YouTubeDL object in extractor.py/fetch()
- ffmpeg_opts: Options passed to ffmpeg when spawning a process, editing the
options in the file is useless, it is mainly used as a reference, instead, modify the copied version for each call
in music.py/play_track()\n
- cmd_prefix: Command prefix used for classic commands.\n
- enable_activity: Display custom activity.
- activity_name: The name of the activity. Appears after the type.
- activity_type: The activity type. Can be "playing", "watching" or "listening".
- default_status: The bot status. Can be "online", "idle", "do_not_disturb", "invisible" or null for a random status.
- enable_file_backups: Enables backup and restore of files like playlists.json and roles.json
in case of a bad write. Requires double the memory needed to open the file for each call.\n
- enable_logging: Enables logging of discord.py errors/debug messages/warnings depending
on the selected log_level.\n
- log_level: Level of log verbosity. Can be:\n
    normal: Simple info about various bot actions.\n
    verbose: Log everything.\n
    warning: Logs only warnings.\n
    errors: Logs only errors.\n
    critical: Logs critical errors.\n
    fatal: Logs fatal errors (crashes).\n
- skip_ffmpeg_check: Does not run the ffmpeg check if set to true. Not recommended if you don't have ffmpeg installed.\n

Module settings\n
These settings allow to control which module gets enabled, useful to limit features
and reduce memory usage if unused.\n

- enable_ModerationCog: Enables users to run commands from the moderation module.\n
- enable_UtilsCog: Enables users to run commands from the utils module. Contains important UX commands like /help. It is highly discouraged to disable this.\n
- enable_MusicCog: Enables users to run commands from the music module.\n """

# remove unused return code
# bump MAX_IO_WAIT_TIME to 20s
# remove ffmpeg_options

import asyncio
import re

# Discord imports
import discord
from discord.ext import commands
from discord.interactions import Interaction
from discord import Intents
from discord import app_commands

# Misc imports
from yt_dlp import YoutubeDL
from logging import FileHandler, Formatter, Logger, getLogger, ERROR, DEBUG, WARNING, INFO, FATAL, CRITICAL
from random import choice, randint, shuffle, random
from functools import lru_cache
from cachetools import TTLCache
from importlib import import_module
from inspect import getmembers, isclass
from datetime import datetime, timedelta
from time import time as get_time, sleep
from copy import deepcopy

# OS imports
from subprocess import Popen, PIPE
from platform import system, python_implementation, python_version
from psutil import virtual_memory
from os.path import join, dirname, exists, isdir
from os import listdir, remove, makedirs, getenv
from shutil import rmtree, which
from sys import exit as sysexit
from dotenv import load_dotenv
from json import load, dump, JSONDecodeError

# Types
from typing import NoReturn, Callable, Any
from types import ModuleType

def log(msg: str) -> None:
    print(f"[main] | {datetime.now().strftime('%d/%m/%Y @ %H:%M:%S')} | {msg}")

def separator() -> None:
    print("------------------------------")

log("Finished importing libraries")
separator()
sleep(0.5)

def open_file_settings(file_path: str, json_mode: bool, returnlines: bool=False) -> dict | str | list[str] | None:
    with open(file_path) as f:
        try:
            content = load(f) if json_mode else f.read() if not returnlines else f.readlines()
        except Exception as e:
            log(f"An error occured while opening file {file_path}\nErr: {e}")
            return None
        
        return content

def write_file_settings(file_path: str, content: dict | str, json_mode: bool) -> bool:
    with open(file_path, "w") as f:
        try:
            if not isinstance(content, dict) and json_mode:
                log("Cannot write content of type string with json_mode=True.")
                return False

            dump(content, f, indent=4) if json_mode else f.write(content)
        except Exception as e:
            log(f"An error occured while writing to file {file_path}\nErr: {e}")
            return False
        
        return True

def get_working_directory() -> str:
    path = dirname(__file__)
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
    mem = virtual_memory()
    if os in ("Linux", "Darwin"):
        from os import uname
        kernel = uname()
    else:
        kernel = None

    log("======HARDWARE======")
    log(f"Memory: {mem.total // 1024 // 1024}MB")
    log(f"Available memory: {mem.available // 1024 // 1024}MB")
    separator()
    log("======SYSTEM======")
    log(f"OS: {os}")
    log(f"Kernel: {os + ' ' + kernel.release if kernel is not None else 'Unknown'}")
    separator()

    return os

def get_api_data() -> tuple[str | None, str, str | None]:
    """ Get data to send to the API. """
    
    activity_enabled = CONFIG.get("enable_activity", False)
    status = CONFIG.get("default_status", None)
    activity_name = CONFIG.get("activity_name", "with the API")
    activity_type = CONFIG.get("activity_type", None)

    return activity_enabled, status, activity_name, activity_type

def get_activity() -> discord.Activity | None:
    if ACTIVITY_ENABLED:
        log("Activity is enabled")
        separator()

        return discord.Activity(
            name=ACTIVITY_NAME,
            type=VALID_ACTIVITY_TYPES.get(ACTIVITY_TYPE, discord.ActivityType.playing)
        )

    log("Activity is disabled.")
    separator()

    return None

def get_status() -> discord.Status:
    return choice((discord.Status.online, discord.Status.idle, discord.Status.do_not_disturb)) if STATUS_TYPE is None else\
    VALID_STATUSES.get(STATUS_TYPE, discord.Status.online)

def handle_ffmpeg_path_output(output: str | None) -> None | NoReturn:
    if output is None:
        log(f"FFmpeg not found!")
        
        if SYSTEM == "Linux":
            log(f"If you're running a Debian/Ubuntu based Linux distro, install it with 'sudo apt install ffmpeg'.\nOtherwise, check your distro's repositories or compile it from source.")
        elif SYSTEM == "Windows":
            log(f"If you're running Windows, make sure the FFmpeg executable is in the PATH environment variable.")
    
        sysexit(1)
    
    log(f"Found FFmpeg at {output}")
    separator()

def open_help_file() -> dict | None:
    path = join(PATH, "help.json")
    if not exists(path):
        log(f"No help file found. /help will not be available.")
        separator()
        
        return None

    log(f"Help file found at {path}")    
    log(f"Opening help file at {path}")
    
    content = open_file_settings(path, True, False)
    if content is None:
        log("No /help will be available.")
        return None
    
    log(f"Found {len(content.keys())} entries in help file.")

    separator()
    return content

def get_defaults() -> dict:
    return {
        "yt_dlp_options": {
            "quiet": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "extractaudio": True,
            "no_warnings": True
        },
        "command_prefix": "?",
        "enable_activity": False,
        "activity_name": "With the API",
        "activity_type": "playing",
        "default_status": None,
        "enable_file_backups": True,
        "enable_logging": True,
        "log_level": "normal",
        "skip_ffmpeg_check": False,
        "enable_ModerationCog": True,
        "enable_UtilsCog": True, 
        "enable_MusicCog": True,
        "enable_MyCog": False
    }

def check_config_exists(path: str, default_data: dict) -> None | NoReturn:
    if not exists(path):
        log(f"Creating config file because config.json does not exist at {path}")
        success = write_file_settings(path, default_data, True)

        if not success:
            sysexit(1)

        log(f"Created config file at {path}")

def get_config_data() -> dict | NoReturn:
    path = join(PATH, "config.json")
    default_data = get_defaults()

    check_config_exists(path, default_data)

    log(f"Found config file at {path}")
    log(f"Opening config file at {path}")
    content = open_file_settings(path, True, False)

    if content is None:
        sysexit(1)

    log(f"Found {len(content.keys())} entries in {path}")
    separator()
    
    return content

def set_up_logging() -> tuple[FileHandler, Formatter, Logger, str]:
    log("Logging enabled")
    log("Setting up logging...")

    path = join(PATH, "discord.log")

    HANDLER = FileHandler(path, "w", "utf-8")

    log(f"Created log file at {HANDLER.stream.name}")
    
    FORMATTER = Formatter("[{asctime}] | {levelname:<8} {name}: {message}", "%d/%m/%Y @ %H:%M:%S", style="{")
    LEVEL = CONFIG["log_level"].strip() if CONFIG["log_level"] in VALID_LOG_LEVELS else "normal"
    
    log(f"Log level found: {LEVEL}, actual: {VALID_LOG_LEVELS.get(LEVEL, INFO)}")
    separator()

    LOGGER = getLogger("discord")

    return HANDLER, FORMATTER, LOGGER, LEVEL

def remove_log() -> tuple[None, None, None, None]:
    log(f"Logging disabled")
    
    path = join(PATH, "discord.log")

    if exists(path):
        try:
            remove(path)
            log(f"Removed {path}")
        except (Exception, OSError) as e:
            log(f"An error occured while removing {path}.\nErr: {e}")
    separator()

    return None, None, None, None

VALID_LOG_LEVELS = {"normal": INFO, "verbose": DEBUG, "errors": ERROR, "warnings": WARNING, "critical": CRITICAL, "fatal": FATAL}
VALID_ACTIVITY_TYPES = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening}
VALID_STATUSES = {"online": discord.Status.online, "idle": discord.Status.idle, "do_not_disturb": discord.Status.do_not_disturb, "invisible": discord.Status.invisible}
RETURN_CODES = {
    "NOT_FOUND": 1,
    "BAD_EXTRACTION": 2,
    "READ_FAIL": 3,
    "WRITE_FAIL": 4,
    "WRITE_SUCCESS": 5,
    "QUERY_NOT_SUPPORTED": 6,
    "SAME_INDEX_REPOSITION": 7,
    "NO_PLAYLISTS": 8,
    "PLAYLIST_DOES_NOT_EXIST": 9,
    "PLAYLIST_EXISTS": 11,
    "MAX_PLAYLIST_LIMIT_REACHED": 12,
    "NAME_TOO_LONG": 13,
    "QUEUE_TOO_LONG": 14,
    "PLAYLIST_IS_EMPTY": 15,
    "INVALID_RANGE": 16,
    "HISTORY_IS_EMPTY": 17,
    "NOT_ENOUGH_TRACKS": 18,
    "SAME_INDEX_PLACEMENT": 19,
    "QUERY_IS_EMPTY": 20,
    "PLAYLIST_IS_FULL": 21,
    "NOT_A_NUMBER": 22
}

# System info and config
PATH = get_working_directory()
PYTHON = get_python()
SYSTEM = get_os()

CONFIG = get_config_data()
load_dotenv()
sleep(0.2)

# Define config vars as constants
CAN_LOG = CONFIG.get("enable_logging", True)
SKIP_FFMPEG_CHECK = CONFIG.get("skip_ffmpeg_check", False)
YDL_OPTIONS = CONFIG.get("yt_dlp_options", {"quiet": True, "noplaylist": True, "format": "bestaudio/best", "extractaudio": True, "no_warnings": True})
COMMAND_PREFIX = CONFIG.get("command_prefix", "?")
HELP = open_help_file()
COOLDOWNS = {
    "MUSIC_COMMANDS_COOLDOWN": 10.0,
    "EXTRACTOR_MUSIC_COMMANDS_COOLDOWN": 30.0, # prevents spam and bandwidth waste to an extent
    "HELP_COMMAND_COOLDOWN": 5.0,
    "ROLE_COMMANDS_COOLDOWN": 60.0,
    "PURGE_CHANNEL_COMMAND_COOLDOWN": 45.0,
    "KICK_COMMAND_COOLDOWN": 10.0,
    "BAN_COMMAND_COOLDOWN": 10.0,
    "UNBAN_COMMAND_COOLDOWN": 10.0,
    "TIMEOUT_COMMAND_COOLDOWN": 10.0,
    "REMOVE_TIMEOUT_COMMAND_COOLDOWN": 10.0,
    "ADD_ROLE_COMMAND_COOLDOWN": 10.0,
    "REMOVE_ROLE_COMMAND_COOLDOWN": 10.0,
    "DELETE_CHANNEL_COMMAND_COOLDOWN": 10.0,
    "CREATE_CHANNEL_COMMAND_COOLDOWN": 20.0,
    "CHANGE_SLOWMODE_COMMAND_COOLDOWN": 20.0,
    "ANNOUNCE_MESSAGE_COMMAND_COOLDOWN": 15.0,
    "MOVE_USER_COMMAND_COOLDOWN": 15.0,
    "VC_KICK_COMMAND_COOLDOWN": 15.0,
    "VC_MUTE_COMMAND_COOLDOWN": 15.0
}

# Logging
# Set up file handler and formatter for discord.py's logging lib, if requested.
HANDLER, FORMATTER, LOGGER, LEVEL = set_up_logging() if CAN_LOG else remove_log()

if not SKIP_FFMPEG_CHECK:
    FFMPEG = which("ffmpeg")
    handle_ffmpeg_path_output(FFMPEG)
else:
    FFMPEG = None
    log(f"FFMpeg check disabled. Program may not function correctly if package ffmpeg is not installed.")
    separator()

PLAYLIST_LOCKS = {}
ROLE_LOCKS = {}
ROLE_FILE_CACHE = TTLCache(maxsize=16384, ttl=3600)
PLAYLIST_FILE_CACHE = TTLCache(maxsize=16384, ttl=3600)

""" Asyncio.Event() objects that function as locks for safe shutdown.
Use .clear() to release the lock.
Use .set() to acquire the lock and refuse any VoiceClient or I/O operation.
Use .wait() to block the event loop if a lock is acquired (should be used rarely).
Use .is_set() to check if a lock is acquired (True) or not (False). Refuse operation if True. """
FILE_OPERATIONS_LOCKED_PERMANENTLY = asyncio.Event()
VOICE_OPERATIONS_LOCKED_PERMANENTLY = asyncio.Event()
MAX_IO_WAIT_TIME = 20000 # Only wait up to 20 seconds for locks to be false during shutdown.

# API stuff
ACTIVITY_ENABLED, STATUS_TYPE, ACTIVITY_NAME, ACTIVITY_TYPE = get_api_data()

INTENTS = Intents.all()
ACTIVITY = get_activity()
STATUS = get_status()
sleep(0.4)

# Token stuff
TOKEN = getenv("TOKEN")

if TOKEN:
    log("Found token!")
    separator()
else:
    log("Token not found.\nPlease follow setup instructions.")
    sysexit(1)