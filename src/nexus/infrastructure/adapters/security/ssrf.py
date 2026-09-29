"""SSRF (Server-Side Request Forgery) protection, URL validation, and IP pinning."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
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


def resolve_and_validate_safe_url(url: str, allow_local: bool = False) -> tuple[bool, str, str | None]:
    """Validate that a URL is safe to fetch and return (is_safe, error_message, pinned_ip).

    Fails closed on any DNS resolution error. Resolves IP address once and pins it
    to eliminate DNS rebinding (TOCTOU) attacks.
    """
    if not url or not isinstance(url, str):
        return False, "Empty or invalid URL", None

    try:
        parsed = urlparse(url.strip())
    except Exception as e:
        return False, f"Failed to parse URL: {e}", None

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"Disallowed protocol scheme '{scheme}'. Only http and https are permitted.", None

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "URL is missing a valid hostname", None

    pinned_ip: str | None = None
    if not allow_local:
        if hostname in BLOCKED_HOSTNAMES:
            return False, f"Host '{hostname}' is blocked by SSRF security policy", None

        # Check if hostname directly represents an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if not is_safe_ip(str(ip)):
                return False, f"Target IP {hostname} is non-routable or private, blocked by SSRF policy", None
            pinned_ip = str(ip)
        except ValueError:
            # Not an IP literal, resolve DNS and fail closed on resolution failure
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                if not addr_info:
                    return False, f"DNS resolution for '{hostname}' returned no address records", None
                for item in addr_info:
                    resolved_ip = item[4][0]
                    if not is_safe_ip(resolved_ip):
                        return False, f"Host '{hostname}' resolves to private/internal IP {resolved_ip}", None
                    if pinned_ip is None:
                        pinned_ip = resolved_ip
            except socket.gaierror as e:
                return False, f"DNS resolution failed for '{hostname}': {e}", None
    else:
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            if addr_info:
                pinned_ip = addr_info[0][4][0]
        except Exception:
            pass

    return True, "", pinned_ip


def validate_safe_url(url: str, allow_local: bool = False) -> tuple[bool, str]:
    """Validate that a URL is safe to fetch and does not target internal or metadata services.

    Fails closed on any DNS resolution error.
    Returns:
        (is_safe, error_message)
    """
    safe, err, _ = resolve_and_validate_safe_url(url, allow_local=allow_local)
    return safe, err


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

        is_safe, err, _ = resolve_and_validate_safe_url(newurl, allow_local=self.allow_local)
        if not is_safe:
            raise urllib.error.HTTPError(newurl, 403, f"SSRF Blocked Redirect: {err}", headers, fp)

        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PinnedHTTPHandler(urllib.request.HTTPHandler):
    """HTTP handler that connects directly to the pre-resolved pinned IP."""

    def __init__(self, pinned_ip: str, original_host: str):
        super().__init__()
        self.pinned_ip = pinned_ip
        self.original_host = original_host

    def http_open(self, req):
        return self.do_open(self._build_connection, req)

    def _build_connection(self, host, timeout=30, **kwargs):
        port = None
        if ":" in host:
            _, port_str = host.split(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                pass
        return http.client.HTTPConnection(self.pinned_ip, port=port, timeout=timeout, **kwargs)


class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    """HTTPS handler that connects to pinned IP while verifying certificate against original host."""

    def __init__(self, pinned_ip: str, original_host: str):
        super().__init__()
        self.pinned_ip = pinned_ip
        self.original_host = original_host

    def https_open(self, req):
        return self.do_open(self._build_connection, req)

    def _build_connection(self, host, timeout=30, **kwargs):
        import ssl

        port = None
        hostname = self.original_host
        if ":" in hostname:
            hostname = hostname.split(":", 1)[0]
        if ":" in host:
            _, port_str = host.split(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                pass
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(self.pinned_ip, port=port, timeout=timeout, context=context, **kwargs)
        orig_connect = conn.connect

        def _pinned_connect():
            try:
                orig_connect()
            except Exception:
                sock = socket.create_connection((self.pinned_ip, conn.port), conn.timeout)
                conn.sock = context.wrap_socket(sock, server_hostname=hostname)

        conn.connect = _pinned_connect
        return conn


def build_safe_opener(
    allow_local: bool = False,
    max_redirects: int = 5,
    pinned_ip: str | None = None,
    original_host: str | None = None,
) -> urllib.request.OpenerDirector:
    """Build a urllib OpenerDirector with strict SSRF redirect interception and IP pinning."""
    redirect_handler = SSRFSafeRedirectHandler(allow_local=allow_local, max_redirects=max_redirects)
    handlers: list[Any] = [redirect_handler]
    if pinned_ip and original_host:
        handlers.append(PinnedHTTPHandler(pinned_ip, original_host))
        handlers.append(PinnedHTTPSHandler(pinned_ip, original_host))
    opener = urllib.request.build_opener(*handlers)
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
    is_safe, err, pinned_ip = resolve_and_validate_safe_url(url, allow_local=allow_local)
    if not is_safe:
        return 403, f"SSRF Blocked: {err}", {}

    parsed = urlparse(url.strip())
    original_host = parsed.netloc

    opener = build_safe_opener(
        allow_local=allow_local,
        max_redirects=max_redirects,
        pinned_ip=pinned_ip,
        original_host=original_host,
    )
    req_headers = dict(headers or {})
    req_headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    if original_host:
        req_headers["Host"] = original_host

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with opener.open(req, timeout=timeout) as resp:
        content = resp.read().decode("utf-8", errors="replace")
        resp_headers = dict(resp.headers)
        return resp.status, content, resp_headers
