""" General settings configuration for discord.py bot """

from init.info import get_current_directory, get_python, get_os, get_activity, get_activity_data, get_status, handle_ffmpeg_path_output
from init.config import get_config_data, get_default_yt_dlp_config_data
from init.help import open_help_file
from init.loghelpers import set_up_logging, remove_log
from init.logutils import log, separator

import asyncio
import discord
from discord import Intents
from cachetools import TTLCache
from os import getenv
from sys import exit as sysexit
from time import sleep
from shutil import which
from dotenv import load_dotenv

log("Finished importing libraries")
separator()
log(f"Running discord.py version {discord.__version__}")
separator()
sleep(0.5)

# System info and config
PATH = get_current_directory(__file__)
PYTHON = get_python()
SYSTEM = get_os()
CONFIG = get_config_data(PATH)
load_dotenv()
sleep(0.2)

# Define config vars as constants
CAN_LOG = CONFIG.get("enable_logging", True)
YDL_OPTIONS = CONFIG.get("yt_dlp_options", get_default_yt_dlp_config_data())
COMMAND_PREFIX = CONFIG.get("command_prefix", "?")
USE_SHARDING = CONFIG.get("use_sharding", False)
ENABLE_FILE_BACKUPS = CONFIG.get("enable_file_backups", True)
HELP = open_help_file(PATH)
COOLDOWNS = {
    "PING_COMMAND_COOLDOWN": 5.0,
    "HELP_COMMAND_COOLDOWN": 5.0,
    "MUSIC_COMMANDS_COOLDOWN": 10.0,
    "EXTRACTOR_MUSIC_COMMANDS_COOLDOWN": 30.0,
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
    "MOVE_USER_COMMAND_COOLDOWN": 10.0,
    "VC_KICK_COMMAND_COOLDOWN": 10.0,
    "VC_MUTE_COMMAND_COOLDOWN": 10.0
}

# Logging
# Set up file handler and formatter for discord.py's logging lib, if requested.
HANDLER, FORMATTER, LOGGER, LEVEL = set_up_logging(PATH, CONFIG) if CAN_LOG else remove_log(PATH)

FFMPEG = which("ffmpeg")
handle_ffmpeg_path_output(SYSTEM, FFMPEG)

# Cache
# Set up hashmaps for asyncio locks and cache
PLAYLIST_LOCKS = {}
ROLE_LOCKS = {}
ROLE_FILE_CACHE = TTLCache(maxsize=16384, ttl=3600)
PLAYLIST_FILE_CACHE = TTLCache(maxsize=16384, ttl=3600)

# Event objects that function as locks for safe shutdown.
# Use .clear() to release the lock.
# Use .set() to acquire the lock and refuse any VoiceClient or I/O operation.
# Use .wait() to block the event loop if a lock is acquired (should be used rarely).
# Use .is_set() to check if a lock is acquired (True) or not (False). Refuse operation if True. """
FILE_OPERATIONS_LOCKED = asyncio.Event()
VOICE_OPERATIONS_LOCKED = asyncio.Event()

# API stuff
ACTIVITY_ENABLED, STATUS_TYPE, ACTIVITY_NAME, ACTIVITY_TYPE = get_activity_data(CONFIG)

INTENTS = Intents.all()
ACTIVITY = get_activity(ACTIVITY_ENABLED, ACTIVITY_NAME, ACTIVITY_TYPE)
STATUS = get_status(STATUS_TYPE)
sleep(0.4)

# Token stuff
TOKEN = getenv("TOKEN")

if TOKEN:
    log("Found token!")
    separator()
else:
    log("Token not found.\nPlease follow setup instructions.")
    sysexit(1)