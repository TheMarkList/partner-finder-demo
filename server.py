"""
Partner Finder - the small local web server.

Start it with:   python3 server.py
Then open:       http://localhost:8000

It only listens on your own computer (not the internet).
It never sends messages to anyone. Press Control + C in the Terminal to stop it.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import db

HERE = Path(__file__).parent
PORT = 8000


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the Terminal quiet

    def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(200, (HERE / "screen.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/template.csv":
            self.send(200, (HERE / "template.csv").read_bytes(), "text/csv; charset=utf-8",
                      {"Content-Disposition": 'attachment; filename="partner-finder-template.csv"'})
        elif self.path == "/api/state":
            con = db.connect()
            self.send(200, db.get_state(con))
        else:
            self.send(404, {"error": "Not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            body = json.loads(raw) if raw else {}
            con = db.connect()
            p = self.path
            if p == "/api/owners":
                result = db.upsert_owner(con, body)
                msg = "Owner added." if result == "added" else "Already saved — numbers updated."
            elif p == "/api/import":
                r = db.import_csv(con, body.get("csv", ""))
                msg = f"Imported: {r['added']} added, {r['updated']} updated."
                if r["problems"]:
                    msg += " Problems: " + "; ".join(r["problems"])
            elif p == "/api/sample/load":
                n = db.load_samples(con)
                msg = f"Loaded {n} sample communities."
            elif p == "/api/sample/clear":
                n = db.clear_samples(con)
                msg = f"Removed {n} sample communities."
            elif p.startswith("/api/owners/"):
                db.update_owner(con, int(p.rsplit("/", 1)[1]),
                                status=body.get("status"), draft_message=body.get("draft_message"))
                msg = "Saved."
            elif p == "/api/scoreboard":
                db.update_scoreboard(con, body)
                msg = "Scoreboard updated."
            else:
                return self.send(404, {"error": "Not found"})
            self.send(200, {"message": msg, "state": db.get_state(con)})
        except (ValueError, json.JSONDecodeError) as e:
            self.send(400, {"error": str(e)})


if __name__ == "__main__":
    db.connect()  # creates partners.db if it isn't there yet
    print(f"Partner Finder is running. Open http://localhost:{PORT} in your browser.")
    print("Press Control + C here to stop it.")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
