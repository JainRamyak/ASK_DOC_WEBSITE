"""
tests/test_web_loader.py

Run with: pytest tests/test_web_loader.py -v

Fast and key-free — the SSRF guard needs no network beyond DNS
resolution, and `test_load_url_returns_correct_shape` mocks the actual
HTTP fetch so it isn't dependent on a live third-party page staying up.
"""
import pytest

from src.ingestion.web_loader import URLValidationError, _validate_url, load_url


# ── SSRF guard ───────────────────────────────────────────────────────────

def test_validate_url_rejects_non_http_scheme():
    with pytest.raises(URLValidationError):
        _validate_url("file:///etc/passwd")


def test_validate_url_rejects_localhost():
    with pytest.raises(URLValidationError):
        _validate_url("http://localhost/")


def test_validate_url_rejects_loopback_ip():
    with pytest.raises(URLValidationError):
        _validate_url("http://127.0.0.1/")


def test_validate_url_rejects_cloud_metadata_ip():
    with pytest.raises(URLValidationError):
        _validate_url("http://169.254.169.254/latest/meta-data/")


def test_validate_url_rejects_unspecified_ip():
    with pytest.raises(URLValidationError):
        _validate_url("http://0.0.0.0/")


def test_validate_url_rejects_missing_hostname():
    with pytest.raises(URLValidationError):
        _validate_url("http:///no-host")


def test_validate_url_accepts_valid_public_url():
    # example.com is IANA-reserved for documentation and always resolves
    # to a public IP — this should NOT raise.
    _validate_url("https://example.com/")


def test_validate_url_rejects_private_ipv6_even_with_public_ipv4(monkeypatch):
    """A hostname with a public A record but a private AAAA record must
    still be rejected — checking only the IPv4 address (as gethostbyname()
    would) misses this."""
    import src.ingestion.web_loader as web_loader

    def fake_getaddrinfo(hostname, port):
        return [
            (2, 1, 6, "", ("93.184.216.34", 0)),   # public IPv4
            (10, 1, 6, "", ("fd00::1", 0, 0, 0)),  # private IPv6 (ULA)
        ]

    monkeypatch.setattr(web_loader.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(URLValidationError):
        web_loader._validate_url("https://example.com/")


# ── load_url() shape and boilerplate stripping ───────────────────────────

def test_load_url_returns_correct_shape(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}

        def iter_content(self, chunk_size):
            yield (
                b"<html><head><style>.x{color:red}</style></head>"
                b"<body><nav>skip me</nav>"
                b"<p>Python was created by Guido van Rossum.</p>"
                b"<footer>skip me too</footer></body></html>"
            )

    def fake_get(url, headers, timeout, allow_redirects, stream):
        return FakeResponse()

    monkeypatch.setattr("src.ingestion.web_loader._validate_url", lambda u: "93.184.216.34")
    monkeypatch.setattr("requests.get", fake_get)

    docs = load_url("https://example.com/python")

    assert len(docs) == 1
    assert docs[0]["source"] == "https://example.com/python"
    assert "Guido van Rossum" in docs[0]["text"]
    assert "skip me" not in docs[0]["text"]


# ── Domain allowlist ─────────────────────────────────────────────────────

def test_domain_allowlist_blocks_unlisted_domain(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "url_allowed_domains_raw", "wikipedia.org")
    with pytest.raises(URLValidationError):
        _validate_url("https://example.com/page")


def test_domain_allowlist_allows_listed_domain_and_subdomains(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "url_allowed_domains_raw", "wikipedia.org")
    _validate_url("https://en.wikipedia.org/wiki/RAG")  # should not raise


def test_empty_allowlist_means_any_public_domain_allowed(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "url_allowed_domains_raw", "")
    _validate_url("https://example.com/page")  # should not raise
