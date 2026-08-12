from typing import Protocol

from src.schema import Posting


class Source(Protocol):
    name: str

    def fetch(self) -> list[Posting]: ...
