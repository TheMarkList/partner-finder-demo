"""
Partner Finder - the database and the fit score.

Everything is stored in one file: partners.db (in this folder).
It is created automatically the first time anything runs.

You can also run this file from the Terminal (the draft-outreach skill does this):
    python3 db.py top-new            -> shows the top 20 "New" owners
    python3 db.py save-drafts FILE   -> saves drafted messages from a JSON file
Nothing in this file ever sends a message to anyone.
"""

import csv
import io
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "partners.db"

STATUSES = ["New", "Drafted", "Approved", "Replied", "Signed"]
PLATFORMS = ["Skool", "Circle", "Discord", "Slack", "Facebook group", "Other"]

# The columns used by the "Add owner" form and the CSV template, in order.
FIELDS = ["community_name", "url", "platform", "owner_name", "niche",
          "member_count", "price", "posts_this_week"]


# ---------------------------------------------------------------- setup

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS owners (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            community_name  TEXT NOT NULL,
            url             TEXT,
            url_key         TEXT UNIQUE,      -- cleaned-up URL (or name), stops duplicates
            platform        TEXT,
            owner_name      TEXT,
            niche           TEXT,
            member_count    INTEGER,
            price           TEXT,
            posts_this_week INTEGER,
            fit_score       INTEGER,
            status          TEXT DEFAULT 'New',
            draft_message   TEXT,
            is_sample       INTEGER DEFAULT 0,
            date_found      TEXT,
            date_updated    TEXT
        );
        CREATE TABLE IF NOT EXISTS scoreboard (
            id                     INTEGER PRIMARY KEY CHECK (id = 1),
            owners_found           INTEGER DEFAULT 0,
            owners_signed          INTEGER DEFAULT 0,
            challenges_run         INTEGER DEFAULT 0,
            partners_signed        INTEGER DEFAULT 0,
            partners_at_10_per_month INTEGER DEFAULT 0,
            date_updated           TEXT
        );
        INSERT OR IGNORE INTO scoreboard (id, date_updated) VALUES (1, NULL);
    """)
    return con


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- fit score

COACH_WORDS = ["coach", "coaching", "mentor"]
CREATOR_WORDS = ["creator", "youtube", "content", "influencer"]
BUSINESS_WORDS = ["business", "agency", "entrepreneur", "marketing", "local business"]
SOCIAL_WORDS = ["social media"]
OFF_TOPIC_WORDS = ["crypto", "gaming", "forex", "betting", "nft"]


def score_parts(name, niche, members, posts):
    """Returns (total, activity, size, niche_points, matched_groups)."""
    # Activity: up to 40. 0 posts = 0 points, 10 or more posts a week = 40.
    posts = posts or 0
    activity = round(min(posts, 10) / 10 * 40)

    # Size: up to 20. Best between 100 and 5,000 members.
    if members is None:
        size = 10                     # unknown size gets half points
    elif 100 <= members <= 5000:
        size = 20
    elif 50 <= members < 100 or 5000 < members <= 20000:
        size = 12
    else:
        size = 5                      # very small (<50) or very large (>20,000)

    # Niche match: up to 40. Each matching group is 15 points, social media +10.
    text = f"{name or ''} {niche or ''}".lower()

    def has(words):
        return any(re.search(r"\b" + re.escape(w), text) for w in words)

    groups = []
    if has(OFF_TOPIC_WORDS):
        niche_pts = 0
        groups = ["off-topic"]
    else:
        niche_pts = 0
        for label, words, pts in [("coaches", COACH_WORDS, 15),
                                  ("creators", CREATOR_WORDS, 15),
                                  ("small business", BUSINESS_WORDS, 15),
                                  ("social media", SOCIAL_WORDS, 10)]:
            if has(words):
                niche_pts += pts
                groups.append(label)
        niche_pts = min(niche_pts, 40)

    total = activity + size + niche_pts
    if groups == ["off-topic"]:
        total = min(total, 20)        # off-topic communities always rank at the bottom
    return total, activity, size, niche_pts, groups


def why_this_owner(row):
    """Three plain-English bullets for the screen."""
    total, activity, size, niche_pts, groups = score_parts(
        row["community_name"], row["niche"], row["member_count"], row["posts_this_week"])
    posts = row["posts_this_week"] or 0
    members = row["member_count"]

    b1 = f"Activity {activity}/40: {posts} post{'s' if posts != 1 else ''} this week" + \
         (" — very active." if posts >= 10 else " — quiet." if posts < 3 else ".")
    if members is None:
        b2 = f"Size {size}/20: member count unknown."
    elif size == 20:
        b2 = f"Size {size}/20: {members:,} members — in the sweet spot (100–5,000)."
    else:
        b2 = f"Size {size}/20: {members:,} members — outside the 100–5,000 sweet spot."
    if groups == ["off-topic"]:
        b3 = "Niche 0/40: niche looks off-topic for us, so the whole score is capped at 20."
    elif groups:
        b3 = f"Niche {niche_pts}/40: matches {', '.join(groups)}."
    else:
        b3 = "Niche 0/40: no match with coaches, creators or small business."
    return [b1, b2, b3]


# ---------------------------------------------------------------- helpers

def to_int(value):
    """Turns '1,200' or ' 45 ' into a number. Blank or '—' becomes None."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s in ("", "-", "—"):
        return None
    try:
        return int(float(s))
    except ValueError:
        raise ValueError(f"'{value}' is not a number")


def make_key(url, name, platform):
    """Same community = same key, so it is only saved once."""
    if url and url.strip():
        u = url.strip().lower()
        u = re.sub(r"^https?://", "", u)
        u = re.sub(r"^www\.", "", u)
        return u.rstrip("/")
    return f"name:{(name or '').strip().lower()}|{(platform or '').strip().lower()}"


def sync_scoreboard(con):
    found = con.execute("SELECT COUNT(*) FROM owners").fetchone()[0]
    signed = con.execute("SELECT COUNT(*) FROM owners WHERE status='Signed'").fetchone()[0]
    con.execute("UPDATE scoreboard SET owners_found=?, owners_signed=?, date_updated=? WHERE id=1",
                (found, signed, now()))


# ---------------------------------------------------------------- actions

def upsert_owner(con, data, is_sample=False):
    """Adds a new owner, or updates the numbers if this community is already saved.
    Returns 'added' or 'updated'. Status and draft message are never overwritten."""
    name = (data.get("community_name") or "").strip()
    if not name:
        raise ValueError("Community name is required")
    url = (data.get("url") or "").strip()
    platform = (data.get("platform") or "").strip() or "Other"
    members = to_int(data.get("member_count"))
    posts = to_int(data.get("posts_this_week"))
    price = (data.get("price") or "").strip() or None
    owner_name = (data.get("owner_name") or "").strip() or None
    niche = (data.get("niche") or "").strip() or None
    score = score_parts(name, niche, members, posts)[0]
    key = make_key(url, name, platform)
    t = now()

    existing = con.execute("SELECT id FROM owners WHERE url_key=?", (key,)).fetchone()
    if existing:
        con.execute("""UPDATE owners SET community_name=?, url=?, platform=?, owner_name=?,
                       niche=?, member_count=?, price=?, posts_this_week=?, fit_score=?,
                       date_updated=? WHERE id=?""",
                    (name, url or None, platform, owner_name, niche, members, price, posts,
                     score, t, existing["id"]))
        result = "updated"
    else:
        con.execute("""INSERT INTO owners (community_name, url, url_key, platform, owner_name,
                       niche, member_count, price, posts_this_week, fit_score, status,
                       is_sample, date_found, date_updated)
                       VALUES (?,?,?,?,?,?,?,?,?,?, 'New', ?, ?, ?)""",
                    (name, url or None, key, platform, owner_name, niche, members, price,
                     posts, score, 1 if is_sample else 0, t, t))
        result = "added"
    sync_scoreboard(con)
    con.commit()
    return result


def import_csv(con, text):
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [f for f in FIELDS if f not in headers]
    if missing:
        raise ValueError("The CSV is missing these columns: " + ", ".join(missing))
    added = updated = 0
    problems = []
    for line_no, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): v for k, v in raw.items()}
        if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue  # skip blank lines
        try:
            if upsert_owner(con, row) == "added":
                added += 1
            else:
                updated += 1
        except ValueError as e:
            problems.append(f"Row {line_no}: {e}")
    return {"added": added, "updated": updated, "problems": problems}


SAMPLES = [
    ("Sample: Coach Growth Lab", "Skool", "Jamie Sample", "business coaching for new coaches", 820, "$49/month", 14),
    ("Sample: Creator Content Club", "Skool", "Riley Sample", "YouTube creators and content strategy", 2400, "$29/month", 9),
    ("Sample: Local Business Marketing Hub", "Circle", "Morgan Sample", "social media marketing for local business owners", 610, "$79/month", 6),
    ("Sample: Agency Owners Circle", "Skool", "Casey Sample", "agency owners and entrepreneurs", 4300, "$99/month", 4),
    ("Sample: Fitness Coach Collective", "Facebook group", "Taylor Sample", "fitness coaching", 15000, "Free", 22),
    ("Sample: Etsy Sellers Corner", "Discord", "Jordan Sample", "handmade online shop sellers", 300, "Free", 2),
    ("Sample: Crypto Moon Traders", "Skool", "Alex Sample", "crypto trading signals", 9000, "$199/month", 30),
    ("Sample: Tiny Podcast Starters", "Slack", "Sam Sample", "podcast content creators", 40, "$10/month", 1),
]


def load_samples(con):
    n = 0
    for i, (name, platform, owner, niche, members, price, posts) in enumerate(SAMPLES, start=1):
        upsert_owner(con, {"community_name": name, "url": f"https://example.com/sample-{i}",
                           "platform": platform, "owner_name": owner, "niche": niche,
                           "member_count": members, "price": price,
                           "posts_this_week": posts}, is_sample=True)
        n += 1
    return n


def clear_samples(con):
    n = con.execute("DELETE FROM owners WHERE is_sample=1").rowcount
    sync_scoreboard(con)
    con.commit()
    return n


def update_owner(con, owner_id, status=None, draft_message=None):
    if status is not None and status not in STATUSES:
        raise ValueError(f"Unknown status: {status}")
    row = con.execute("SELECT id FROM owners WHERE id=?", (owner_id,)).fetchone()
    if not row:
        raise ValueError("Owner not found")
    if status is not None:
        con.execute("UPDATE owners SET status=?, date_updated=? WHERE id=?", (status, now(), owner_id))
    if draft_message is not None:
        con.execute("UPDATE owners SET draft_message=?, date_updated=? WHERE id=?",
                    (draft_message, now(), owner_id))
    sync_scoreboard(con)
    con.commit()


def update_scoreboard(con, data):
    for col in ("challenges_run", "partners_signed", "partners_at_10_per_month"):
        if col in data:
            v = to_int(data[col])
            if v is None or v < 0:
                raise ValueError(f"{col} must be 0 or more")
            con.execute(f"UPDATE scoreboard SET {col}=?, date_updated=? WHERE id=1", (v, now()))
    con.commit()


def get_state(con):
    owners = []
    for r in con.execute("SELECT * FROM owners ORDER BY fit_score DESC, community_name"):
        d = dict(r)
        d["why"] = why_this_owner(r)
        owners.append(d)
    sb = dict(con.execute("SELECT * FROM scoreboard WHERE id=1").fetchone())
    last = con.execute("SELECT MAX(date_updated) FROM owners").fetchone()[0]
    return {"owners": owners, "scoreboard": sb, "last_updated": last or sb["date_updated"],
            "statuses": STATUSES, "platforms": PLATFORMS}


# ---------------------------------------------------------------- for the draft-outreach skill

def cli_top_new():
    con = connect()
    rows = con.execute("""SELECT id, community_name, platform, owner_name, niche, member_count,
                          price, posts_this_week, fit_score
                          FROM owners WHERE status='New'
                          ORDER BY fit_score DESC LIMIT 20""").fetchall()
    print(json.dumps([dict(r) for r in rows], indent=2))


def cli_save_drafts(path):
    """File format: {"12": "Hi Jamie, ...", "15": "..."}  (owner id -> message).
    Only owners still marked "New" are changed. Status becomes "Drafted"."""
    drafts = json.loads(Path(path).read_text())
    con = connect()
    saved, skipped = 0, []
    for owner_id, message in drafts.items():
        cur = con.execute("""UPDATE owners SET draft_message=?, status='Drafted', date_updated=?
                             WHERE id=? AND status='New'""", (message.strip(), now(), int(owner_id)))
        if cur.rowcount:
            saved += 1
        else:
            skipped.append(owner_id)
    sync_scoreboard(con)
    con.commit()
    print(f"Saved {saved} drafts. Skipped (not found or not 'New'): {skipped or 'none'}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "top-new":
        cli_top_new()
    elif len(sys.argv) >= 3 and sys.argv[1] == "save-drafts":
        cli_save_drafts(sys.argv[2])
    else:
        print(__doc__)
