from .async_file_handler import AsyncFileHandler


class LogWriter(AsyncFileHandler):
    """Session log writer: every line goes to both the console and the
    per-session log file on disk (report section 0.18.3/0.27.9 -- the
    real-time terminal trace plus a persisted, browsable log per run).
    """

    async def create_log_file(self) -> None:
        await super().create_file()

    async def write_log(self, log: str) -> None:
        print(log)  # console sink
        await super().write_line(log + "\n")  # file sink
