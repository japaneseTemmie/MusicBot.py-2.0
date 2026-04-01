""" Generic async HTTP helpers for discord.py bot """

from error import Error

from asyncio import TimeoutError
from aiohttp import ClientSession, ClientResponse
from aiohttp.client_exceptions import ContentTypeError, ClientError
from json import JSONDecodeError
from typing import Any

class ResponsePayload:
    """ Generic response payload with additional read-only response attributes and the cached result. """

    def __init__(self, response: ClientResponse, result: Any):
        self.content_type = response.content_type
        self.content_length = response.content_length
        self.charset = response.charset
        self.content_disposition = response.content_disposition
        self.cookies = response.cookies
        self.headers = response.headers
        self.status = response.status
        self.result = result

async def http_get_json(session: ClientSession, url: str, **kwargs) -> ResponsePayload | Error:
    """ Make an HTTP GET request the given endpoint and return a JSON response. 
    
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

async def http_get_bytes(session: ClientSession, url: str, **kwargs) -> ResponsePayload | Error:
    """ Make an HTTP GET request to the given endpoint and return its content as bytes. 
    
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