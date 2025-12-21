""" Constants module for discord.py bot """

import discord
from logging import INFO, DEBUG, ERROR, WARNING, CRITICAL

VALID_LOG_LEVELS = {"normal": INFO, "verbose": DEBUG, "errors": ERROR, "warnings": WARNING, "critical": CRITICAL}
VALID_ACTIVITY_TYPES = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening}
VALID_STATUSES = {"online": discord.Status.online, "idle": discord.Status.idle, "do_not_disturb": discord.Status.do_not_disturb, "invisible": discord.Status.invisible}
PLAYBACK_END_GRACE_PERIOD = 1
STREAM_VALIDATION_TIMEOUT = 3
MAX_RETRY_COUNT = 3
CRASH_RECOVERY_TIME_WINDOW = 10
FFMPEG_RECONNECT_TIMEOUT_SECONDS = 10
FFMPEG_READ_WRITE_TIMEOUT_MILLIS = 7000000
IS_STREAM_URL_ALIVE_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}
MAX_IO_SYNC_WAIT_TIME = 20
MAX_GUILD_COUNT_BEFORE_SHARDING_REQUIRED = 2500
MAX_FETCH_CALLS = 50
RAW_FILTER_TO_VISUAL_TEXT = {
    "uploader": "Author",
    "min_duration": "Minimum duration",
    "max_duration": "Maximum duration",
    "source_website": "Website"
}
NEED_FORMATTING_FILTERS = ["min_duration", "max_duration"]