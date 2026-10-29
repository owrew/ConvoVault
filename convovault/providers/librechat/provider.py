"""LibreChat adapter shared by CLI and Studio."""
from ..portable import PortableProvider


class LibreChatProvider(PortableProvider):
    provider_name = "librechat"
