"""Scrapers para a Câmara dos Deputados."""

from .parliamentarian import parliamentarian
from .proposition import proposition
from .agency import agency


def speeches_transcripts(*args, **kwargs):
    """Import lazily to avoid runpy warning when executing this module with -m."""
    from .speeches_transcripts import speeches_transcripts as _speeches_transcripts

    return _speeches_transcripts(*args, **kwargs)

__all__ = ["parliamentarian", "proposition", "agency", "speeches_transcripts"]