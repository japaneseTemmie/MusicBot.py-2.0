""" Catgirl downloader module for discord.py bot """

from settings import CAN_LOG, LOGGER
from init.constants import COOLDOWNS, NEKOS_MOE_RANDOM_ENDPOINT, NEKOS_MOE_IMAGE, NEKOS_MOE_REQUEST_HEADERS
from bot import Bot, ShardedBot
from error import Error
from init.logutils import log_to_discord_log
from helpers.httphelpers import get_json_response, get_bytes_response

import discord
from discord import app_commands
from discord.interactions import Interaction
from discord.ext import commands
from io import BytesIO

class CatgirlDownloader(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
        self.client = client

    @app_commands.command(name="get-catgirl", description="Shows a random, SFW-ONLY picture of a catgirl provided by nekos.moe")
    @app_commands.describe(
        private="Whether or not the response should be hidden from others. (default True)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["GET_CATGIRL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    async def show_random_catgirl(self, interaction: Interaction, private: bool=True):
        await interaction.response.defer(ephemeral=private)

        json_response_payload = await get_json_response(self.client.client_http_session, NEKOS_MOE_RANDOM_ENDPOINT + "?nsfw=false", headers=NEKOS_MOE_REQUEST_HEADERS)
        if isinstance(json_response_payload, Error):
            await interaction.followup.send(json_response_payload.msg)
            return
        
        data = json_response_payload.result
        
        image_data = data["images"][0]

        image_id = image_data["id"]
        image_artist = image_data.get("artist") or "Not provided" # API specs says this is not guaranteed

        bytes_response_payload = await get_bytes_response(self.client.client_http_session, NEKOS_MOE_IMAGE + f"/{image_id}", headers=NEKOS_MOE_REQUEST_HEADERS)
        if isinstance(bytes_response_payload, Error):
            await interaction.followup.send(bytes_response_payload.msg)
            return
        
        image_bytes = bytes_response_payload.result

        if not image_bytes:
            await interaction.followup.send("Received empty image.")
            return
        
        image_extension = bytes_response_payload.response.content_type.split("/")[-1]

        file = discord.File(BytesIO(image_bytes), f"{image_id}.{image_extension}")
        
        await interaction.followup.send(f"Credit: **{image_artist}**", file=file)

    @show_random_catgirl.error
    async def handle_show_random_catgirl_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred")