from colors import Colors, all_colors
from datetime import datetime
from random import choice
from logging import Logger

def log(msg: str) -> None:
    """ Log `msg` to stdout. """
    
    print(f"{choice(all_colors)}[main]{Colors.RESET} | {choice(all_colors)}{datetime.now().strftime('%d/%m/%Y @ %H:%M:%S')}{Colors.RESET} | {choice(all_colors)}{msg}{Colors.RESET}")

def separator(s: str="=", length: int=35) -> None:
    print("".join([choice(all_colors) + s + Colors.RESET for _ in range(length)]))

def log_to_discord_log(
        msg_or_exception: str | Exception, 
        log_type: str="info",
        can_log: bool=False,
        logger: Logger | None=None
    ) -> bool:
    
    if can_log and logger is not None:
        if isinstance(msg_or_exception, Exception):
            logger.exception(msg_or_exception)
            
            return True
        
        log_funcs = {
            "warning": logger.warning,
            "error": logger.error,
            "info": logger.info,
            "debug": logger.debug
        }

        func = log_funcs.get(log_type, logger.info)
        func(msg_or_exception)

        return True
    
    return False