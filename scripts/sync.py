'''Script to run with GitHub Actions in order to update database with new Issue interactions (publication, closure, comments).
Creates the database for books, reading progress.'''
# Imports
import json, os, requests, re
import sqlite3

from dateutil.parser import parse as parse_date
from dotenv import load_dotenv

# Load environment vars
load_dotenv(dotenv_path=os.path.join(".env"))

# Constants 
PAGE_ONLY_RE = re.compile(r"^\s*(\d+)\s*$") 
DATED_PAGE_RE = re.compile(r"^\s*(\d{8})\s*:\s*(\d+)\s*$")
## SQL automation
BOOKS_COLUMNS = {
    "issue_id": "INTEGER PRIMARY KEY",
    "title": "TEXT", # Issue title
    "author": "TEXT", # Issue title
    "issue_number": "INTEGER",
    "status": "TEXT", # Set automatically upon sync workflow, script based on issue status and comments
    "date_began": "TEXT",
    "date_ended": "TEXT",
    "publisher": "TEXT",
    "year_published": "TEXT",
    "year_edition": "TEXT",
    "isbn": "TEXT",
    "width": "REAL",
    "length": "REAL",
    "height": "REAL",
    "total_pages": "INTEGER",
    ## 
    "translator": "TEXT", # last_name, first_name
    "collection": "INTEGER", # 1 = 'TRUE' = collection of (short) stories; 0 = 'FALSE' = novel
    ##
    "created_on": "TEXT DEFAULT (DATE('now'))",
    "updated_on": "TEXT DEFAULT (DATE('now'))",
} # All BOOKS table columns including system columns (e.g. not about the book, about the entry of the book into the table)
BOOK_SYSTEM_COLUMNS = {
    "issue_id",
    "title",
    "author",
    "issue_number",
    "status",
    "date_began",
    "date_ended",
    "created_on",
    "updated_on",
} # Provided in EVERY case by the creation of a book issue, updated as changes are made to the issue
BOOK_METADATA_KEYS = {
    col for col in BOOKS_COLUMNS
    if col not in BOOK_SYSTEM_COLUMNS
} # This captures everything "else;" everything that's added into the body of the issue not explicitly defined above
READING_EVENTS_COLUMNS = {
    "source_id": "TEXT PRIMARY KEY", 
    "issue_id": "INTEGER",
    "date": "TEXT",
    "page": "INTEGER",
    "source": "TEXT",
    "created_on": "TEXT DEFAULT (DATE('now'))",
    "updated_on": "TEXT DEFAULT (DATE('now'))",
}

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

# Enable abandonment
ABANDON_KEYWORDS = {"abandon","give_up"}
AUTO_CLOSED_LABEL = "auto-closed" # For automatically closing books marked abandoned (and not going recursive)

# Functions
## Custom SQL generation functions
def sql_create_table(table_name, columns):
    '''Creating a SQL table not with a fixed command, but with dynamic input.'''
    cols = ",\n    ".join(f"{name} {ctype}" for name, ctype in columns.items())
    command = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {cols}
        )
        """
    return command

def sql_upsert(table, columns, conflict_key):
    '''Upserting dynamically as well.'''
    col_names = list(columns.keys())
    insert_cols = ", ".join(col_names)
    placeholders = ", ".join("?" for _ in col_names)
    update_cols = ", ".join(
        f"{c}=excluded.{c}"
        for c in col_names
        if c not in {conflict_key, "created_on", "updated_on"}
    )
    command = f"""
        INSERT INTO {table} ({insert_cols})
        VALUES ({placeholders})
        ON CONFLICT({conflict_key}) DO UPDATE SET
            {update_cols},
            updated_on = DATE('now') 
        """ # Updated_on is refreshed here
    return command

def ensure_columns(cur, table_name, columns):
    '''Checking existing tables and ensure/adding columns, allows for dynamic input.'''
    cur.execute(f"PRAGMA table_info({table_name})")
    existing = {row[1] for row in cur.fetchall()}
    # Iterate
    for name, ctype in columns.items():
        if name not in existing:
            cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {ctype}")

## Other functions
def parse_int(value):
    """Try to convert to integer; return None if invalid."""
    try:
        return int(value)
    except ValueError:
        return None

def parse_float(value):
    """Extract a float from a string; return None if invalid."""
    match = re.search(r"[-+]?\d*\.?\d+", value) # Remove any non-numeric characters except dot or minus
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
        if not line or ":" not in line or line[0].isdigit(): # If no colon or if it is a date:page update, skip 
            continue
        # Begin parsing
        key, value = line.split(":", 1)
        key, value = key.strip().lower(), value.strip() # Set column header lowercase
        # Skip if key (column) not provided in BOOK_COLUMNS (BOOK_METADATA_KEYS)
        if key not in BOOK_METADATA_KEYS:
            continue
        # Data type handling
        sql_type = BOOKS_COLUMNS[key].upper()
        # Validate numeric inputs or otherwise pass value through
        if "REAL" in sql_type:
            metadata[key] = parse_float(value)
        elif "INTEGER" in sql_type:
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
            continue # Skip empty lines
        events_tmp = extract_events(
            text=line,
            fallback_date=parse_date(issue["created_at"]).date(),
            source="issue-body",
            source_id=None  # Set sourde_id later
        )
        for e in events_tmp:
            e["source_id"] = f"issue:{issue['id']}:{e['date'].isoformat()}:{e['page']}" # Create source_id deduped
            events.append(e)

# Source: Comments (e.g. need to handle page updates and log them as daily progress; robust to multiple comments per day)
# To make robust, check for previous comments in the day (requires setting the connection here rather than down the line)
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Create tables as normal (somewhat redundant; SQL contains condition of "if doesn't exist" already)
cur.execute(sql_create_table("books", BOOKS_COLUMNS)) # New: for dynamic column addition
cur.execute(sql_create_table("reading_events", READING_EVENTS_COLUMNS)) # New: for dynamic column addition

# Add check to confirm all columns are OK
ensure_columns(cur, "books", BOOKS_COLUMNS)
ensure_columns(cur, "reading_events", READING_EVENTS_COLUMNS)

# Ensure date_began and date_ended are reflected correctly.
cur.execute("""
    SELECT MIN(date) FROM reading_events WHERE issue_id=?
""", (issue["id"],))
earliest_event_date = cur.fetchone()[0]  # Returns a string date or None
# Parse dates
issue_created_date = parse_date(issue["created_at"]).date()
earliest_event_date_obj = parse_date(earliest_event_date).date() if earliest_event_date else None

# Compute date_began
if earliest_event_date_obj:
    date_began = min(issue_created_date, earliest_event_date_obj)
else:
    date_began = issue_created_date

# Compute date_ended
date_ended = parse_date(issue["closed_at"]).date() if issue.get("closed_at") else None


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

# Set up upsert(s)
SQL_UPSERT_BOOK = sql_upsert("books", BOOKS_COLUMNS, "issue_id")
SQL_UPSERT_EVENT = sql_upsert("reading_events", READING_EVENTS_COLUMNS, "source_id")
## Define and perform book upsert
book_row = {
    "issue_id": issue["id"],
    "title": title,
    "author": author,
    "issue_number": issue["number"],
    "status": status,
    "date_began": date_began.isoformat(),
    "date_ended": date_ended.isoformat() if date_ended else None,
    **book_metadata, # Non-system columns; book metadata columns
    # NOTE: Removed both created_on and updated_on, this was causing problems by overwriting as None
}
## Upsert
cur.execute(
    SQL_UPSERT_BOOK, 
    # tuple(book_row[c] for c in BOOKS_COLUMNS)) # Remove for testing 
    tuple(book_row.get(c) for c in BOOKS_COLUMNS))

## Perform events upsert
for e in events:
    event_row = {
        "source_id": e["source_id"],
        "issue_id": issue["id"],
        "date": e["date"].isoformat(),
        "page": e["page"],
        "source": e["source"],
        # NOTE: Removed both created_on and updated_on, this was causing problems by overwriting as None
    }
    # Upsert events
    cur.execute(
        SQL_UPSERT_EVENT,
        tuple(event_row[col] for col in READING_EVENTS_COLUMNS)
    )

# End connection
conn.commit()
conn.close()