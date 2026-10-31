"""The one line Meridian may not cross: the open internet is fine, this machine is not.

Meridian explores freely. But "any URL" quietly includes `http://127.0.0.1:8000`,
which on this machine is a private application holding real financial data, plus Postgres,
Redis, and anything else bound to loopback. A fetch tool with no network boundary is
not a browser; it is a hole straight into the host.

So the rule is about *address space*, never about topic:

* resolve the hostname first, then judge the **IP**, not the string — a public
  hostname pointing at 127.0.0.1 is the classic way past a name-based check;
* refuse loopback, private, link-local, multicast and reserved ranges, which covers
  localhost, the LAN, and cloud metadata at 169.254.169.254;
* refuse every scheme but http and https, so `file://` and friends never reach the
  URL opener;
* refuse non-standard ports, which is what a port scan through a fetch tool looks like.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse

#: The whole public web is reachable; these two are not.
ALLOWED_SCHEMES = frozenset({"http", "https"})
#: Normal web ports only. Anything else is a service, not a page.
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})

#: Hostnames that never resolve anywhere useful, refused before DNS.
BLOCKED_NAMES = frozenset({"localhost", "localhost.localdomain", "broadcasthost"})
BLOCKED_SUFFIXES = (".local", ".internal", ".localdomain", ".home.arpa", ".onion")


class Blocked(ValueError):
    """The URL points somewhere Meridian must not reach."""


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local      # includes 169.254.169.254, cloud metadata
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def check(url: str) -> str:
    """Return the URL if it is safe to fetch, else raise `Blocked`.

    Resolution happens here so the decision is made on the address the request
    would actually reach.
    """
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise Blocked(f"unparseable URL: {exc}") from exc

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise Blocked(f"scheme {parts.scheme!r} is not allowed — http and https only")

    host = (parts.hostname or "").lower().strip(".")
    if not host:
        raise Blocked("no host in URL")
    if host in BLOCKED_NAMES or host.endswith(BLOCKED_SUFFIXES):
        raise Blocked(f"{host!r} is a local name, not the public internet")

    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise Blocked(f"port {port} is not a web port")

    # A literal IP is judged directly; a name is resolved first, and *every*
    # address it resolves to must be public.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not _ip_is_public(literal):
            raise Blocked(f"{host} is not a public address")
        return url

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise Blocked(f"cannot resolve {host}: {exc.__class__.__name__}") from exc

    addrs = {info[4][0] for info in infos}
    if not addrs:
        raise Blocked(f"{host} resolves to nothing")
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise Blocked(f"{host} resolved to something unparseable") from None
        if not _ip_is_public(ip):
            raise Blocked(f"{host} resolves to {addr}, which is not public")
    return url
