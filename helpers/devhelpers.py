from init.logutils import log

from bot import Bot, ShardedBot
from time import monotonic

async def reload_cogs(original_cogs: list[str], client: Bot | ShardedBot) -> int:
    """ Reloads `client`'s cogs.
     
    Returns time taken for reload in seconds. """
    
    start_time = monotonic()

    log("===== RELOADING COGS =====")

    for name in original_cogs:
        await client.remove_cog(name)

    await client.load_cogs()
    await client.sync_commands()

    return round(monotonic() - start_time, 2)