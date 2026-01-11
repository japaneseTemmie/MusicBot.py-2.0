""" General settings configuration for discord.py bot """

from init.info import get_directory, get_python, get_os, get_activity, get_activity_data, get_status, handle_which_ff_output
from init.help import open_help_file
from init.config import get_config_data
from init.loghelpers import set_up_logging, remove_log
from init.logutils import log, separator
from init.constants import MAX_FETCH_CALLS, VALID_LOG_LEVELS
from helpers.confighelpers import ConfigCategory, get_config_value, correct_type, get_default_yt_dlp_config_data

import asyncio
import discord
from discord import Intents
from cachetools import TTLCache
from logging import INFO
from os import getenv
from sys import exit as sysexit
from time import sleep
from shutil import which
from dotenv import load_dotenv

log(f"Running discord.py version {discord.__version__}")
separator()
sleep(0.5)

# System info and config
PATH = get_directory(__file__)
log(f"Working directory: {PATH}")
separator()

PYTHON_IMPLEMENTATION, PYTHON_VERSION = get_python()
log(f"Running in {PYTHON_IMPLEMENTATION} version {PYTHON_VERSION}")
separator()

OS_PRETTY_NAME, OS_NAME, KERNEL_VERSION = get_os()
log(f"OS: {OS_NAME}, Pretty name: {OS_PRETTY_NAME}")
log(f"Kernel: {OS_PRETTY_NAME + ' ' + KERNEL_VERSION if KERNEL_VERSION is not None else 'Unknown'}")
separator()

CONFIG = get_config_data(PATH)
if CONFIG is None:
    sysexit(1)
load_dotenv()
sleep(0.2)

# Define config constants
CAN_LOG = correct_type(get_config_value(CONFIG, "can_log", ConfigCategory.OTHER), bool, True)
YDL_OPTIONS = correct_type(get_config_value(CONFIG, ConfigCategory.YT_DLP.value), dict, get_default_yt_dlp_config_data())
COMMAND_PREFIX = correct_type(get_config_value(CONFIG, "command_prefix", ConfigCategory.OTHER), str, "?")
USE_SHARDING = correct_type(get_config_value(CONFIG, "use_sharding", ConfigCategory.OTHER), bool, False)
ENABLE_FILE_BACKUPS = correct_type(get_config_value(CONFIG, "enable_file_backups", ConfigCategory.OTHER), bool, True)
CAN_AUTO_DELETE_GUILD_DATA = correct_type(get_config_value(CONFIG, "auto_delete_unused_guild_data", ConfigCategory.OTHER), bool, True)

MAX_QUEUE_TRACK_LIMIT = correct_type(get_config_value(CONFIG, "max_queue_track_limit", ConfigCategory.LIMITS), int, 100)
MAX_TRACK_HISTORY_LIMIT = correct_type(get_config_value(CONFIG, "max_history_track_limit", ConfigCategory.LIMITS), int, 200)
MAX_QUERY_LIMIT = correct_type(get_config_value(CONFIG, "max_query_limit", ConfigCategory.LIMITS), int, 25)
MAX_PLAYLIST_LIMIT = correct_type(get_config_value(CONFIG, "max_playlist_limit", ConfigCategory.LIMITS), int, 10)
MAX_PLAYLIST_TRACK_LIMIT = correct_type(get_config_value(CONFIG, "max_playlist_track_limit", ConfigCategory.LIMITS), int, 100)
MAX_ITEM_NAME_LENGTH = correct_type(get_config_value(CONFIG, "max_name_length", ConfigCategory.LIMITS), int, 50)

HELP = open_help_file(PATH)

# Logging
# Set up file handler and formatter for discord.py's logging lib, if requested.
HANDLER, FORMATTER, LOGGER, LEVEL = set_up_logging(PATH, CONFIG) if CAN_LOG else remove_log(PATH)
LOG_LEVEL = VALID_LOG_LEVELS.get(LEVEL, INFO)

# FFmpeg validation
FFMPEG = which("ffmpeg")
if not handle_which_ff_output(OS_NAME, FFMPEG):
    sysexit(1)

# Cache
# Set up hashmaps for asyncio locks and cache
PLAYLIST_LOCKS = {}
ROLE_LOCKS = {}
ROLE_FILE_CACHE = TTLCache(maxsize=16384, ttl=3600)
PLAYLIST_FILE_CACHE = TTLCache(maxsize=16384, ttl=3600)
EXTRACTOR_CACHE = TTLCache(maxsize=16384, ttl=600)

# Global locks
FILE_OPERATIONS_LOCKED = asyncio.Event()
VOICE_OPERATIONS_LOCKED = asyncio.Event()

# asyncio Semaphore for extractor.
EXTRACTOR_SEMAPHORE = asyncio.Semaphore(MAX_FETCH_CALLS)

# API stuff
ACTIVITY_DATA = get_activity_data(CONFIG)
if not ACTIVITY_DATA["activity_enabled"]:
    log("Activity disabled")
else:
    log("Activity enabled")
separator()

INTENTS = Intents.all()
INTENTS.presences = False
INTENTS.guild_typing = False
INTENTS.dm_typing = False

ACTIVITY = get_activity(ACTIVITY_DATA)
STATUS = get_status(ACTIVITY_DATA["status_type"])
sleep(0.4)

# Token stuff
TOKEN = getenv("TOKEN")

if TOKEN:
    log("Found token!")
    separator()
else:
    log("Token not found.\nPlease follow setup instructions.")
    sysexit(1)