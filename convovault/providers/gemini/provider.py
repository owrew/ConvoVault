"""Gemini adapter shared by CLI and Studio."""
from ..portable import PortableProvider


class GeminiProvider(PortableProvider):
    provider_name = "gemini"
