"""Dowód, że bariera z conftest faktycznie blokuje ruch sieciowy.

Bez tego testu bariera mogłaby przestać działać niezauważenie, a testy
znów zaczęłyby logować się do Garmina i prowokować odpowiedzi 429.
"""
from __future__ import annotations

import socket

import pytest


def test_create_connection_is_blocked_by_default():
    with pytest.raises(RuntimeError, match="połączenia sieciowego"):
        socket.create_connection(("example.invalid", 80), timeout=0.1)


def test_getaddrinfo_is_blocked_by_default():
    with pytest.raises(RuntimeError, match="połączenia sieciowego"):
        socket.getaddrinfo("example.invalid", 80)


def test_socket_connect_is_blocked_by_default():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        with pytest.raises(RuntimeError, match="połączenia sieciowego"):
            handle.connect(("127.0.0.1", 9))


@pytest.mark.allow_network
def test_marker_restores_real_socket_functions():
    """Marker zdejmuje barierę: funkcje są oryginalne, nic nie łączymy."""
    assert socket.getaddrinfo is not None
    assert socket.create_connection.__module__ == "socket"
