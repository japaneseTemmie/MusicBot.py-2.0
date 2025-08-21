""" Helper functions for working with durations for discord.py bot. """

from settings import *

def add_zeroes(parts: list[str], length_limit: int):
    missing = length_limit - len(parts)
    
    for _ in range(missing):
        parts.insert(0, "00")

def format_to_minutes(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"

def format_to_seconds(minutes_str: str) -> int | None:
    try:
        parts = minutes_str.split(":")
        
        if len(parts) < 3:
            add_zeroes(parts, 3)
        
        for i, part in enumerate(parts):
            if int(part) > 59 and i > 0:
                return None
        
        hours, minutes, seconds = map(int, parts)
        return int(hours * 3600 + minutes * 60 + seconds)
    except Exception as e:

        if not isinstance(e, ValueError):
            log_to_discord_log(e)

        return None

def format_to_seconds_extended(minutes_str: str) -> int | None:
    try:
        parts = minutes_str.split(":")
        
        if len(parts) < 4:
            add_zeroes(parts, 4)

        for i, part in enumerate(parts):
            if (i < 1 and int(part) > 28) or\
                (i == 1 and int(part) > 23) or\
                (i > 1 and int(part) > 59):
                
                return None

        days, hours, minutes, seconds = map(int, parts)
        return int(days * 86400 + hours * 3600 + minutes * 60 + seconds)
    except Exception as e:
        if not isinstance(e, ValueError):
            log_to_discord_log(e)
            
        return None
