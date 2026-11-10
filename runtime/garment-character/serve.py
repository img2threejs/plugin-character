#!/usr/bin/env python3
"""Static server for the viewer that forbids caching, so a rebuilt viewer is never served stale."""
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class NoStore(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18773
    ThreadingHTTPServer(("127.0.0.1", port), NoStore).serve_forever()
