""" Generic async HTTP helpers for discord.py bot """

from error import Error

from asyncio import TimeoutError
from aiohttp import ClientSession, ClientResponse
from aiohttp.client_exceptions import ContentTypeError, ClientError
from json import JSONDecodeError
from typing import Any

class ResponsePayload:
    """ Generic response payload. 
    
    Contains response itself (only for read-only metadata) and requested result. """

    def __init__(self, response: ClientResponse, result: Any):
        self.response = response
        self.result = result

async def get_json_response(session: ClientSession, url: str, **kwargs) -> ResponsePayload | Error:
    """ GET the url and return a JSON response. 
    
    Return a ResponsePayload with hashmap containing the jsonified response as `result` or Error on failure. """

    try:
        async with session.get(url, **kwargs) as response:
            if response.status != 200:
                return Error(f"Unable to process request, got HTTP **{response.status}**.")
            
            return ResponsePayload(response, await response.json())
    except ContentTypeError:
        return Error(f"Unable to process request due to unexpected MIME type.")
    except TimeoutError:
        return Error(f"Unable to process request due to timeout error.")
    except (JSONDecodeError, ClientError):
        return Error(f"Unable to process request. Failed to decode response.")

async def get_bytes_response(session: ClientSession, url: str, **kwargs) -> ResponsePayload | Error:
    """ GET the url and return its content as bytes. 
    
    Return ResponsePayload with response content as bytes as `result` or Error on failure. """

    try:
        async with session.get(url, **kwargs) as response:
            if response.status != 200:
                return Error(f"Unable to process request, got HTTP **{response.status}**.")
            
            return ResponsePayload(response, await response.content.read())
    except TimeoutError:
        return Error(f"Unable to process request due to timeout error.")
    except ClientError:
        return Error(f"Unable to process request. Failed to read response.")