'''Script to run with GitHub Actions in order to update database with new Issue interactions (publication, closure, comments).
Creates the database for books, reading progress.'''
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
## Error handling
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

# SQL setup
## Create tables
SQL_CREATE_BOOKS = """
    CREATE TABLE IF NOT EXISTS books (
        issue_id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        issue_number INTEGER,
        status TEXT,
        date_began TEXT,
        date_ended TEXT,
        publisher TEXT,
        year_published TEXT,
        year_edition TEXT,
        isbn TEXT,
        width REAL,
        length REAL,
        height REAL,
        total_pages INTEGER,
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
## Upsert into tables
SQL_UPSERT_BOOK = """
    INSERT INTO books (
        issue_id, title, author, issue_number, status,
        date_began, date_ended,
        publisher, year_published, year_edition, isbn, 
        width, length, height, total_pages,
        created_on, updated_on
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATE('now'), DATE('now'))
    ON CONFLICT(issue_id) DO UPDATE SET
        title=excluded.title,
        author=excluded.author,
        issue_number=excluded.issue_number,
        status=excluded.status,
        date_began=excluded.date_began,
        date_ended=excluded.date_ended,
        publisher=excluded.publisher,
        year_published=excluded.year_published,
        year_edition=excluded.year_edition,
        isbn=excluded.isbn,
        width=excluded.width,
        length=excluded.length,
        height=excluded.height,
        total_pages=excluded.total_pages,
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
## Set metadata options for additional Issue body context and tracking
BOOK_METADATA_KEYS = {
    "publisher",
    "year_published",
    "year_edition",
    "isbn",
    "width",
    "length",
    "height",
    "total_pages",
} # For use in extract_book_metadata; additional details I wanted to see in each Issue body (NOT reading events)

# Enable abandonment
ABANDON_KEYWORDS = {"abandon","give_up"}
AUTO_CLOSED_LABEL = "auto-closed" # For automatically closing books marked abandoned (and not going recursive)

# Functions
def parse_int(value):
    """Try to convert to integer; return None if invalid."""
    try:
        return int(value)
    except ValueError:
        return None

def parse_float(value):
    """Extract a float from a string; return None if invalid."""
    # Remove any non-numeric characters except dot or minus
    match = re.search(r"[-+]?\d*\.?\d+", value)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None

def parse_title(title):
    '''Simple title parse for each Issue.'''
    for sep in ["—", "-"]:
        if sep in title:
            t, a = title.split(sep, 1)
            return t.strip(), a.strip()
    return title.strip(), None

def extract_book_metadata(body):
    """Allow a preset list of properties to be defined for a book in its issue body. 
    Parse that data out separately from extract_events."""
    # Set NULL as column defaults
    metadata = {k: None for k in BOOK_METADATA_KEYS}
    if not body: # If no body content, continue with NULLs
        return metadata
    
    for line in body.splitlines(): # Iterate through lines
        line = line.strip()
        if not line: # Skip if now empty 
            continue
        if ":" not in line or line[0].isdigit(): # If no colon or if it is a date:page update, skip 
            continue
        # Begin parsing
        key, value = line.split(":", 1)
        key, value = key.strip().lower(), value.strip() # Set column header lowercase
        # Validate numeric inputs or otherwise pass value through
        if key in {"width", "length", "height"}:
            metadata[key] = parse_float(value)
        elif key == "total_pages":
            metadata[key] = parse_int(value)
        else: # Not numeric
            metadata[key] = value
    # Return
    return metadata

def extract_events(text, fallback_date, source, source_id):
    '''Extracting reading progress events from the body of an issue (if applicable) and from comments.'''
    events = []
    text = text.strip()
    # Handle content in issue body MMDDYYYY : PAGE
    m = DATED_PAGE_RE.match(text)
    if m:
        date = parse_date(f"{m.group(1)[:2]}/{m.group(1)[2:4]}/{m.group(1)[4:]}").date()
        events.append({
            "page": int(m.group(2)),
            "date": date,
            "source": source,
            "source_id": source_id
        })
        return events

    # Comment only PAGE
    m = PAGE_ONLY_RE.match(text)
    if m:
        events.append({
            "page": int(m.group(1)),
            "date": fallback_date,
            "source": source,
            "source_id": source_id})
        return events
    # Return events
    return events

def is_abandoned(text):
    """Return True if text contains any abandonment keyword (case-insensitive)."""
    text = text.lower()
    return any(keyword in text for keyword in ABANDON_KEYWORDS)

# Begin tasks
## Prepare by grabbing events (from local or from remote/issue history)
with open(EVENT_PATH) as f: # EVENT_PATH fixed to eq file path for events.json
    event = json.load(f)
headers = {
    "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN','')}",
    "Accept": "application/vnd.github+json"
}
## Grab issue
issue_url = event["issue"]["url"]
## Requests of GitHub (if token is set)
if os.environ.get("GITHUB_TOKEN"): # GitHub Actions
    issue_resp = requests.get(issue_url, headers=headers)
    issue_resp.raise_for_status()
    issue = issue_resp.json() # If not fail state, set issue as json response
    comments_resp = requests.get(issue["comments_url"], headers=headers)
    comments_resp.raise_for_status()
    comments = comments_resp.json() # If not fail state, set comments lsit as json response from comments_url 
else: # Local testing 
    issue = event["issue"] 
    comments = issue.get("comments",[]) 

## Set simple knowns
title, author = parse_title(issue["title"])

## Grab or set metadata
book_metadata = extract_book_metadata(issue.get("body", ""))

## Check if book has been auto-closed and quit if so
existing_labels = [l["name"].lower() for l in issue.get("labels", [])]
if AUTO_CLOSED_LABEL in existing_labels:
    print(f"Issue #{issue['number']} already auto-closed. Exit workflow.")
    exit(0)

## Mark book as abandoned and set flag; only care about comments
abandoned = False
# Check comments
for comment in comments:
    if is_abandoned(comment["body"]):
        abandoned = True
        break

## Log events
# Source: Issue (body, e.g. backdating progress if Issue wasn't published on book start date)
events = []
if issue.get("body"):
    for line in issue["body"].splitlines():
        line = line.strip()
        if not line:
            continue # Skip empty
        events_tmp = extract_events(
            text=line,
            fallback_date=parse_date(issue["created_at"]).date(),
            source="issue-body",
            source_id=None  # we’ll set it next
        )
        for e in events_tmp:
            # Construct deduplicated source_id
            e["source_id"] = f"issue:{issue['id']}:{e['date'].isoformat()}:{e['page']}"
            events.append(e)

# Source: Comments (e.g. need to handle page updates and log them as daily progress; robust to multiple comments per day)
# To make robust, check for previous comments in the day (requires setting the connection here rather than down the line)
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Check if all desired columns exist in the database
cur.execute("PRAGMA table_info(books)")
columns = [row[1] for row in cur.fetchall()]
for column in list(BOOK_METADATA_KEYS):
    if column not in columns:
        cur.execute(f"ALTER TABLE books ADD COLUMN {column} TEXT")
        print(f"Added column '{column}' to books table.")

# Create tables as normal (somewhat redundant; SQL contains condition of "if doesn't exist" already)
cur.execute(SQL_CREATE_BOOKS) # TODO: Want to get rid of this, is there another way to be robust?
cur.execute(SQL_CREATE_EVENTS) # TODO: Want to get rid of this, is there another way to be robust?

# Explore comments
for comment in comments:
    for line in comment["body"].splitlines():
        line = line.strip()
        if not line:
            continue # Skip empty
        events_tmp = extract_events(
            text=line,
            fallback_date=parse_date(comment["created_at"]).date(),
            source="comment",
            source_id=None
        )
        for e in events_tmp:
            # Check DB for existing event with same issue_id and date
            cur.execute("""
                SELECT source_id FROM reading_events
                WHERE issue_id=? AND date=?
            """, (issue['id'], e['date']))
            existing = cur.fetchone()
            if existing:
                e["source_id"] = existing[0]  # Overwrite (source_id = key)
            else:
                e["source_id"] = f"comment:{comment['id']}:{e['date'].isoformat()}:{e['page']}" # NOTE: May be able to enhance this for additional uniqueness?
            # Append
            events.append(e)
# Now you have an events list

# If abandoned and still open, auto-close the GitHub Issue *and* add label
if abandoned and issue["state"] != "closed" and os.environ.get("GITHUB_TOKEN"):
    # Close the issue
    resp = requests.patch(
        issue["url"],
        headers=headers,
        json={"state": "closed"}
    )
    resp.raise_for_status()
    # Add the auto-close label
    labels_url = issue["labels_url"]  # URL to manage labels
    resp_labels = requests.post(
        labels_url,
        headers=headers,
        json={"labels": [AUTO_CLOSED_LABEL]}
    )
    resp_labels.raise_for_status()
    # Print
    print(f"Issue #{issue['number']} marked as abandoned, closed, and labeled '{AUTO_CLOSED_LABEL}'.")

# Determine status before upsert
status = "abandoned" if abandoned else ("completed" if issue["state"] == "closed" else "reading")
# Upsert
cur.execute(SQL_UPSERT_BOOK, (
    issue["id"],
    title,
    author,
    issue["number"],
    status,
    None,   # date_began
    None,   # date_ended
    book_metadata["publisher"],
    book_metadata["year_published"],
    book_metadata["year_edition"],
    book_metadata["isbn"],
    book_metadata["width"],
    book_metadata["length"],
    book_metadata["height"],
    book_metadata["total_pages"],
))

# Upsert reading events
for e in events:
    cur.execute(SQL_UPSERT_EVENT, (
        e["source_id"],
        issue["id"],
        e["date"].isoformat(),
        e["page"],
        e["source"],
    ))

# End connection
conn.commit()
conn.close()