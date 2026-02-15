from dataclasses import dataclass


@dataclass
class SourceResult:
    source: str
    title: str
    url: str
    note: str
