from deepgen.services.connectors import build_connectors


def test_build_connectors_includes_extended_sources_when_enabled():
    configs = {
        "familysearch": {"client_id": "cid", "client_secret": "sec", "access_token": "tok"},
        "nara": {"api_key": "nara-key"},
        "loc": {"api_key": "loc-key"},
        "census": {"enabled": "true", "api_key": "census-key"},
        "gnis": {"enabled": "true", "dataset_path": "/tmp"},
        "geonames": {"enabled": "true", "username": "demo"},
        "wikidata": {"enabled": "true"},
        "europeana": {"enabled": "true", "api_key": "euro-key"},
        "openrefine": {"enabled": "true", "service_url": "http://localhost:3333/reconcile"},
        "local": {"enabled": "true", "folder_path": "/tmp"},
    }

    names = [connector.name for connector in build_connectors(configs)]

    assert "familysearch" in names
    assert "nara" in names
    assert "loc" in names
    assert "census" in names
    assert "gnis" in names
    assert "geonames" in names
    assert "wikidata" in names
    assert "europeana" in names
    assert "openrefine" in names
    assert "local_folder" in names


def test_build_connectors_respects_disabled_flags():
    configs = {
        "familysearch": {"client_id": "", "client_secret": "", "access_token": ""},
        "nara": {"api_key": ""},
        "loc": {"api_key": ""},
        "census": {"enabled": "false", "api_key": ""},
        "gnis": {"enabled": "false", "dataset_path": ""},
        "geonames": {"enabled": "false", "username": ""},
        "wikidata": {"enabled": "false"},
        "europeana": {"enabled": "false", "api_key": ""},
        "openrefine": {"enabled": "false", "service_url": ""},
        "local": {"enabled": "false", "folder_path": ""},
    }

    names = [connector.name for connector in build_connectors(configs)]

    assert names == ["loc"]
