import aiofiles
from aiohttp import ClientResponse


async def save_aiohttp_response(
    response: ClientResponse, chunk_size: int = 1024, temp_dir: str = "/tmp"
) -> str:
    """
    Save aiohttp response to temp file.

    Args:
        response: ClientResponse
        chunk_size: int
        temp_dir: str

    Returns:
        str: path to temp file
    """
    async with aiofiles.tempfile.NamedTemporaryFile(
        "wb",
        delete=False,
        dir=temp_dir,
    ) as file:
        while True:
            chunk = await response.content.read(chunk_size)
            if not chunk:
                break

            await file.write(chunk)

        return str(file.name)
