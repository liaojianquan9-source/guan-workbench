"""Same-origin access to the production engine from the existing workbench UI."""
import http.client
from urllib.parse import urlsplit


class SizedReader:
    def __init__(self, stream, size): self.stream, self.remaining = stream, size
    def read(self, size=-1):
        if self.remaining <= 0: return b''
        data = self.stream.read(min(self.remaining, size if size >= 0 else self.remaining))
        if not data: raise ValueError('上传未完成，请重试。')
        self.remaining -= len(data)
        return data


def proxy_production(handler):
    """Only a fixed loopback service is reachable; no caller-provided destinations."""
    parsed = urlsplit(handler.path)
    prefix = '/api/production/'
    if not parsed.path.startswith(prefix): raise ValueError('Invalid production route')
    suffix = parsed.path[len(prefix):]
    if not suffix or '..' in suffix or '\\' in suffix: raise ValueError('Invalid production route')
    target = '/api/' + suffix + (('?' + parsed.query) if parsed.query else '')
    headers = {}
    for name in ('Content-Type', 'Range', 'If-None-Match'):
        if handler.headers.get(name): headers[name] = handler.headers[name]
    body = None
    if handler.command in ('POST', 'PATCH'):
        length = handler.content_length()
        headers['Content-Length'] = str(length)
        body = SizedReader(handler.rfile, length)
    connection = http.client.HTTPConnection('127.0.0.1', 4183, timeout=180)
    started = False
    try:
        connection.request(handler.command, target, body=body, headers=headers)
        response = connection.getresponse()
        handler.send_response(response.status); started = True
        for name in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Cache-Control', 'Content-Disposition'):
            if response.getheader(name) is not None: handler.send_header(name, response.getheader(name))
        handler.send_header('X-Content-Type-Options', 'nosniff')
        handler.end_headers()
        if handler.command != 'HEAD':
            while True:
                chunk = response.read(256 * 1024)
                if not chunk: break
                handler.wfile.write(chunk)
    except (ConnectionError, TimeoutError, OSError, http.client.HTTPException):
        handler.close_connection = True
        if not started:
            handler.send_json(503, {'error': '制作服务暂未连接。请启动「观」本机服务；原视频、已有研究与草稿均已保留。', 'code':'production_unavailable'})
    finally: connection.close()
