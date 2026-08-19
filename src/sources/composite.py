import logging

from src.schema import Posting
from src.sources.base import Source

logger = logging.getLogger(__name__)


class CompositeSource:
    """Aggregates postings from multiple sources. A single source's fetch
    failure is logged and skipped, not raised -- one broken source should
    never suppress alerts from the others."""

    name = "composite"

    def __init__(self, sources: list[Source]):
        self._sources = sources

    def fetch(self) -> list[Posting]:
        postings: list[Posting] = []
        for source in self._sources:
            try:
                postings.extend(source.fetch())
            except Exception:
                logger.exception("source %s fetch failed; skipping", source.name)
        return postings
