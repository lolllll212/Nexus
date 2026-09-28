"""SSRF (Server-Side Request Forgery) protection and URL validation."""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse

BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
}

BLOCKED_IP_STRINGS = {
    "169.254.169.254",  # AWS / GCP / Azure IMDS
    "100.100.100.200",  # Alibaba cloud metadata
}


def is_safe_ip(ip_str: str) -> bool:
    """Return True if the IP address is globally routable and safe from SSRF."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip_str in BLOCKED_IP_STRINGS:
            return False
        if ip.is_loopback:
            return False
        if ip.is_private:
            return False
        if ip.is_link_local:
            return False
        if ip.is_multicast:
            return False
        if ip.is_reserved:
            return False
        if ip.is_unspecified:
            return False
        return True
    except ValueError:
        return False


def validate_safe_url(url: str, allow_local: bool = False) -> tuple[bool, str]:
    """Validate that a URL is safe to fetch and does not target internal or metadata services.

    Fails closed on any DNS resolution error.
    Returns:
        (is_safe, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "Empty or invalid URL"

    try:
        parsed = urlparse(url.strip())
    except Exception as e:
        return False, f"Failed to parse URL: {e}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"Disallowed protocol scheme '{scheme}'. Only http and https are permitted."

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "URL is missing a valid hostname"

    if not allow_local:
        if hostname in BLOCKED_HOSTNAMES:
            return False, f"Host '{hostname}' is blocked by SSRF security policy"

        # Check if hostname directly represents an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if not is_safe_ip(str(ip)):
                return False, f"Target IP {hostname} is non-routable or private, blocked by SSRF policy"
        except ValueError:
            # Not an IP literal, resolve DNS and fail closed on resolution failure
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                if not addr_info:
                    return False, f"DNS resolution for '{hostname}' returned no address records"
                for item in addr_info:
                    resolved_ip = item[4][0]
                    if not is_safe_ip(resolved_ip):
                        return False, f"Host '{hostname}' resolves to private/internal IP {resolved_ip}"
            except socket.gaierror as e:
                return False, f"DNS resolution failed for '{hostname}': {e}"

    return True, ""


class SSRFSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Intercepts and validates every redirect hop against SSRF policies before connecting."""

    def __init__(self, allow_local: bool = False, max_redirects: int = 5) -> None:
        super().__init__()
        self.allow_local = allow_local
        self.max_redirects = max_redirects
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        if self.redirect_count > self.max_redirects:
            raise urllib.error.HTTPError(newurl, 400, "Maximum redirect limit exceeded", headers, fp)

        is_safe, err = validate_safe_url(newurl, allow_local=self.allow_local)
        if not is_safe:
            raise urllib.error.HTTPError(newurl, 403, f"SSRF Blocked Redirect: {err}", headers, fp)

        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_safe_opener(allow_local: bool = False, max_redirects: int = 5) -> urllib.request.OpenerDirector:
    """Build a urllib OpenerDirector with strict SSRF redirect interception."""
    redirect_handler = SSRFSafeRedirectHandler(allow_local=allow_local, max_redirects=max_redirects)
    opener = urllib.request.build_opener(redirect_handler)
    return opener


def safe_http_fetch(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 12.0,
    allow_local: bool = False,
    max_redirects: int = 5,
) -> tuple[int, str, dict[str, str]]:
    """Perform an SSRF-safe HTTP request with pinned validation and redirect protection."""
    is_safe, err = validate_safe_url(url, allow_local=allow_local)
    if not is_safe:
        return 403, f"SSRF Blocked: {err}", {}

    opener = build_safe_opener(allow_local=allow_local, max_redirects=max_redirects)
    req_headers = dict(headers or {})
    req_headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with opener.open(req, timeout=timeout) as resp:
        content = resp.read().decode("utf-8", errors="replace")
        resp_headers = dict(resp.headers)
        return resp.status, content, resp_headers
