"""Pruebas de la frontera de confianza de IPs del backend."""

import unittest

from starlette.requests import Request

from app import main


def request_from(peer_ip: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": headers or [],
            "client": (peer_ip, 12345),
        }
    )


class ClientIpTrustTests(unittest.TestCase):
    def test_untrusted_peer_cannot_choose_rate_limit_key(self) -> None:
        request = request_from(
            "203.0.113.40",
            [(b"x-forwarded-for", b"198.51.100.10"), (b"x-taskflow-client-ip", b"198.51.100.11")],
        )

        self.assertEqual(main.get_client_ip(request), "203.0.113.40")

    def test_trusted_nginx_peer_can_pass_a_valid_normalized_ip(self) -> None:
        request = request_from("172.31.0.10", [(b"x-taskflow-client-ip", b"2001:db8::8")])

        self.assertEqual(main.get_client_ip(request), "2001:db8::8")

    def test_invalid_private_header_falls_back_to_proxy_peer(self) -> None:
        request = request_from("172.31.0.10", [(b"x-taskflow-client-ip", b"not-an-ip")])

        self.assertEqual(main.get_client_ip(request), "172.31.0.10")
