from __future__ import annotations

import httpx

from deepgen.services.local_files import search_local_records
from deepgen.services.source_types import SourceResult


class SourceConnector:
    name: str

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        raise NotImplementedError


class FamilySearchConnector(SourceConnector):
    name = "familysearch"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        if not self.client_id or not self.client_secret:
            return []
        query = name.replace(" ", "+")
        return [
            SourceResult(
                source=self.name,
                title=f"FamilySearch candidate for {name}",
                url=(
                    "https://www.familysearch.org/search/record/results"
                    f"?q.anyDate.from={birth_year or ''}&q.givenName={query}"
                ),
                note="Live search URL generated. Add OAuth token flow for direct API retrieval.",
            )
        ]


class NaraConnector(SourceConnector):
    name = "nara"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        if not self.api_key:
            return []
        params = {
            "q": name,
            "rows": "5",
            "resultTypes": "description",
            "api.key": self.api_key,
        }
        if birth_year:
            params["q"] = f'{name} "{birth_year}"'

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get("https://catalog.archives.gov/api/v2", params=params)
                res.raise_for_status()
                payload = res.json()
        except Exception as exc:  # noqa: BLE001
            return [
                SourceResult(
                    source=self.name,
                    title=f"NARA request failed for {name}",
                    url="https://catalog.archives.gov/",
                    note=f"Failed to fetch NARA API results: {exc}",
                )
            ]

        descriptions = payload.get("data", [])[:5]
        results: list[SourceResult] = []
        for item in descriptions:
            title = (
                item.get("title")
                or item.get("description", {}).get("title")
                or f"NARA record for {name}"
            )
            na_id = item.get("naId") or item.get("description", {}).get("naId")
            url = f"https://catalog.archives.gov/id/{na_id}" if na_id else "https://catalog.archives.gov/"
            results.append(
                SourceResult(
                    source=self.name,
                    title=str(title),
                    url=url,
                    note="Live NARA API result.",
                )
            )
        return results


class LocConnector(SourceConnector):
    name = "loc"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        query = f'{name} {birth_year}' if birth_year else name
        params = {"fo": "json", "q": query}
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get("https://www.loc.gov/search/", params=params)
                res.raise_for_status()
                payload = res.json()
        except Exception as exc:  # noqa: BLE001
            return [
                SourceResult(
                    source=self.name,
                    title=f"LOC request failed for {name}",
                    url="https://www.loc.gov/",
                    note=f"Failed to fetch LOC API results: {exc}",
                )
            ]

        items = payload.get("results", [])[:5]
        results: list[SourceResult] = []
        for item in items:
            title = str(item.get("title") or f"LOC record for {name}")
            url = str(item.get("url") or "https://www.loc.gov/")
            date = item.get("date")
            note = f"Live LOC API result. Date: {date}" if date else "Live LOC API result."
            results.append(SourceResult(source=self.name, title=title, url=url, note=note))
        return results


class LocalFolderConnector(SourceConnector):
    name = "local_folder"

    def __init__(self, folder_path: str):
        self.folder_path = folder_path

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        if not self.folder_path:
            return []
        try:
            return search_local_records(
                folder_path=self.folder_path,
                name=name,
                birth_year=birth_year,
                max_results=6,
            )
        except Exception as exc:  # noqa: BLE001
            return [
                SourceResult(
                    source=self.name,
                    title=f"Local folder search failed for {name}",
                    url="file://",
                    note=f"Failed local search: {exc}",
                )
            ]


def build_connectors(configs: dict[str, dict[str, str]]) -> list[SourceConnector]:
    connectors: list[SourceConnector] = []
    family = configs.get("familysearch", {})
    nara = configs.get("nara", {})
    loc = configs.get("loc", {})
    local = configs.get("local", {})

    if family.get("client_id") and family.get("client_secret"):
        connectors.append(
            FamilySearchConnector(
                client_id=family["client_id"],
                client_secret=family["client_secret"],
            )
        )
    if nara.get("api_key"):
        connectors.append(NaraConnector(api_key=nara["api_key"]))
    connectors.append(LocConnector(api_key=loc.get("api_key", "")))

    local_folder = local.get("folder_path", "").strip()
    local_enabled = local.get("enabled", "false").lower() == "true"
    if local_enabled and local_folder:
        connectors.append(LocalFolderConnector(folder_path=local_folder))

    return connectors
