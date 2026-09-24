"""
src/ingestion/web_loader.py

Fetches a single live URL and returns it in the same shape file loaders
use (`loader.py`), so it flows through the existing chunk/embed/store
pipeline unchanged.

Ships with an explicit SSRF guard rather than a bare `requests.get()`:
fetching an arbitrary user-supplied URL from a server, unaudited, is one
of the most common real-world web app vulnerabilities (OWASP-listed) —
it can be used to reach a private network or a cloud metadata endpoint
(e.g. 169.254.169.254) from behind whatever firewall the server sits in.

What the guard covers: scheme allowlist (http/https only), rejecting
hostnames that resolve to a private/loopback/link-local/reserved IP, no
redirect-following, and caps on timeout and response size.

What it does NOT cover: DNS rebinding (a hostname resolving to a public
IP at validation time but a private one when the connection is actually
made). Closing that fully needs a network-level egress policy, not an
application-level check — see ARCHITECTURE.md.
"""
import ipaddress
import logging
import socket
from typing import List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5MB
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "AskMyDocs/2.0 (+https://github.com/JainRamyak/ASK_DOC_WEBSITE)"


class URLValidationError(Exception):
    pass


def _validate_url(url: str) -> str:
    """Raises URLValidationError if `url` is unsafe to fetch. Returns the
    first resolved IP address (mostly useful for tests/logging)."""
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise URLValidationError(
            f"Unsupported scheme '{parsed.scheme}'. Only http/https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL has no hostname.")

    # Resolve with getaddrinfo(), not gethostbyname(), so both IPv4 (A)
    # and IPv6 (AAAA) records are checked. gethostbyname() only returns
    # the IPv4 address — a hostname with a public A record but a private
    # AAAA record (e.g. an internal ULA range) would pass validation but
    # could still be reached if the actual fetch connects over IPv6.
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise URLValidationError(f"Could not resolve hostname '{hostname}': {e}")

    resolved_ips = {info[4][0] for info in addr_infos}
    for resolved_ip in resolved_ips:
        ip = ipaddress.ip_address(resolved_ip)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise URLValidationError(
                f"'{hostname}' resolves to {resolved_ip}, which is a private/"
                f"internal address. Refusing to fetch it."
            )

    allowed = settings.url_allowed_domains
    if allowed:
        lowered = hostname.lower()
        if not any(lowered == d or lowered.endswith(f".{d}") for d in allowed):
            raise URLValidationError(
                f"This deployment only accepts URLs from: {', '.join(allowed)}"
            )

    return next(iter(resolved_ips))


def load_url(url: str) -> List[dict]:
    """Fetch `url`, strip HTML boilerplate, and return it as a single
    {"text": ..., "source": ...} dict — same shape `loader.py` produces
    for a file, so it flows through the existing chunker unchanged."""
    _validate_url(url)

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException as e:
        raise URLValidationError(f"Failed to fetch '{url}': {e}")

    if 300 <= response.status_code < 400:
        raise URLValidationError(
            f"'{url}' returned a redirect (HTTP {response.status_code}). "
            f"Redirects are not followed — submit the final URL directly."
        )
    if response.status_code != 200:
        raise URLValidationError(f"'{url}' returned HTTP {response.status_code}.")

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise URLValidationError(
            f"'{url}' is not an HTML page (content-type: {content_type or 'unknown'})."
        )

    raw = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        raw.extend(chunk)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise URLValidationError(
                f"'{url}' exceeded the {MAX_RESPONSE_BYTES // (1024 * 1024)}MB size cap."
            )

    soup = BeautifulSoup(bytes(raw), "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())
    if not text:
        logger.warning("No extractable text found at %s", url)
        return []

    logger.info("Fetched URL: %s | %d chars extracted", url, len(text))
    return [{"text": text, "source": url}]
