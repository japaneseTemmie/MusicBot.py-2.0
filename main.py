""" main.py script for discord.py bot """

from settings import COMMAND_PREFIX, ACTIVITY, INTENTS, TOKEN, HANDLER, FORMATTER, LOG_LEVEL, USE_SHARDING
from init.logutils import log, separator
from bot import Bot, ShardedBot

from discord.errors import PrivilegedIntentsRequired, LoginFailure

def main() -> None:
    """ Main entry point. The greatest journey begins here. (assuming it starts :3) 
    
    Handles construction of the custom `Bot` object and runs it. """

    bot = Bot(COMMAND_PREFIX, activity=ACTIVITY, intents=INTENTS) if not USE_SHARDING else\
    ShardedBot(COMMAND_PREFIX, activity=ACTIVITY, intents=INTENTS)
    
    try:
        bot.run(TOKEN, log_handler=HANDLER, log_formatter=FORMATTER, log_level=LOG_LEVEL)
    except PrivilegedIntentsRequired:
        log("Failed to request intents. Ensure all Priviliged Gateway Intents are enabled.")
    except LoginFailure:
        log("Failed to log in Discord. Ensure the provided token in the .env file is valid.")

if __name__ == "__main__":
    log(f"Running main()")
    separator()
    main()