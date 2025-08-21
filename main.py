""" main.py script for discord.py bot """

from settings import *
from bot import Bot

def main() -> None:
    """ Main entry point. The greatest journey begins here. (assuming it starts :3) 
    Handles construction of the custom `Bot` object and runs it. """

    bot = Bot(COMMAND_PREFIX, activity=ACTIVITY, intents=INTENTS)
    
    try:
        bot.run(TOKEN, log_handler=HANDLER, log_formatter=FORMATTER, log_level=VALID_LOG_LEVELS.get(LEVEL, INFO))
    except discord.errors.PrivilegedIntentsRequired:
        log("Failed to request intents. Ensure all Priviliged Gateway Intents are enabled.")
    except discord.errors.LoginFailure:
        log("Failed to log in to Discord. Ensure the provided token in the .env file is valid.")

if __name__ == "__main__":
    log(f"Running main()")
    separator()
    main()