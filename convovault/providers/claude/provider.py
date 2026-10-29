"""Claude adapter shared by CLI and Studio."""
from ..portable import PortableProvider


class ClaudeProvider(PortableProvider):
    provider_name = "claude"
