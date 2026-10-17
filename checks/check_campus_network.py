"""Exercise real local TLS and a recording proxy without school accounts or external requests."""
import os
import socket
import ssl
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from backend.services.auth import protocols


class Destination(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.seen.append(self.headers['Host'])
        if self.path in {'/school-redirect', '/external-redirect'}:
            self.send_response(302)
            self.send_header('Location', 'https://ids.shanghaitech.edu.cn/' if self.path == '/school-redirect'
                             else 'https://www.gradescope.com/')
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'synthetic campus response')


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        self.server.seen.append(self.path)
        self.send_error(502, 'Synthetic proxy refuses tunnels')


temporary = PROJECT / '.codex' / 'tmp'
temporary.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=temporary) as directory:
    certificate, private_key = Path(directory) / 'school.pem', Path(directory) / 'key.pem'
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Synthetic campus test')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('shanghaitech.edu.cn'),
                           x509.DNSName('*.shanghaitech.edu.cn')]), critical=False).sign(key, hashes.SHA256()))
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
    destination = ThreadingHTTPServer(('127.0.0.1', 0), Destination)
    proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, private_key)
    destination.socket = tls.wrap_socket(destination.socket, server_side=True)
    threads = []
    for server in (destination, proxy):
        server.seen = []
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        threads.append(worker)
    original_dns = socket.getaddrinfo

    def local_dns(host, port, *args, **kwargs):
        if host == 'shanghaitech.edu.cn' or host.endswith('.shanghaitech.edu.cn'):
            return original_dns('127.0.0.1', destination.server_port, *args, **kwargs)
        if host != '127.0.0.1':
            raise AssertionError('No external DNS is allowed in this regression')
        return original_dns(host, port, *args, **kwargs)

    proxy_variables = {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'ssl_cert_file', 'ssl_cert_dir'}
    env = {key: value for key, value in os.environ.items() if key.lower() not in proxy_variables}
    address = f'http://127.0.0.1:{proxy.server_port}'
    env.update(HTTP_PROXY=address, HTTPS_PROXY=address, ALL_PROXY=address, NO_PROXY='', SSL_CERT_FILE=str(certificate))
    try:
        with patch.dict(os.environ, env, clear=True), patch.object(socket, 'getaddrinfo', side_effect=local_dns):
            # Reproduce the original proxy failure before exercising the application policy.
            with httpx.Client(timeout=3) as client:
                try:
                    client.get('https://eams.shanghaitech.edu.cn/')
                    raise AssertionError('The environment proxy should have rejected this tunnel')
                except httpx.ProxyError:
                    pass
            proxy.seen.clear()
            with protocols.http_client() as client:
                for host in ('shanghaitech.edu.cn', 'eams.shanghaitech.edu.cn', 'elrc.shanghaitech.edu.cn',
                             'elearning.shanghaitech.edu.cn:8443', 'ids.shanghaitech.edu.cn', 'mail.shanghaitech.edu.cn'):
                    assert client.get('https://' + host + '/', timeout=3).text == 'synthetic campus response'
                assert not proxy.seen, 'Campus traffic must not reach the environment proxy'
                assert client.get('https://eams.shanghaitech.edu.cn/school-redirect', timeout=3).url.host == 'ids.shanghaitech.edu.cn'
                for url in ('https://www.gradescope.com/', 'https://piazza.com/',
                            'https://shanghaitech.edu.cn.example.org/', 'https://notshanghaitech.edu.cn/',
                            'https://eams.shanghaitech.edu.cn/external-redirect'):
                    try:
                        client.get(url, timeout=3)
                        raise AssertionError('External requests must retain the environment proxy')
                    except httpx.ProxyError:
                        pass
                assert len(proxy.seen) == 5
            # Direct routing must not disable certificate authentication.
            del os.environ['SSL_CERT_FILE']
            with protocols.http_client() as client:
                try:
                    client.get('https://eams.shanghaitech.edu.cn/', timeout=3)
                    raise AssertionError('An untrusted server certificate must be rejected')
                except httpx.ConnectError as error:
                    assert 'CERTIFICATE_VERIFY_FAILED' in str(error)
    finally:
        for server, worker in zip((destination, proxy), threads):
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

print('campus network: direct TLS, port 8443, redirects, external proxy, lookalike domains and CA verification passed')
