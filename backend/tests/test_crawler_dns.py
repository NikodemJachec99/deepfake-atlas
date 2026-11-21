"""Crawler łączy się z adresem IP sprawdzonym raz. Adresy zmyślone (zakresy dokumentacyjne)."""

import socket

import httpx
import pytest

from crawler import fetch


def fake_dns(answers):
    calls = {"n": 0}

    def getaddrinfo(host, port, *args, **kwargs):
        calls["n"] += 1
        ip = answers[min(calls["n"], len(answers)) - 1]
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    return getaddrinfo, calls


def fetcher_with(monkeypatch, handler, settings):
    settings.CRAWLER_PROXY = ""
    f = fetch.HttpFetcher()
    monkeypatch.setattr(f, "_client", lambda profile: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))
    return f


def test_connection_goes_to_the_checked_ip_even_if_dns_changes(monkeypatch, settings):
    getaddrinfo, calls = fake_dns(["93.184.216.34", "10.0.0.5"])  # druga odpowiedź to rebinding do sieci wewnętrznej
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers["host"], request.extensions.get("sni_hostname")))
        return httpx.Response(200, html="<html><title>ok</title></html>")

    result = fetcher_with(monkeypatch, handler, settings).fetch("https://oferta.example/strona?x=1")
    assert result.status == 200 and result.final_url == "https://oferta.example/strona?x=1"
    assert seen == [("93.184.216.34", "oferta.example", "oferta.example")]
    assert calls["n"] == 1


def test_each_redirect_hop_is_checked_and_pinned(monkeypatch, settings):
    getaddrinfo, _ = fake_dns(["93.184.216.34", "10.0.0.5"])
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    def handler(request):
        return httpx.Response(302, headers={"location": "http://wewnetrzny.example/admin"})

    result = fetcher_with(monkeypatch, handler, settings).fetch("https://oferta.example/")
    assert "sieci niepublicznej" in result.error
    assert [hop.url for hop in result.chain] == ["https://oferta.example/"]


def test_ipv6_and_port_keep_host_header():
    target, headers, extensions = fetch.pinned_request("http://oferta.example:8080/a?b=1", "2001:db8::1")
    assert target == "http://[2001:db8::1]:8080/a?b=1"
    assert headers == {"Host": "oferta.example:8080"} and extensions == {}


def test_private_answer_is_refused_before_connecting(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns(["127.0.0.1"])[0])
    with pytest.raises(fetch.BlockedUrl):
        fetch.resolve_public("http://localhost.example/")
