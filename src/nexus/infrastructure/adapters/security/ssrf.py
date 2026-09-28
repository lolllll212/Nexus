"""SSRF (Server-Side Request Forgery) protection and URL validation."""

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple


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


def validate_safe_url(url: str, allow_local: bool = False) -> Tuple[bool, str]:
    """Validate that a URL is safe to fetch and does not target internal or metadata services.

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
            # Not an IP literal, resolve DNS
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for item in addr_info:
                    resolved_ip = item[4][0]
                    if not is_safe_ip(resolved_ip):
                        return False, f"Host '{hostname}' resolves to private/internal IP {resolved_ip}"
            except socket.gaierror:
                # DNS resolution failure will be handled by the caller or allowed if offline testing
                pass

    return True, ""
