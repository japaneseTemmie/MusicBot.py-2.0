""" Extractor helper functions for discord.py bot """

from settings import EXTRACTOR_SEMAPHORE
from helpers.guildhelpers import update_query_extraction_state, update_guild_state
from webextractor import fetch, get_query_type
from error import Error

import asyncio
from discord.interactions import Interaction
from typing import Any

# Functions for fetching stuff from source websites
async def fetch_query(
        guild_states: dict[str, Any],
        interaction: Interaction,
        query: str,
        extraction_state_amount: int=1,
        extraction_state_max_length: int=1,
        query_name: str=None,
        allowed_query_types: tuple[str] | None=None,
        provider: str | None=None
    ) -> dict[str, Any] | list[dict[str, Any]] | Error:
    """ Extract a query from its website, catch any errors and return the result. """
    
    query = query.strip()

    if not query:
        return Error("Query cannot be empty.")

    query_type = get_query_type(query, provider)
    
    if allowed_query_types is not None and query_type.source_website not in allowed_query_types:
        return Error(f"Query type **{query_type.source_website}** not supported for this command!")

    await update_query_extraction_state(
        guild_states, 
        interaction, 
        extraction_state_amount, 
        extraction_state_max_length, 
        query_name.strip() if isinstance(query_name, str) else query,
        query_type.source_website
    )

    async with EXTRACTOR_SEMAPHORE:
        extracted_track = await asyncio.to_thread(fetch, query, query_type)

    return extracted_track

async def fetch_queries(
        guild_states: dict[str, Any],
        interaction: Interaction,
        queries: list[str] | list[dict[str, Any]],
        query_names: list[str] | None=None,
        allowed_query_types: tuple[str]=None,
        provider: str | None=None
    ) -> list[dict[str, Any]] | Error:
    """ Extract a list of queries and return the result. 
    
    `allowed_query_types` must be a tuple containing SourceWebsite enum values. 
    
    `provider` must be a SourceWebsite search website enum value. (if used) """

    found = []
    queries_length = len(queries)
    is_query_names_list = isinstance(query_names, list)

    if is_query_names_list and\
        queries_length != len(query_names):
        query_names = None

    await update_guild_state(guild_states, interaction, True, "can_extract")
    can_extract = guild_states[interaction.guild.id]["can_extract"]

    for i, query in enumerate(queries):
        can_extract = guild_states[interaction.guild.id]["can_extract"]
        if not can_extract:
            break

        extracted_query = await fetch_query(guild_states, interaction,
            query=query if not isinstance(query, dict) else query["webpage_url"],
            extraction_state_amount=i + 1,
            extraction_state_max_length=queries_length,
            query_name=query_names[i] if is_query_names_list else None,
            allowed_query_types=allowed_query_types,
            provider=provider
        )

        if isinstance(extracted_query, Error):
            return extracted_query
        elif isinstance(extracted_query, list):
            found.extend(extracted_query)
        else:
            found.append(extracted_query)
    
    if can_extract:
        await update_guild_state(guild_states, interaction, False, "can_extract")

    return found

async def resolve_expired_url(webpage_url: str) -> dict[str, Any] | None:
    """ Fetch a new track object based on the current webpage URL.
    
    Unlike `fetch()`, this function returns None on failure. """
    
    provider = None
    query_type = get_query_type(webpage_url, provider)
    
    async with EXTRACTOR_SEMAPHORE:
        new_extracted_track = await asyncio.to_thread(fetch, webpage_url, query_type, False) # Do not use caching as it will pull invalid data
    
    if isinstance(new_extracted_track, Error):
        return None
    
    return new_extracted_track

async def add_results_to_queue(interaction: Interaction, results: list[dict[str, Any]], queue: list, max_limit: int) -> list[dict[str, Any]]:
    """ Append found results to a queue in place.

    Reply to the interaction if it exceeds `max_limit` and stop operation.
    
    Return the added items. """
    
    added = []

    for track_info in results:
        if len(queue) >= max_limit:
            await interaction.channel.send(f"Maximum track limit of **{max_limit}** reached.\nCannot add more tracks.")
            break

        queue.append(track_info)
        added.append(track_info)

    return added
