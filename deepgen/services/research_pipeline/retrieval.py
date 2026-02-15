from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha1
from threading import BoundedSemaphore
from urllib.parse import urlsplit, urlunsplit

from deepgen.services.connectors import SourceConnector
from deepgen.services.source_types import SourceResult


@dataclass
class RetrievalEvidence:
    source: str
    title: str
    url: str
    note: str
    normalized_url: str
    normalized_title_hash: str


@dataclass
class ConnectorFetchResult:
    items: list[SourceResult]
    retries_used: int
    errors: list[str]


@dataclass
class RetrievalResult:
    evidence: list[RetrievalEvidence]
    retries_used: int
    errors: list[str]


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        split = urlsplit(raw)
    except ValueError:
        return raw

    scheme = split.scheme.lower()
    netloc = split.netloc.lower()
    path = split.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def normalize_title_hash(title: str) -> str:
    compact = " ".join((title or "").lower().split())
    return sha1(compact.encode("utf-8")).hexdigest()


def _search_with_retry(
    connector: SourceConnector,
    name: str,
    birth_year: int | None,
    max_retries: int,
    semaphore: BoundedSemaphore,
) -> ConnectorFetchResult:
    retries_used = 0
    errors: list[str] = []

    for attempt in range(max_retries + 1):
        with semaphore:
            try:
                items = connector.search_person(name=name, birth_year=birth_year)
                return ConnectorFetchResult(items=items, retries_used=retries_used, errors=errors)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{connector.name} attempt {attempt + 1}: {exc}")
                if attempt < max_retries:
                    retries_used += 1

    return ConnectorFetchResult(items=[], retries_used=retries_used, errors=errors)


def retrieve_evidence(
    connectors: list[SourceConnector],
    name: str,
    birth_year: int | None,
    *,
    max_retries: int = 1,
    max_results_per_connector: int = 6,
    max_total: int = 24,
    max_parallel_connectors: int = 4,
) -> RetrievalResult:
    if not connectors:
        return RetrievalResult(evidence=[], retries_used=0, errors=[])

    semaphore = BoundedSemaphore(max(1, max_parallel_connectors))
    retries_used = 0
    errors: list[str] = []
    merged: list[SourceResult] = []

    with ThreadPoolExecutor(max_workers=min(len(connectors), max_parallel_connectors)) as pool:
        futures = [
            pool.submit(_search_with_retry, connector, name, birth_year, max_retries, semaphore)
            for connector in connectors
        ]
        for future in futures:
            result = future.result()
            retries_used += result.retries_used
            errors.extend(result.errors)
            merged.extend(result.items[:max_results_per_connector])

    deduped: list[RetrievalEvidence] = []
    seen: set[tuple[str, str]] = set()
    for item in merged:
        normalized_url = normalize_url(item.url)
        normalized_title = normalize_title_hash(item.title)
        key = (normalized_url, normalized_title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            RetrievalEvidence(
                source=item.source,
                title=item.title,
                url=item.url,
                note=item.note,
                normalized_url=normalized_url,
                normalized_title_hash=normalized_title,
            )
        )
        if len(deduped) >= max_total:
            break

    return RetrievalResult(evidence=deduped, retries_used=retries_used, errors=errors)
