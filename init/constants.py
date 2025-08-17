import discord
from logging import INFO, DEBUG, ERROR, WARNING, CRITICAL

VALID_LOG_LEVELS = {"normal": INFO, "verbose": DEBUG, "errors": ERROR, "warnings": WARNING, "critical": CRITICAL}
VALID_ACTIVITY_TYPES = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening}
VALID_STATUSES = {"online": discord.Status.online, "idle": discord.Status.idle, "do_not_disturb": discord.Status.do_not_disturb, "invisible": discord.Status.invisible}
PLAYBACK_END_GRACE_PERIOD = 1