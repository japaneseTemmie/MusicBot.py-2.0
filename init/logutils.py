""" Logging utilities module for discord.py bot """

from colors import Colors, all_colors

from datetime import datetime
from random import choice
from logging import Logger

def log(msg: str, log_type: str="main") -> None:
    """ Log `msg` to stdout. """
    
    print(f"{choice(all_colors)}[{log_type}]{Colors.RESET} | {choice(all_colors)}{datetime.now().strftime('%d/%m/%Y @ %H:%M:%S')}{Colors.RESET} | {choice(all_colors)}{msg}{Colors.RESET}")

def separator(s: str="=", length: int=35) -> None:
    print("".join([choice(all_colors) + s + Colors.RESET for _ in range(length)]))

def log_to_discord_log(
        content: str | Exception, 
        log_type: str="info",
        can_log: bool=False,
        logger: Logger | None=None
    ) -> bool:

    """
    Log a message or exception to `discord.log` file if logging is enabled.
    
    When `content` is an exception, it is logged directly.
    
    When `log_type` is specified (either 'warning', 'error', 'info', or 'debug') and `content` is a string. The message will be logged as `log_type`.

    Return value indicates log success.
    """

    if can_log and logger is not None:
        if isinstance(content, Exception):
            logger.exception(content)
            
            return True
        
        log_funcs = {
            "warning": logger.warning,
            "error": logger.error,
            "info": logger.info,
            "debug": logger.debug
        }

        func = log_funcs.get(log_type, logger.info)
        func(content)

        return True
    
    return False