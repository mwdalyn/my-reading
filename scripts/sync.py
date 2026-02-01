'''

'''
# Imports
import json, os, requests, re
import sqlite3

from dateutil.parser import parse as parse_date
from dotenv import load_dotenv

# Constants 
PAGE_ONLY_RE = re.compile(r"^\s*(\d+)\s*$")
DATED_PAGE_RE = re.compile(r"^\s*(\d{8})\s*:\s*(\d+)\s*$")

# Load environment vars
load_dotenv(dotenv_path=os.path.join(".env"))

# Event path
EVENT_PATH = os.environ.get("GITHUB_EVENT_PATH") or os.environ.get("GITHUB_TEST_EVENT_PATH")

if not EVENT_PATH:
    raise RuntimeError(
        "GITHUB_EVENT_PATH or GITHUB_TEST_EVENT_PATH not set. "
        "This script must be run inside GitHub Actions or with a mock event file.")
if not os.path.exists(EVENT_PATH):
    raise RuntimeError(f"Event file not found at: {EVENT_PATH}")

# Database path
DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR,"reading.sqlite")
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

# Set SQL queries and statements
SQL_CREATE_BOOKS = """
    CREATE TABLE IF NOT EXISTS books (
        issue_id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        issue_number INTEGER,
        status TEXT,
        date_began TEXT,
        date_ended TEXT,
        created_on TEXT DEFAULT (DATE('now')),
        updated_on TEXT DEFAULT (DATE('now'))
    )"""

SQL_CREATE_EVENTS = """
    CREATE TABLE IF NOT EXISTS reading_events (
        source_id TEXT PRIMARY KEY,
        issue_id INTEGER,
        date TEXT,
        page INTEGER,
        source TEXT,
        created_on TEXT DEFAULT (DATE('now')),
        updated_on TEXT DEFAULT (DATE('now'))
    )
"""

SQL_UPSERT_BOOK = """
    INSERT INTO books (issue_id, title, author, issue_number, status, date_began, date_ended, created_on, updated_on)
    VALUES (?, ?, ?, ?, ?, ?, ?, DATE('now'), DATE('now'))
    ON CONFLICT(issue_id) DO UPDATE SET
        title=excluded.title,
        author=excluded.author,
        issue_number=excluded.issue_number,
        status=excluded.status,
        date_began=excluded.date_began,
        date_ended=excluded.date_ended,
        updated_on=DATE('now')
"""

SQL_UPSERT_EVENT = """
    INSERT INTO reading_events (source_id, issue_id, date, page, source, created_on, updated_on)
    VALUES (?, ?, ?, ?, ?, DATE('now'), DATE('now'))
    ON CONFLICT(source_id) DO UPDATE SET
        date=excluded.date,
        page=excluded.page,
        source=excluded.source,
        updated_on=DATE('now')
"""


# Functions
def parse_title(title):
    '''Simple title parse for each Issue.'''
    for sep in ["—", "-"]:
        if sep in title:
            t, a = title.split(sep, 1)
            return t.strip(), a.strip()
    return title.strip(), None

def extract_events(text, fallback_date, source, source_id):
    '''Extracting events from the body of an issue (if applicable) and from comments.'''
    events = []
    text = text.strip()

    # Handle backdated content in issue body MMDDYYYY : PAGE
    m = DATED_PAGE_RE.match(text)
    if m:
        # date = parse_date(m.group(1)).date()
        date = parse_date(f"{m.group(1)[:2]}/{m.group(1)[2:4]}/{m.group(1)[4:]}").date()
        page = int(m.group(2))
        events.append({
            "page": page,
            "date": date,
            "source": source,
            "source_id": source_id
        })
        return events

    # Comment only PAGE
    m = PAGE_ONLY_RE.match(text)
    if m:
        page = int(m.group(1))
        events.append({
            "page": page,
            "date": fallback_date,
            "source": source,
            "source_id": source_id})
        return events
    # Return events
    return events

## Body
# Prepare
with open(EVENT_PATH) as f: # EVENT_PATH fixed to eq file path for events.json
    event = json.load(f)
headers = {
    "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN','')}",
    "Accept": "application/vnd.github+json"
}
# Get issue
issue_url = event["issue"]["url"]
# Requests of GitHub (if token is set)
if os.environ.get("GITHUB_TOKEN"): # GitHub Actions
    issue_resp = requests.get(issue_url, headers=headers)
    issue_resp.raise_for_status()
    issue = issue_resp.json()
    comments_resp = requests.get(issue["comments_url"], headers=headers)
    comments_resp.raise_for_status()
    comments = comments_resp.json()
else: # Local testing 
    issue = event["issue"] 
    comments = issue.get("comments",[]) 

# Set (simple) knowns
title, author = parse_title(issue["title"])

# Log events
# Issue body text
events = []
if issue.get("body"):
    for line in issue["body"].splitlines():
        line = line.strip()
        if not line:
            continue # Skip empty
        events_tmp = extract_events(
            text=line,
            fallback_date=parse_date(issue["created_at"]).date().isoformat(),
            source="issue-body",
            source_id=None  # we’ll set it next
        )
        for e in events_tmp:
            # Construct deduplicated source_id
            e["source_id"] = f"issue:{issue['id']}:{e['date'].isoformat()}:{e['page']}"
            events.append(e)
# Comments
for comment in comments:
    for line in comment["body"].splitlines():
        line = line.strip()
        if not line:
            continue # Skip empty
        events_tmp = extract_events(
            text=line,
            fallback_date=parse_date(comment["created_at"]).date().isoformat(),
            source="comment",
            source_id=None
        )
        for e in events_tmp:
            e["source_id"] = f"comment:{comment['id']}:{e['date'].isoformat()}:{e['page']}"
            events.append(e)

# Now have events list
## Push to database
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
# Create tables
cur.execute(SQL_CREATE_BOOKS)
cur.execute(SQL_CREATE_EVENTS)

# Upsert book
cur.execute(SQL_UPSERT_BOOK, (
    issue["id"],
    title,
    author,
    issue["number"],
    "completed" if issue["state"] == "closed" else "reading",
    None,   # date_began
    None    # date_ended
))

# Upsert reading events
for e in events:
    cur.execute(SQL_UPSERT_EVENT, (
        e["source_id"],
        issue["id"],
        e["date"],
        e["page"],
        e["source"],
    ))
# End connection
conn.commit()
conn.close()

