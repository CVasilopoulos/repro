import asyncio

from gate.gate import Gate, Ledger, decide, host_allowed, parse_allowlist

ALLOW = parse_allowlist("github.com,pypi.org,files.pythonhosted.org")


def fake_resolver(table):
    def resolve(host, port):
        if host not in table:
            raise OSError("no such host")
        return table[host]
    return resolve


def test_allowlisted_host_with_public_address_is_allowed():
    d = decide("github.com", 443, ALLOW, fake_resolver({"github.com": ["140.82.121.4"]}))
    assert d.allowed and d.address == "140.82.121.4"


def test_subdomains_of_allowlisted_hosts_are_allowed():
    assert host_allowed("api.github.com", ALLOW)
    assert not host_allowed("github.com.evil.example", ALLOW)
    assert not host_allowed("notgithub.com", ALLOW)


def test_metadata_endpoint_by_ip_is_denied_with_its_own_reason():
    d = decide("169.254.169.254", 80, ALLOW, fake_resolver({}))
    assert not d.allowed and d.reason == "cloud metadata endpoint"


def test_raw_public_ip_is_denied():
    d = decide("1.1.1.1", 443, ALLOW, fake_resolver({}))
    assert not d.allowed and "raw IP" in d.reason


def test_host_not_on_allowlist_is_denied():
    d = decide("pastebin.com", 443, ALLOW, fake_resolver({"pastebin.com": ["104.20.67.143"]}))
    assert not d.allowed and d.reason == "host not on the allowlist"


def test_allowlisted_name_resolving_to_private_address_is_denied():
    d = decide("pypi.org", 443, ALLOW, fake_resolver({"pypi.org": ["10.0.0.5"]}))
    assert not d.allowed and "private address" in d.reason


def test_allowlisted_name_resolving_to_metadata_is_denied():
    d = decide("pypi.org", 443, ALLOW, fake_resolver({"pypi.org": ["169.254.169.254"]}))
    assert not d.allowed and "metadata" in d.reason


def test_non_web_ports_are_denied():
    d = decide("github.com", 22, ALLOW, fake_resolver({"github.com": ["140.82.121.4"]}))
    assert not d.allowed and "port 22" in d.reason


def test_loopback_and_ipv6_link_local_are_denied():
    assert decide("127.0.0.1", 80, ALLOW, fake_resolver({})).reason == "loopback address"
    assert decide("[fe80::1]", 80, ALLOW, fake_resolver({})).reason == "link-local address"


def test_denied_connect_gets_403_and_a_ledger_line(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"

    async def scenario():
        gate = Gate(ALLOW, Ledger(str(ledger_path)), resolve=fake_resolver({}))
        server = await asyncio.start_server(gate.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"CONNECT 169.254.169.254:80 HTTP/1.1\r\nHost: 169.254.169.254:80\r\n\r\n")
        await writer.drain()
        data = await reader.read(1000)
        writer.close()
        server.close()
        return data

    data = asyncio.run(scenario())
    assert data.startswith(b"HTTP/1.1 403")
    assert b"cloud metadata endpoint" in data
    line = ledger_path.read_text().strip()
    assert '"allowed": false' in line and '"host": "169.254.169.254"' in line


def test_plain_http_to_unlisted_host_is_refused(tmp_path):
    async def scenario():
        gate = Gate(ALLOW, Ledger(None), resolve=fake_resolver({"example.com": ["93.184.215.14"]}))
        server = await asyncio.start_server(gate.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET http://example.com/x HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await writer.drain()
        data = await reader.read(1000)
        writer.close()
        server.close()
        return data

    assert b"host not on the allowlist" in asyncio.run(scenario())
