"""No outbound network: prove connect pinning, bounds and execution denial."""
import asyncio
from contextlib import ExitStack
import io
import gzip
import ipaddress
import socket
import time
import unittest
from unittest.mock import Mock, patch
from app import safe_network as net

PUBLIC = "93.184.216.34"
CANDIDATE = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
             (PUBLIC, 443), ipaddress.ip_address(PUBLIC))


class Response:
    def __init__(self, status=200, headers=None, data=b"hello"):
        self.status = status
        self.headers = {"Content-Type": "text/plain", **(headers or {})}
        self.body = io.BytesIO(data)
    def getheader(self, key, default=None): return self.headers.get(key, default)
    def read(self, size): return self.body.read(size)
    def close(self): self.body.close()


class NetworkContract(unittest.TestCase):
    def test_private_ambiguous_credentials_and_ports_denied_before_connect(self):
        urls = ["http://127.0.0.1/", "http://169.254.169.254/", "http://10.0.0.1/",
                "http://172.28.0.3/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
                "http://[64:ff9b::7f00:1]/", "http://2130706433/", "http://0177.0.0.1/",
                "http://user:password@example.com/", "http://example.com:5432/",
                "file:///etc/passwd", "http://example.com\\@127.0.0.1/",
                "https://example.com/\r\nInjected: yes", "http://localhost/", "http://[fe80::1%25eth0]/"]
        with patch.object(net.socket, "socket") as dial:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(net.NetworkDenied):
                    net.public_get(url)
            dial.assert_not_called()

    def test_mixed_dns_answers_rejected_and_dns_occurs_once(self):
        answer = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC, 443)),
                  (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.1", 443))]
        with patch.object(net.socket, "getaddrinfo", return_value=answer) as resolve:
            with self.assertRaisesRegex(net.NetworkDenied, "nonpublic"):
                net._resolve_public("example.com", 443, time.monotonic() + 3)
            self.assertEqual(resolve.call_count, 1)

    def test_numeric_socket_dial_and_original_hostname_tls(self):
        wire = Mock()
        wire.getpeername.return_value = (PUBLIC, 443)
        tls = Mock()
        context = Mock()
        context.wrap_socket.return_value = tls
        with patch.object(net.socket, "socket", return_value=wire), patch.object(net.ssl, "create_default_context", return_value=context), patch.object(net.socket, "getaddrinfo") as dns:
            conn = net._PinnedConnection("example.com", 443, secure=True, candidate=CANDIDATE, deadline=time.monotonic() + 3)
            try:
                conn.connect()
                wire.connect.assert_called_once_with((PUBLIC, 443))
                dns.assert_not_called()
                context.wrap_socket.assert_called_once_with(wire, server_hostname="example.com", do_handshake_on_connect=False)
                tls.do_handshake.assert_called_once()
            finally:
                conn.finish()

    def test_connected_peer_mismatch_denied(self):
        wire = Mock()
        wire.getpeername.return_value = ("127.0.0.1", 443)
        with patch.object(net.socket, "socket", return_value=wire):
            conn = net._PinnedConnection("example.com", 443, secure=False, candidate=CANDIDATE, deadline=time.monotonic() + 3)
            try:
                with self.assertRaises(net.NetworkDenied): conn.connect()
            finally: conn.finish()

    def test_redirect_private_target_rechecked_before_second_socket(self):
        conn = Mock()
        conn.getresponse.return_value = Response(302, {"Location": "https://10.0.0.1/"})
        with patch.object(net, "_resolve_public", return_value=CANDIDATE), patch.object(net, "_PinnedConnection", return_value=conn) as dial:
            with self.assertRaisesRegex(net.NetworkDenied, "nonpublic"):
                net.public_get("https://example.com/")
            self.assertEqual(dial.call_count, 1)
            conn.finish.assert_called_once()

    def test_compression_size_redirect_and_status_bounds(self):
        cases = [Response(headers={"Content-Encoding": "br"}), Response(data=b"12345"),
                 Response(headers={"Content-Length": "999"}), Response(500),
                 Response(302, {"Location": "http://example.com/"}),
                 Response(headers={"Content-Type": "image/png"})]
        for response in cases:
            conn = Mock(); conn.getresponse.return_value = response
            with self.subTest(response=response), patch.object(net, "_resolve_public", return_value=CANDIDATE), patch.object(net, "_PinnedConnection", return_value=conn):
                with self.assertRaises(net.NetworkDenied): net.public_get("https://example.com/", max_bytes=4)
        conn = Mock(); conn.getresponse.side_effect = [Response(302, {"Location": "/next"}) for _ in range(4)]
        with patch.object(net, "_resolve_public", return_value=CANDIDATE), patch.object(net, "_PinnedConnection", return_value=conn):
            with self.assertRaisesRegex(net.NetworkDenied, "redirect_limit"):
                net.public_get("https://example.com/")
            self.assertEqual(conn.request.call_count, 4)

    def test_gzip_decodes_with_independent_wire_and_expanded_caps(self):
        cases = [(gzip.compress(b"hello"), 50, b"hello"),
                 (gzip.compress(b"x" * 100000), 500, None),
                 (gzip.compress(b"hello")[:-5], 50, None),
                 (gzip.compress(b"hello") + gzip.compress(b"extra"), 100, None)]
        for body, cap, expected in cases:
            response = Response(headers={"Content-Encoding":"gzip"}, data=body)
            conn = Mock(); conn.getresponse.return_value=response
            with self.subTest(expected=expected), patch.object(net,"_resolve_public",return_value=CANDIDATE), patch.object(net,"_PinnedConnection",return_value=conn):
                if expected is None:
                    with self.assertRaises(net.NetworkDenied): net.public_get("https://example.com/",max_bytes=cap)
                else:
                    self.assertEqual(net.public_get("https://example.com/",max_bytes=cap).body,expected)

    def test_total_deadline_timer_survives_http_response_close(self):
        # http.client closes its connection at headers for Connection: close,
        # while the response owns the file. The absolute timer must remain live.
        wire = Mock(); wire.getpeername.return_value = (PUBLIC, 443)
        with patch.object(net.socket, "socket", return_value=wire):
            conn = net._PinnedConnection("example.com", 443, secure=False, candidate=CANDIDATE, deadline=time.monotonic() + .04)
            conn.connect()
            conn.close()
            time.sleep(.07)
            wire.shutdown.assert_called_once_with(socket.SHUT_RDWR)
            conn.finish()

    def test_tool_scope_denial_and_search_parsing(self):
        from app import tools
        from app.execution import Execution, execution_scope
        html = b'<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffacts">Public fact</a><span class="result__snippet">Source summary</span></div>'
        with patch.object(tools, "public_get", return_value=net.PublicResponse("https://html.duckduckgo.com/", "text/html", html)) as fetch:
            with self.assertRaises(Exception): tools.web_search.invoke({"query": "example"})
            fetch.assert_not_called()
            # Context propagation, including worker threads, is a release boundary.
            with execution_scope(Execution(owner_id="00000000-0000-0000-0000-000000000001", run_id="00000000-0000-4000-8000-000000000004", mode="mock")):
                with self.assertRaises(Exception): asyncio.run(asyncio.to_thread(tools.web_fetch.invoke, {"url":"https://example.com"}))
            fetch.assert_not_called()
            with execution_scope(Execution(owner_id="00000000-0000-0000-0000-000000000001", run_id="00000000-0000-4000-8000-000000000004", mode="live")):
                text = tools.web_search.invoke({"query": "example"})
            self.assertIn("URL: https://example.com/facts", text)
            self.assertIn("Source summary", text)
            self.assertEqual(fetch.call_count, 1)


if __name__ == "__main__": unittest.main()
