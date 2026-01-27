""" Catgirl downloader module for discord.py bot """

from settings import CAN_LOG, LOGGER, NEKOS_MOE_CACHE
from init.constants import COOLDOWNS, NEKOS_MOE_RANDOM_ENDPOINT, NEKOS_MOE_IMAGE, NEKOS_MOE_REQUEST_HEADERS
from bot import Bot, ShardedBot
from error import Error
from init.logutils import log_to_discord_log
from helpers.httphelpers import get_json_response, get_bytes_response
from helpers.cachehelpers import get_cache, store_cache

import discord
from discord import app_commands
from discord.interactions import Interaction
from discord.ext import commands
from io import BytesIO
from typing import Any

class CatgirlDownloader(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
        self.client = client

    async def _get_image(self, image_id: str) -> discord.File | Error:
        """ Get an image from nekos.moe given an ID and return a discord.File object or Error on failure. """
        
        cache = get_cache(NEKOS_MOE_CACHE, image_id)

        if cache is not None:
            bytes_response_payload = cache
        else:
            bytes_response_payload = await get_bytes_response(self.client.client_http_session, NEKOS_MOE_IMAGE + f"/{image_id}", headers=NEKOS_MOE_REQUEST_HEADERS)
            
            if isinstance(bytes_response_payload, Error):
                return bytes_response_payload
            elif not bytes_response_payload.result:
                return Error("Received empty image.")
        
            store_cache(bytes_response_payload, image_id, NEKOS_MOE_CACHE)

        image_bytes = bytes_response_payload.result
        content_type = bytes_response_payload.response.content_type or "image/jpeg"
        image_extension = content_type.split("/")[-1]

        return discord.File(BytesIO(image_bytes), f"{image_id}.{image_extension}")

    async def _get_image_metadata(self, url: str) -> dict[str, Any] | Error:
        """ Get image metadata from a valid nekos.moe API URL. """
        
        json_response_payload = await get_json_response(self.client.client_http_session, url, headers=NEKOS_MOE_REQUEST_HEADERS)
        if isinstance(json_response_payload, Error):
            return json_response_payload
        
        return json_response_payload.result

    @app_commands.command(name="get-catgirl", description="Shows a random, SFW-ONLY picture of a catgirl provided by nekos.moe")
    @app_commands.describe(
        private="Whether or not the response should be hidden from others. (default True)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["GET_CATGIRL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    async def show_random_catgirl(self, interaction: Interaction, private: bool=True):
        await interaction.response.defer(ephemeral=private)

        data = await self._get_image_metadata(NEKOS_MOE_RANDOM_ENDPOINT + "?nsfw=false")
        if isinstance(data, Error):
            await interaction.followup.send(data.msg)
            return

        image_data = data["images"][0]

        image_id = image_data["id"]
        image_artist = image_data.get("artist") or "Unknown artist" # API specs says this is not guaranteed

        file = await self._get_image(image_id)
        if isinstance(file, Error):
            await interaction.followup.send(file.msg)
            return
        
        await interaction.followup.send(f"Credit: **{image_artist}**", file=file)

    @show_random_catgirl.error
    async def handle_show_random_catgirl_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred")
