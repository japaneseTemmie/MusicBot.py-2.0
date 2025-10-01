""" Helper functions for working with durations for discord.py bot. """

from settings import CAN_LOG, LOGGER
from init.logutils import log_to_discord_log

def add_zeroes(parts: list[str], length_limit: int):
    missing = length_limit - len(parts)
    
    for _ in range(missing):
        parts.insert(0, "00")

def format_to_minutes(seconds: int) -> str | None:
    """ Format `seconds` into a HH:MM:SS string. Returns None if `seconds` is None. """
    
    if seconds is None:
        return None

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"

def format_to_seconds(minutes_str: str) -> int | None:
    """ Format a HH:MM:SS `minutes_str` into seconds. Returns None if `minutes_str` is None. """
    
    try:
        if minutes_str is None:
            return None

        parts = minutes_str.split(":")
        
        if len(parts) < 3:
            add_zeroes(parts, 3)
        
        for i, part in enumerate(parts):
            if int(part) < 0 or (int(part) > 59 and i > 0):
                return None
        
        hours, minutes, seconds = map(int, parts)
        return int(hours * 3600 + minutes * 60 + seconds)
    except ValueError:
        return None
    except Exception as e:
        log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER)
        return None

def format_to_seconds_extended(minutes_str: str) -> int | None:
    """ Format a DD:HH:MM:SS `minutes_str` into seconds. Returns None if `minutes_str` is None. """
    
    if minutes_str is None:
        return None

    try:
        parts = minutes_str.split(":")
        
        if len(parts) < 4:
            add_zeroes(parts, 4)

        for i, part in enumerate(parts):
            if (i < 1 and int(part) > 28) or\
                (i == 1 and int(part) > 23) or\
                (i > 1 and int(part) > 59) or\
                int(part) < 0:
                
                return None

        days, hours, minutes, seconds = map(int, parts)
        return int(days * 86400 + hours * 3600 + minutes * 60 + seconds)
    except ValueError:
        return None
    except Exception as e:
        log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER)
        return None
