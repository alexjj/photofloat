"""A small local web server to preview the gallery.

For a real site, upload the site folder to any static web host instead.
"""

import os
import re
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


class Handler(SimpleHTTPRequestHandler):
    """Static file handler with HTTP Range support (Safari needs it for video)."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".json": "application/json",
        ".mp4": "video/mp4",
        ".js": "text/javascript",
    }
    mounts = {}

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        for prefix, target in self.mounts.items():
            if clean.startswith("/" + prefix + "/"):
                rest = clean[len(prefix) + 2:]
                base = super().translate_path("/" + rest)
                return os.path.join(target, os.path.relpath(base, self.directory))
        return super().translate_path(path)

    _range = None

    def send_head(self):
        self._range = None
        header = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not header or not os.path.isfile(path):
            return super().send_head()
        match = _RANGE.match(header.strip())
        size = os.path.getsize(path)
        if not match or (not match.group(1) and not match.group(2)):
            return super().send_head()
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else size - 1
        else:
            start = max(0, size - int(match.group(2)))
            end = size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.end_headers()
            return None
        f = open(path, "rb")
        f.seek(start)
        self._range = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(self._range))
        self.end_headers()
        return f

    def copyfile(self, source, outputfile):
        if self._range is None:
            return super().copyfile(source, outputfile)
        remaining = self._range
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def log_message(self, format, *args):
        pass


def serve(site, port, bind, albums, cache):
    site = os.path.abspath(site)
    if not os.path.isfile(os.path.join(site, "index.html")):
        raise SystemExit("%s doesn't look like the PhotoFloat web folder (no index.html)" % site)
    if not os.path.isfile(os.path.join(cache, "root.json")):
        print("Warning: no albums found in %s yet, run 'photofloat scan' first." % cache)
    mounts = {}
    # Albums and cache may live outside the site folder.
    for name, target in (("albums", albums), ("cache", cache)):
        target = os.path.abspath(target)
        if target != os.path.join(site, name):
            mounts[name] = target
    handler = partial(type("MountedHandler", (Handler,), {"mounts": mounts}), directory=site)
    server = ThreadingHTTPServer((bind, port), handler)
    host = "localhost" if bind in ("127.0.0.1", "0.0.0.0", "") else bind
    print("Serving %s at http://%s:%d/  (Ctrl+C to stop)" % (site, host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
