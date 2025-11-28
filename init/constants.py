""" Constants module for discord.py bot """

import discord
from logging import INFO, DEBUG, ERROR, WARNING, CRITICAL

VALID_LOG_LEVELS = {"normal": INFO, "verbose": DEBUG, "errors": ERROR, "warnings": WARNING, "critical": CRITICAL}
VALID_ACTIVITY_TYPES = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening}
VALID_STATUSES = {"online": discord.Status.online, "idle": discord.Status.idle, "do_not_disturb": discord.Status.do_not_disturb, "invisible": discord.Status.invisible}
PLAYBACK_END_GRACE_PERIOD = 1
STREAM_VALIDATION_TIMEOUT = 3
MAX_IO_SYNC_WAIT_TIME = 20000
MAX_GUILD_COUNT_BEFORE_SHARDING_REQUIRED = 2500
MAX_FETCH_CALLS = 35
RAW_FILTER_TO_VISUAL_TEXT = {
    "uploader": "Author",
    "min_duration": "Minimum duration",
    "max_duration": "Maximum duration",
    "source_website": "Website"
}
NEED_FORMATTING_FILTERS = ["min_duration", "max_duration"]