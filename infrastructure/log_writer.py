from .async_file_handler import AsyncFileHandler


class LogWriter(AsyncFileHandler):
    """Session log writer: every line goes to both the console and the
    per-session log file on disk (report section 0.18.3/0.27.9 -- the
    real-time terminal trace plus a persisted, browsable log per run).
    This is the one deliberate `print` left in the codebase.
    """

    def __init__(self, file_name: str):
        super().__init__(file_name)

    async def create_log_file(self) -> None:
        await super().create_file()

    async def write_log(self, log: str) -> None:
        print(log)  # console sink
        await super().write_line(log + "\n")  # file sink

    async def close_file(self) -> None:
        await super().close_file()
