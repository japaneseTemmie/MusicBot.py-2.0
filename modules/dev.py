from settings import CAN_LOG, LOGGER, COOLDOWNS, VOICE_OPERATIONS_LOCKED, FILE_OPERATIONS_LOCKED
from init.logutils import log, log_to_discord_log
from helpers.devhelpers import reload_cogs
from bot import Bot, ShardedBot

import asyncio
from discord.ext import commands
from time import monotonic

class DevCog(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
        self.client = client
        
        self.guild_states = self.client.guild_states
        self.original_cogs = []

        self.reloading_cogs = False

    @commands.command("reload-cogs")
    @commands.cooldown(rate=1, per=COOLDOWNS["DEV_COMMAND_COOLDOWN"], type=commands.BucketType.user)
    @commands.guild_only()
    async def reload_cogs(self, ctx: commands.Context):
        if not await self.client.is_owner(ctx.author) or\
            self.reloading_cogs or\
            not self.client.has_finished_on_ready:
            return
        
        if not self.original_cogs:
            self.original_cogs = list(self.client.cogs)

        async with ctx.typing():
            self.reloading_cogs = True
            VOICE_OPERATIONS_LOCKED.set()
            FILE_OPERATIONS_LOCKED.set()

            time_taken = await reload_cogs(self.original_cogs, self.client)

            await asyncio.sleep(10)

            self.reloading_cogs = False
            VOICE_OPERATIONS_LOCKED.clear()
            FILE_OPERATIONS_LOCKED.clear()

            current_cog_names = list(self.client.cogs)
            
            await ctx.send(
                f"Reloaded **{len(current_cog_names)}** out of **{len(self.original_cogs)}** cogs in **{time_taken}**s\n"+
                f"Currently active cogs:\n{"".join([f"- **{name}**\n" for name in current_cog_names])}"+
                "Check logs for more accurate report."
            )

    @reload_cogs.error
    async def handle_reload_cogs_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.NoPrivateMessage):
            return
        elif isinstance(error, commands.CommandOnCooldown):
            if await self.client.is_owner(ctx.author):
                await ctx.send(str(error))

            return

        log("An error occurred while reloading cogs")
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        await ctx.send("An unknown error occurred, check logs.")