from __future__ import annotations
from pathlib import Path

import httpx

from deepgen.services.local_files import search_local_records
from deepgen.services.source_types import SourceResult


class SourceConnector:
    name: str

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        raise NotImplementedError


def _surname_token(name: str) -> str:
    parts = [part for part in (name or "").split() if part.strip()]
    return parts[-1] if parts else ""


class FamilySearchConnector(SourceConnector):
    name = "familysearch"

    def __init__(self, client_id: str, client_secret: str, access_token: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        query = name.replace(" ", "+")
        fallback_url = (
            "https://www.familysearch.org/search/record/results"
            f"?q.anyDate.from={birth_year or ''}&q.givenName={query}"
        )

        results: list[SourceResult] = []
        failure_note = ""

        if self.access_token:
            params = {
                "q.givenName": (name.split(" ")[0] if name else ""),
                "q.surname": _surname_token(name),
                "count": "5",
            }
            if birth_year:
                params["q.birthLikeDate"] = str(birth_year)
            try:
                with httpx.Client(timeout=8.0) as client:
                    res = client.get(
                        "https://api.familysearch.org/platform/tree/search",
                        params=params,
                        headers={
                            "Authorization": f"Bearer {self.access_token}",
                            "Accept": "application/json",
                        },
                    )
                    res.raise_for_status()
                    payload = res.json()
                entries = payload.get("entries", [])[:5] if isinstance(payload, dict) else []
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    item_id = str(entry.get("id") or "").strip()
                    title = str(entry.get("title") or f"FamilySearch API match for {name}")
                    url = f"https://www.familysearch.org/ark:/61903/{item_id}" if item_id else fallback_url
                    results.append(
                        SourceResult(
                            source=self.name,
                            title=title,
                            url=url,
                            note="FamilySearch API result (platform/tree/search).",
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                failure_note = f" FamilySearch API lookup failed: {exc}"

        if results:
            return results

        if not self.client_id and not self.client_secret and not self.access_token:
            return []

        return [
            SourceResult(
                source=self.name,
                title=f"FamilySearch candidate for {name}",
                url=fallback_url,
                note=(
                    "FamilySearch web search URL generated. "
                    "Set familysearch.access_token for direct API retrieval."
                    f"{failure_note}"
                ).strip(),
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
        query = f"{name} {birth_year}" if birth_year else name
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


class CensusConnector(SourceConnector):
    name = "census"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:  # noqa: ARG002
        surname = _surname_token(name)
        if not surname:
            return []

        params = {
            "get": "NAME,COUNT,PROP100K,RANK",
            "NAME": surname.upper(),
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get("https://api.census.gov/data/2010/surname", params=params)
                res.raise_for_status()
                payload = res.json()
        except Exception as exc:  # noqa: BLE001
            return [
                SourceResult(
                    source=self.name,
                    title=f"Census surname lookup failed for {surname}",
                    url="https://www.census.gov/data/developers/data-sets/surnames.html",
                    note=f"Census API lookup failed: {exc}",
                )
            ]

        if not isinstance(payload, list) or len(payload) < 2:
            return []

        rows = payload[1:6]
        results: list[SourceResult] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 4:
                continue
            row_name = row[0]
            count = row[1]
            prop100k = row[2]
            rank = row[3]
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"Census surname profile: {row_name}",
                    url="https://www.census.gov/data/developers/data-sets/surnames.html",
                    note=f"Count={count}, Prop100K={prop100k}, Rank={rank}.",
                )
            )
        return results


class GnisDatasetConnector(SourceConnector):
    name = "gnis"

    def __init__(self, dataset_path: str):
        self.dataset_path = dataset_path

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        path = Path(self.dataset_path).expanduser()
        if not path.exists():
            return [
                SourceResult(
                    source=self.name,
                    title="GNIS dataset path not found",
                    url="",
                    note=f"Set gnis.dataset_path to a downloaded GNIS file/folder. Missing: {path}",
                )
            ]

        if path.is_dir():
            try:
                hits = search_local_records(
                    folder_path=str(path),
                    name=name,
                    birth_year=birth_year,
                    max_results=5,
                )
            except Exception as exc:  # noqa: BLE001
                return [
                    SourceResult(
                        source=self.name,
                        title=f"GNIS folder search failed for {name}",
                        url="",
                        note=f"GNIS folder lookup failed: {exc}",
                    )
                ]
            return [
                SourceResult(
                    source=self.name,
                    title=item.title,
                    url=item.url,
                    note=f"GNIS local dataset match. {item.note}",
                )
                for item in hits
            ]

        tokens = [token.lower() for token in name.split() if token.strip()][:2]
        results: list[SourceResult] = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return [
                SourceResult(
                    source=self.name,
                    title="GNIS dataset file unreadable",
                    url=path.as_uri(),
                    note=f"Unable to read dataset file: {exc}",
                )
            ]

        for line in content.splitlines()[:10000]:
            haystack = line.lower()
            if tokens and not any(token in haystack for token in tokens):
                continue
            title = line.strip()[:160] or path.name
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"GNIS row: {title}",
                    url=path.as_uri(),
                    note="Matched against local GNIS dataset export.",
                )
            )
            if len(results) >= 5:
                break

        return results


class GeoNamesConnector(SourceConnector):
    name = "geonames"

    def __init__(self, username: str):
        self.username = username

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:  # noqa: ARG002
        if not self.username:
            return []

        params = {
            "q": name,
            "maxRows": "5",
            "username": self.username,
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get("https://secure.geonames.org/searchJSON", params=params)
                res.raise_for_status()
                payload = res.json()
        except Exception as exc:  # noqa: BLE001
            return [
                SourceResult(
                    source=self.name,
                    title=f"GeoNames lookup failed for {name}",
                    url="https://www.geonames.org/",
                    note=f"GeoNames API lookup failed: {exc}",
                )
            ]

        items = payload.get("geonames", [])[:5] if isinstance(payload, dict) else []
        results: list[SourceResult] = []
        for item in items:
            geoname_id = item.get("geonameId")
            label = str(item.get("name") or item.get("toponymName") or "GeoNames result")
            country = str(item.get("countryName") or "")
            url = f"https://www.geonames.org/{geoname_id}" if geoname_id else "https://www.geonames.org/"
            note = f"GeoNames place authority match. Country: {country}" if country else "GeoNames place authority match."
            results.append(SourceResult(source=self.name, title=label, url=url, note=note))
        return results


class WikidataConnector(SourceConnector):
    name = "wikidata"

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:  # noqa: ARG002
        params = {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "format": "json",
            "type": "item",
            "limit": "5",
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get("https://www.wikidata.org/w/api.php", params=params)
                res.raise_for_status()
                payload = res.json()
        except Exception as exc:  # noqa: BLE001
            return [
                SourceResult(
                    source=self.name,
                    title=f"Wikidata lookup failed for {name}",
                    url="https://www.wikidata.org/",
                    note=f"Wikidata API lookup failed: {exc}",
                )
            ]

        entries = payload.get("search", [])[:5] if isinstance(payload, dict) else []
        results: list[SourceResult] = []
        for item in entries:
            qid = str(item.get("id") or "")
            label = str(item.get("label") or qid or "Wikidata item")
            description = str(item.get("description") or "")
            url = f"https://www.wikidata.org/wiki/{qid}" if qid else "https://www.wikidata.org/"
            note = f"Wikidata entity match. {description}".strip()
            results.append(SourceResult(source=self.name, title=label, url=url, note=note))
        return results


class EuropeanaConnector(SourceConnector):
    name = "europeana"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        if not self.api_key:
            return []

        query = f"{name} {birth_year}" if birth_year else name
        params = {
            "wskey": self.api_key,
            "query": query,
            "rows": "5",
            "profile": "minimal",
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get("https://api.europeana.eu/record/v2/search.json", params=params)
                res.raise_for_status()
                payload = res.json()
        except Exception as exc:  # noqa: BLE001
            return [
                SourceResult(
                    source=self.name,
                    title=f"Europeana lookup failed for {name}",
                    url="https://www.europeana.eu/",
                    note=f"Europeana API lookup failed: {exc}",
                )
            ]

        items = payload.get("items", [])[:5] if isinstance(payload, dict) else []
        results: list[SourceResult] = []
        for item in items:
            raw_title = item.get("title")
            if isinstance(raw_title, list) and raw_title:
                title = str(raw_title[0])
            else:
                title = str(raw_title or f"Europeana record for {name}")
            url = str(item.get("guid") or "https://www.europeana.eu/")
            provider = item.get("dataProvider")
            provider_text = provider[0] if isinstance(provider, list) and provider else provider
            note = (
                f"Europeana metadata result. Provider: {provider_text}"
                if provider_text
                else "Europeana metadata result."
            )
            results.append(SourceResult(source=self.name, title=title, url=url, note=note))
        return results


class OpenRefineConnector(SourceConnector):
    name = "openrefine"

    def __init__(self, service_url: str):
        self.service_url = service_url

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:  # noqa: ARG002
        if not self.service_url:
            return []

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(self.service_url, params={"query": name})
                res.raise_for_status()
                payload = res.json()
        except Exception as exc:  # noqa: BLE001
            return [
                SourceResult(
                    source=self.name,
                    title=f"OpenRefine reconciliation failed for {name}",
                    url=self.service_url,
                    note=f"OpenRefine service lookup failed: {exc}",
                )
            ]

        results_list: list[dict] = []
        if isinstance(payload, dict) and isinstance(payload.get("result"), list):
            results_list = payload["result"]
        elif isinstance(payload, dict):
            # Multi-query reconciliation response shape.
            for value in payload.values():
                if isinstance(value, dict) and isinstance(value.get("result"), list):
                    results_list.extend(value["result"])

        results: list[SourceResult] = []
        for item in results_list[:5]:
            entity_id = str(item.get("id") or "")
            title = str(item.get("name") or item.get("id") or "OpenRefine candidate")
            score = item.get("score")
            note = f"OpenRefine reconciliation match. Score={score}." if score is not None else "OpenRefine reconciliation match."
            results.append(
                SourceResult(
                    source=self.name,
                    title=title,
                    url=f"{self.service_url}#{entity_id}" if entity_id else self.service_url,
                    note=note,
                )
            )
        return results


class SocialLeadConnector(SourceConnector):
    name = "social_leads"

    def __init__(
        self,
        *,
        x_enabled: bool,
        linkedin_enabled: bool,
        reddit_enabled: bool,
        github_enabled: bool,
        facebook_enabled: bool,
        instagram_enabled: bool,
        bluesky_enabled: bool,
    ):
        self.x_enabled = x_enabled
        self.linkedin_enabled = linkedin_enabled
        self.reddit_enabled = reddit_enabled
        self.github_enabled = github_enabled
        self.facebook_enabled = facebook_enabled
        self.instagram_enabled = instagram_enabled
        self.bluesky_enabled = bluesky_enabled

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        query = f"{name} {birth_year}" if birth_year else name
        encoded = query.replace(" ", "%20")
        name_handle = "".join(ch for ch in name.lower() if ch.isalnum())[:30] or "person"

        results: list[SourceResult] = []

        if self.linkedin_enabled:
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"LinkedIn people search lead: {name}",
                    url=f"https://www.linkedin.com/search/results/people/?keywords={encoded}",
                    note="Potential contact lead from public LinkedIn search. Manual verification required.",
                )
            )
        if self.x_enabled:
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"X/Twitter search lead: {name}",
                    url=f"https://x.com/search?q={encoded}&src=typed_query",
                    note="Potential contact lead from public X search results. Manual verification required.",
                )
            )
        if self.reddit_enabled:
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"Reddit discussion lead: {name}",
                    url=f"https://www.reddit.com/search/?q={encoded}",
                    note="Potential information lead from Reddit communities and threads.",
                )
            )
        if self.github_enabled:
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"GitHub user lead: {name}",
                    url=f"https://github.com/search?q={encoded}&type=users",
                    note="Potential public-profile contact lead from GitHub user search.",
                )
            )
        if self.facebook_enabled:
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"Facebook public search lead: {name}",
                    url=f"https://www.facebook.com/search/top/?q={encoded}",
                    note="Potential contact lead from Facebook public search (login may be required).",
                )
            )
        if self.instagram_enabled:
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"Instagram profile lead: {name}",
                    url=f"https://www.instagram.com/{name_handle}/",
                    note="Potential profile lead from Instagram handle heuristic. Manual verification required.",
                )
            )
        if self.bluesky_enabled:
            results.append(
                SourceResult(
                    source=self.name,
                    title=f"Bluesky search lead: {name}",
                    url=f"https://bsky.app/search?q={encoded}",
                    note="Potential contact lead from public Bluesky search results.",
                )
            )

        return results[:8]


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


def _enabled(config: dict[str, str]) -> bool:
    return str(config.get("enabled", "false")).lower() == "true"


def build_connectors(configs: dict[str, dict[str, str]]) -> list[SourceConnector]:
    connectors: list[SourceConnector] = []

    family = configs.get("familysearch", {})
    nara = configs.get("nara", {})
    loc = configs.get("loc", {})
    census = configs.get("census", {})
    gnis = configs.get("gnis", {})
    geonames = configs.get("geonames", {})
    wikidata = configs.get("wikidata", {})
    europeana = configs.get("europeana", {})
    openrefine = configs.get("openrefine", {})
    social = configs.get("social", {})
    local = configs.get("local", {})

    family_access_token = family.get("access_token", "").strip()
    if family.get("client_id") or family.get("client_secret") or family_access_token:
        connectors.append(
            FamilySearchConnector(
                client_id=family.get("client_id", ""),
                client_secret=family.get("client_secret", ""),
                access_token=family_access_token,
            )
        )

    if nara.get("api_key"):
        connectors.append(NaraConnector(api_key=nara["api_key"]))

    connectors.append(LocConnector(api_key=loc.get("api_key", "")))

    if _enabled(census):
        connectors.append(CensusConnector(api_key=census.get("api_key", "")))

    if _enabled(gnis):
        dataset_path = gnis.get("dataset_path", "").strip()
        if dataset_path:
            connectors.append(GnisDatasetConnector(dataset_path=dataset_path))

    if _enabled(geonames) and geonames.get("username", "").strip():
        connectors.append(GeoNamesConnector(username=geonames["username"].strip()))

    if _enabled(wikidata):
        connectors.append(WikidataConnector())

    if _enabled(europeana) and europeana.get("api_key", "").strip():
        connectors.append(EuropeanaConnector(api_key=europeana["api_key"].strip()))

    if _enabled(openrefine) and openrefine.get("service_url", "").strip():
        connectors.append(OpenRefineConnector(service_url=openrefine["service_url"].strip()))

    if _enabled(social):
        connectors.append(
            SocialLeadConnector(
                x_enabled=str(social.get("x_enabled", "true")).lower() == "true",
                linkedin_enabled=str(social.get("linkedin_enabled", "true")).lower() == "true",
                reddit_enabled=str(social.get("reddit_enabled", "true")).lower() == "true",
                github_enabled=str(social.get("github_enabled", "true")).lower() == "true",
                facebook_enabled=str(social.get("facebook_enabled", "false")).lower() == "true",
                instagram_enabled=str(social.get("instagram_enabled", "false")).lower() == "true",
                bluesky_enabled=str(social.get("bluesky_enabled", "false")).lower() == "true",
            )
        )

    local_folder = local.get("folder_path", "").strip()
    if _enabled(local) and local_folder:
        connectors.append(LocalFolderConnector(folder_path=local_folder))

    return connectors
