import aiofiles


class AsyncFileHandler:
    """Thin async wrapper around a single append-mode text file."""

    def __init__(self, file_name: str):
        self.file_name = file_name

    async def create_file(self) -> None:
        self.file = await aiofiles.open(self.file_name, mode="w")

    async def write_line(self, data: str) -> None:
        text = str(data)
        await self.file.write(text + "\n")
        await self.file.flush()

    async def close_file(self) -> None:
        if hasattr(self, "file"):
            await self.file.close()
