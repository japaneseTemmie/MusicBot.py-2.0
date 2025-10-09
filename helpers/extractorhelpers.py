""" Helper functions for discord.py bot """

from settings import EXTRACTOR_SEMAPHORE
from helpers.guildhelpers import update_query_extraction_state
from extractor import fetch, get_query_type
from error import Error

import asyncio
from discord.interactions import Interaction

# Functions for fetching stuff from source websites
async def fetch_query(
        guild_states: dict,
        interaction: Interaction,
        query: str,
        extraction_state_amount: int=1,
        extraction_state_max_length: int=1,
        query_name: str=None,
        allowed_query_types: tuple[str] | None=None,
        provider: str | None=None
    ) -> dict | list[dict] | Error:
    """ Extract a query from its website, catch any errors and return the result. """
    
    query = query.strip()

    if not query:
        return Error("Query cannot be empty.")

    await update_query_extraction_state(guild_states, interaction, extraction_state_amount, extraction_state_max_length, query_name.strip() if query_name is not None else query)

    query_type = get_query_type(query, provider)
    source_website = query_type[1]
    
    if allowed_query_types is not None and source_website not in allowed_query_types:
        return Error(f"Query type **{source_website}** not supported for this command!")

    async with EXTRACTOR_SEMAPHORE:
        extracted_track = await asyncio.to_thread(fetch, query, query_type)

    return extracted_track

async def fetch_queries(guild_states: dict,
        interaction: Interaction,
        queries: list[str | dict],
        query_names: list[str]=None,
        allowed_query_types: tuple[str]=None,
        provider: str | None=None
    ) -> list[dict | list[dict]] | Error:
    """ Extract a list of queries using the fetch_query() function. """
    
    found = []
    for i, query in enumerate(queries):
        extracted_query = await fetch_query(guild_states, interaction,
            query=query if not isinstance(query, dict) else query["webpage_url"],
            extraction_state_amount=i + 1,
            extraction_state_max_length=len(queries),
            query_name=query_names[i] if isinstance(query_names, list) else query_names,
            allowed_query_types=allowed_query_types,
            provider=provider
        )

        if isinstance(extracted_query, Error):
            return extracted_query
        elif isinstance(extracted_query, list):
            found.extend(extracted_query)
        else:
            found.append(extracted_query)
    
    return found

async def resolve_expired_url(webpage_url: str) -> dict | None:
    """ Fetch a new track object based on the current webpage URL.
    Unlike `fetch()`, this function returns None on failure. """
    
    provider = None
    query_type = get_query_type(webpage_url, provider)
    
    async with EXTRACTOR_SEMAPHORE:
        new_extracted_track = await asyncio.to_thread(fetch, webpage_url, query_type) # Can't use the wrapper fetch_query() here because we can't update the extraction state visible to users.
    
    if isinstance(new_extracted_track, Error):
        return None
    
    return new_extracted_track

async def add_results_to_queue(interaction: Interaction, results: list[dict], queue: list, max_limit: int) -> list[dict]:
    """ Append found results to a queue in place.\n
    Reply to the interaction if it exceeds `max_limit`.
    Return the added items. """
    added = []

    for track_info in results:
        if len(queue) >= max_limit:
            await interaction.channel.send(f"Maximum track limit of **{max_limit}** reached.\nCannot add more tracks.")
            break

        queue.append(track_info)
        added.append(track_info)

    return added
