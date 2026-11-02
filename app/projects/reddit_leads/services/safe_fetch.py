"""Bounded public HTTP fetching, with DNS-pinned connections and checked redirects."""
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit, urlunsplit


class UnsafeURL(ValueError):
    pass


def public_target(url):
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURL('Provide a public HTTP or HTTPS website URL.')
    url = url.strip()
    if '://' not in url:
        url = 'https://' + url
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeURL('Only public HTTP and HTTPS URLs without credentials are allowed.')
    try:
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        host = parsed.hostname.encode('idna').decode('ascii')
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (ValueError, UnicodeError) as exc:
        raise UnsafeURL('Invalid website URL.') from exc
    # Refuse the whole hostname if any answer is private, loopback, link-local, or reserved.
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise UnsafeURL('Website URLs must resolve exclusively to public internet addresses.')
    return urlunsplit(parsed), parsed, host, port, addresses[0][4][0]


def fetch_public_text(url, timeout=6, max_bytes=1_000_000):
    for _ in range(6):
        url, parsed, host, port, address = public_target(url)
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
        # Pin the resolved public address so DNS cannot change between validation and connection.
        sock = socket.create_connection((address, port), timeout=timeout)
        try:
            if parsed.scheme == 'https':
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            connection.sock = sock
            target = parsed.path or '/'
            if parsed.query:
                target += '?' + parsed.query
            connection.request('GET', target, headers={'User-Agent': 'LeadsProProductResearch/1.0', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Redirect has no destination.')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError('Product website returned HTTP %s.' % response.status)
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError('Product website response is too large.')
            return body.decode('utf-8', errors='replace')
        finally:
            connection.close()
            sock.close()
    raise ValueError('Too many product website redirects.')
