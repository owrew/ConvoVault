"""ChatGPT adapter shared by CLI and Studio."""
from ..portable import PortableProvider


class ChatGPTProvider(PortableProvider):
    provider_name = "chatgpt"
