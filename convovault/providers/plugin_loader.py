"""
plugin_loader.py
================
Dynamic provider registration and entrypoint loader for ConvoVault.
"""
from __future__ import annotations
import logging
from typing import Dict, Type, List, Optional
from .base import BaseProvider


# Import built-in providers
from .antigravity import AntigravityProvider
from .chatgpt import ChatGPTProvider
from .claude import ClaudeProvider
from .openwebui import OpenWebUIProvider
from .ollama import OllamaProvider
from .gemini import GeminiProvider
from .librechat import LibreChatProvider

log = logging.getLogger(__name__)

# Registry of built-in providers
_PROVIDERS: Dict[str, Type[BaseProvider]] = {
    "antigravity": AntigravityProvider,
    "chatgpt": ChatGPTProvider,
    "claude": ClaudeProvider,
    "openwebui": OpenWebUIProvider,
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
    "librechat": LibreChatProvider,
}

def get_provider(name: str) -> Optional[BaseProvider]:
    """
    Resolve and instantiate a provider by name.
    First checks built-ins, then scans python entry_points.
    """
    name_lower = name.lower()
    
    # 1. Built-in check
    if name_lower in _PROVIDERS:
        return _PROVIDERS[name_lower]()

    # 2. Entrypoint check (third-party plugins)
    try:
        import sys
        if sys.version_info >= (3, 8):
            from importlib.metadata import entry_points
            eps = entry_points()
            # In Python 3.10+, entry_points() returns an EntryPoints object that can be queried by group
            # In older versions it returns a dict. We handle both.
            if hasattr(eps, 'select'):
                group_eps = eps.select(group='convovault.providers')
            else:
                group_eps = eps.get('convovault.providers', [])
                
            for ep in group_eps:
                if ep.name == name_lower:
                    provider_cls = ep.load()
                    return provider_cls()
    except Exception as e:
        log.debug("Error loading entrypoint providers: %s", e)

    return None

def register_provider(name: str, provider_cls: Type[BaseProvider]):
    """Allow programmatically registering custom providers."""
    _PROVIDERS[name.lower()] = provider_cls

def list_providers() -> List[str]:
    """List all registered provider names."""
    names = list(_PROVIDERS.keys())
    # Add external plugins
    try:
        import sys
        if sys.version_info >= (3, 8):
            from importlib.metadata import entry_points
            eps = entry_points()
            if hasattr(eps, 'select'):
                group_eps = eps.select(group='convovault.providers')
            else:
                group_eps = eps.get('convovault.providers', [])
            for ep in group_eps:
                if ep.name not in names:
                    names.append(ep.name)
    except Exception:
        pass
    return sorted(names)
