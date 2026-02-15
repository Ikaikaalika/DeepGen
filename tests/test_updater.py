from deepgen.services.updater import check_for_updates


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):  # noqa: ARG002
        return _Resp(self.payload)


def test_check_for_updates_detects_newer_version(monkeypatch):
    payload = {
        "channel": "test",
        "latest": {
            "version": "0.2.0",
            "download_url": "https://example.com/DeepGen.dmg",
            "notes": "beta",
        },
    }

    monkeypatch.setattr("deepgen.services.updater.httpx.Client", lambda timeout: _Client(payload))

    result = check_for_updates(current_version="0.1.0", feed_url="https://example.com/feed.json")
    assert result.available is True
    assert result.latest_version == "0.2.0"


def test_check_for_updates_handles_fetch_failure(monkeypatch):
    class BadClient:
        def __init__(self, timeout):  # noqa: ARG002
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):  # noqa: ARG002
            raise RuntimeError("network down")

    monkeypatch.setattr("deepgen.services.updater.httpx.Client", BadClient)

    result = check_for_updates(current_version="0.1.0", feed_url="https://example.com/feed.json")
    assert result.available is False
    assert "Update check failed" in result.notes
