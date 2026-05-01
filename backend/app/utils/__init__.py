"""
Utilities Module
"""

from .file_parser import FileParser

__all__ = ['FileParser', 'LLMClient']


def __getattr__(name):
    if name == 'LLMClient':
        from .llm_client import LLMClient
        return LLMClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
