""" main.py script for discord.py bot """

from settings import COMMAND_PREFIX, ACTIVITY, INTENTS, TOKEN, HANDLER, FORMATTER, LEVEL
from init.constants import VALID_LOG_LEVELS
from init.logutils import log, separator
from bot import Bot

from discord.errors import PrivilegedIntentsRequired, LoginFailure
from logging import INFO

def main() -> None:
    """ Main entry point. The greatest journey begins here. (assuming it starts :3) 
    Handles construction of the custom `Bot` object and runs it. """

    bot = Bot(COMMAND_PREFIX, activity=ACTIVITY, intents=INTENTS)
    
    try:
        bot.run(TOKEN, log_handler=HANDLER, log_formatter=FORMATTER, log_level=VALID_LOG_LEVELS.get(LEVEL, INFO))
    except PrivilegedIntentsRequired:
        log("Failed to request intents. Ensure all Priviliged Gateway Intents are enabled.")
    except LoginFailure:
        log("Failed to log in to Discord. Ensure the provided token in the .env file is valid.")

if __name__ == "__main__":
    log(f"Running main()")
    separator()
    main()