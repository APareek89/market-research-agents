"""Bounded public GETs: DNS pinned at the socket, TLS verifies the original host."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
import zlib
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_BYTES = 1024 * 1024
MAX_SECONDS = 15.0
MAX_REDIRECTS = 3
_DNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="public-dns")
_DNS_SLOTS = threading.BoundedSemaphore(4)
_FETCH_SLOTS = threading.BoundedSemaphore(4)
_TRANSITION_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32",
))


class NetworkDenied(ValueError):
    """Only fixed, non-sensitive reason codes leave this transport."""


@dataclass(frozen=True)
class PublicResponse:
    url: str
    content_type: str
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _public_ip(value: str):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise NetworkDenied("invalid_address") from None
    if not address.is_global or address.is_multicast or address.is_unspecified:
        raise NetworkDenied("nonpublic_address")
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped or any(address in net for net in _TRANSITION_NETWORKS):
            raise NetworkDenied("translated_address")
    return address


def _parse_url(value: str):
    if not isinstance(value, str) or len(value) > 4096 or re.search(r"[\x00-\x20\x7f\\]", value):
        raise NetworkDenied("invalid_url")
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            raise NetworkDenied("unsupported_url")
        if parsed.username is not None or parsed.password is not None:
            raise NetworkDenied("url_credentials_denied")
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if "%" in host or host.endswith(".") or len(host) > 253:
            raise NetworkDenied("invalid_host")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            raise NetworkDenied("nonstandard_port")
        try:
            _public_ip(host)
        except NetworkDenied as exc:
            if str(exc) != "invalid_address":
                raise
            if not re.fullmatch(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                raise NetworkDenied("invalid_host") from None
            if "." not in host or any(not x or len(x) > 63 or x.startswith("-") or x.endswith("-") for x in host.split(".")):
                raise NetworkDenied("invalid_host") from None
            if all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", x) for x in host.split(".")):
                raise NetworkDenied("ambiguous_address") from None
        authority = f"[{host}]" if ":" in host else host
        target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        target.encode("ascii")
        return parsed.scheme, host, port, target, f"{parsed.scheme}://{authority}{target}"
    except NetworkDenied:
        raise
    except (ValueError, UnicodeError):
        raise NetworkDenied("invalid_url") from None


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise NetworkDenied("deadline_exceeded")
    return left


def _resolve_public(host: str, port: int, deadline: float):
    if not _DNS_SLOTS.acquire(blocking=False):
        raise NetworkDenied("resolver_busy")
    try:
        future = _DNS_POOL.submit(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    except Exception:
        _DNS_SLOTS.release()
        raise NetworkDenied("resolution_failed") from None
    future.add_done_callback(lambda _: _DNS_SLOTS.release())
    try:
        answers = future.result(timeout=min(3.0, _remaining(deadline)))
    except FutureTimeout:
        raise NetworkDenied("resolution_timeout") from None
    except Exception:
        raise NetworkDenied("resolution_failed") from None
    if not answers:
        raise NetworkDenied("resolution_failed")
    candidates = []
    for family, socktype, proto, _, sockaddr in answers:
        if family not in (socket.AF_INET, socket.AF_INET6):
            raise NetworkDenied("unsupported_address")
        address = _public_ip(sockaddr[0])
        if family == socket.AF_INET6 and sockaddr[3] != 0:
            raise NetworkDenied("scoped_address")
        candidates.append((family, socktype, proto, sockaddr, address))
    # Every answer must be public; only one selected numeric sockaddr is dialed.
    # No second DNS resolution is allowed to substitute an internal address.
    return sorted(candidates, key=lambda x: x[0] != socket.AF_INET)[0]


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, *, secure, candidate, deadline):
        super().__init__(host, port, timeout=min(5.0, _remaining(deadline)))
        self._candidate = candidate
        self._deadline = deadline
        self._secure = secure
        self._timer = None
        self._wire_socket = None

    def connect(self):
        family, socktype, proto, sockaddr, expected = self._candidate
        raw = socket.socket(family, socktype, proto)
        self.sock = raw
        self._wire_socket = raw
        # Absolute timeout bounds slow headers and byte-at-a-time bodies too.
        def expire():
            current = self._wire_socket
            if current is not None:
                try:
                    current.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                current.close()
        self._timer = threading.Timer(_remaining(self._deadline), expire)
        self._timer.daemon = True
        self._timer.start()
        raw.settimeout(min(5.0, _remaining(self._deadline)))
        raw.connect(sockaddr)
        if _public_ip(raw.getpeername()[0]) != expected:
            raise NetworkDenied("connected_address_mismatch")
        if self._secure:
            # Original hostname is SNI and certificate identity, not the IP.
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
            self._wire_socket = self.sock
            self.sock.do_handshake()

    def finish(self):
        # HTTPConnection may call close() after response headers while the
        # response still owns the socket. Only this finalizer cancels the timer.
        if self._timer:
            self._timer.cancel()
        super().close()
        if self._wire_socket is not None:
            self._wire_socket.close()


def public_get(url: str, *, max_bytes: int = MAX_BYTES, max_seconds: float = MAX_SECONDS) -> PublicResponse:
    """Fetch bounded text without proxies, credentials, cookies or hidden retries."""
    if not 1 <= max_bytes <= MAX_BYTES or not 0 < max_seconds <= MAX_SECONDS:
        raise NetworkDenied("invalid_limits")
    if not _FETCH_SLOTS.acquire(blocking=False):
        raise NetworkDenied("fetch_busy")
    deadline = time.monotonic() + max_seconds
    try:
        for redirect in range(MAX_REDIRECTS + 1):
            scheme, host, port, target, canonical = _parse_url(url)
            candidate = _resolve_public(host, port, deadline)
            conn = _PinnedConnection(host, port, secure=scheme == "https", candidate=candidate, deadline=deadline)
            response = None
            try:
                conn.request("GET", target, headers={
                    "User-Agent": "PortfolioResearch/1.0", "Accept": "text/html,text/plain,application/json",
                    "Accept-Encoding": "gzip, identity", "Connection": "close",
                })
                response = conn.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location or redirect >= MAX_REDIRECTS:
                        raise NetworkDenied("redirect_limit")
                    url = urljoin(canonical, location)
                    if scheme == "https" and urlsplit(url).scheme != "https":
                        raise NetworkDenied("tls_downgrade")
                    continue
                if response.status != 200:
                    raise NetworkDenied("http_status")
                encoding = response.getheader("Content-Encoding", "identity").strip().lower()
                if encoding not in ("identity", "", "gzip"):
                    raise NetworkDenied("unsupported_encoding")
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
                content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type not in ("text/html", "text/plain", "application/json", "application/xhtml+xml"):
                    raise NetworkDenied("unsupported_content_type")
                size = response.getheader("Content-Length")
                if size is not None and (not size.isdigit() or int(size) > max_bytes):
                    raise NetworkDenied("response_too_large")
                data = bytearray()
                raw_size = 0
                while True:
                    _remaining(deadline)
                    part = response.read(min(65536, max_bytes + 1 - raw_size))
                    if not part:
                        break
                    raw_size += len(part)
                    if raw_size > max_bytes:
                        raise NetworkDenied("response_too_large")
                    decoded = decoder.decompress(part, max_bytes + 1 - len(data)) if decoder else part
                    data.extend(decoded)
                    if len(data) > max_bytes:
                        raise NetworkDenied("response_too_large")
                    if decoder and decoder.unused_data:
                        raise NetworkDenied("invalid_compressed_response")
                if decoder:
                    data.extend(decoder.flush(max_bytes + 1 - len(data)))
                    if len(data) > max_bytes:
                        raise NetworkDenied("response_too_large")
                    if not decoder.eof:
                        raise NetworkDenied("invalid_compressed_response")
                _remaining(deadline)
                return PublicResponse(canonical, content_type, bytes(data))
            finally:
                if response is not None:
                    response.close()
                conn.finish()
        raise NetworkDenied("redirect_limit")
    except NetworkDenied:
        raise
    except Exception:
        raise NetworkDenied("request_failed") from None
    finally:
        _FETCH_SLOTS.release()
