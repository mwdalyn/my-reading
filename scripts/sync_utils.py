import json, os, requests, re
import sqlite3

from dateutil.parser import parse as parse_date
from dotenv import load_dotenv

from core.constants import * 

# Setup
def get_event_path():
    '''Trying to isolate the creation of the event_path, given it's not a constant; TODO: probably change variable case.'''
    EVENT_PATH = os.environ.get(GH_EVENT_PATH) or os.environ.get(GH_EVENT_PATH_TEST)
    ## Error handling
    if not EVENT_PATH:
        raise RuntimeError(
            "GITHUB_EVENT_PATH or GITHUB_TEST_EVENT_PATH not set. "
            "This script must be run inside GitHub Actions or with a mock event file.")
    if not os.path.exists(EVENT_PATH):
        raise RuntimeError(f"Event file not found at: {EVENT_PATH}")
    return EVENT_PATH

# Database path
def validate_db():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)

# def enforce_date_order(conn):
#     '''Preliminary for checking database and reporting on issues with columns.'''
#     cur = conn.cursor()
#     cur.execute("""
#         UPDATE books
#         SET date_ended = date_began
#         WHERE date_ended < date_began
#     """)

def fill_missing_created_on(conn, books_table="books", events_table="reading_events"):
    """Fill created_on if NULL for books table rows using the earliest of:
      (a) the book's date_began, or (b) the earliest associated reading_event date."""
    # Find all books where created_on is NULL
    cur = conn.cursor()
    cur.execute(f"SELECT issue_id, date_began FROM {books_table} WHERE created_on IS NULL")
    rows = cur.fetchall()
    # Iter
    for issue_id, date_began in rows:
        # Earliest associated reading_event
        cur.execute(f"SELECT MIN(date) FROM {events_table} WHERE issue_id = ?", (issue_id,))
        earliest_event = cur.fetchone()[0]  # Returns string date or None
        # Determine fill value
        fill_date = None
        if date_began and earliest_event:
            fill_date = min(date_began, earliest_event)
        elif date_began:
            fill_date = date_began
        elif earliest_event:
            fill_date = earliest_event
        
        if fill_date:
            cur.execute(f"""
                UPDATE {books_table}
                SET created_on = ?
                WHERE issue_id = ?
            """, (fill_date, issue_id))
    # Commit
    conn.commit()
    print(f"Filled created_on for {len(rows)} books where it was NULL.")
    
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

def is_abandoned(text):
    """Return True if text contains any abandonment keyword (case-insensitive)."""
    text = text.lower()
    return any(keyword in text for keyword in ABANDON_KEYWORDS)

def extract_book_metadata(body, ):
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
