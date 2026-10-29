"""Error types that map onto the CLI exit codes."""


class ConfigError(Exception):
    """Invalid config or CLI arguments. Exit code 2."""

    def __init__(self, messages):
        if isinstance(messages, str):
            messages = [messages]
        self.messages = [str(item) for item in messages if str(item)]
        super().__init__("\n".join(self.messages))


class LogError(Exception):
    """A log path could not be read, or the file is not JSONL or CSV. Exit code 1."""

    def __init__(self, messages):
        if isinstance(messages, str):
            messages = [messages]
        self.messages = [str(item) for item in messages if str(item)]
        super().__init__("\n".join(self.messages))
