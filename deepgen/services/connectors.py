from dataclasses import dataclass


@dataclass
class SourceResult:
    source: str
    title: str
    url: str
    note: str


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
                url=f"https://www.familysearch.org/search/record/results?q.anyPlace=&q.anyDate.from={birth_year or ''}&q.givenName={query}",
                note="Connector scaffolded. Add OAuth token flow for live record retrieval.",
            )
        ]


class NaraConnector(SourceConnector):
    name = "nara"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        if not self.api_key:
            return []
        query = name.replace(" ", "%20")
        return [
            SourceResult(
                source=self.name,
                title=f"NARA candidate for {name}",
                url=f"https://catalog.archives.gov/api/v2?q={query}",
                note="Connector scaffolded. Parse JSON results and ingest document metadata.",
            )
        ]


class LocConnector(SourceConnector):
    name = "loc"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_person(self, name: str, birth_year: int | None) -> list[SourceResult]:
        query = name.replace(" ", "+")
        return [
            SourceResult(
                source=self.name,
                title=f"LOC candidate for {name}",
                url=f"https://www.loc.gov/search/?fo=json&q={query}",
                note="Public API endpoint scaffolded for document discovery.",
            )
        ]


def build_connectors(configs: dict[str, dict[str, str]]) -> list[SourceConnector]:
    connectors: list[SourceConnector] = []
    family = configs.get("familysearch", {})
    nara = configs.get("nara", {})
    loc = configs.get("loc", {})
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
    return connectors
