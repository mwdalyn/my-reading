'''Script to run with GitHub Actions in order to update database with new Issue interactions (publication, closure, comments).
Creates the database for books, reading progress.'''
# Imports
import json, os, requests, re
import sqlite3

from dateutil.parser import parse as parse_date
from dotenv import load_dotenv

from sync_utils import * 
from core.constants import * 

# Load environment vars
load_dotenv(dotenv_path=os.path.join(".env"))

def main():
    # Begin tasks
    ## Validate or create db
    validate_db()
    ## Prepare by grabbing events (from local or from remote/issue history)
    event_path = get_event_path()
    with open(event_path) as f: # EVENT_PATH fixed to eq file path for events.json
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
    # Check comments
    for comment in comments:
        if is_abandoned(comment["body"]):
            abandoned = True
            break
        else:
            abandoned = False

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

    ## Books table updates
    # Ensure date_began and date_ended are reflected correctly.
    cur.execute("""
        SELECT MIN(date) FROM reading_events WHERE issue_id=?
    """, (issue["id"],))
    earliest_event_date = cur.fetchone()[0]  # Returns a string date or None
    # Parse dates
    issue_created_date = parse_date(issue["created_at"]).date()
    earliest_event_date_obj = parse_date(earliest_event_date).date() if earliest_event_date else None

    # QA/QC: Infill missing created_on values for books table
    fill_missing_created_on(conn)

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

    # Determine date_began and date_ended
    date_ended = parse_date(issue["closed_at"]).date() if issue.get("closed_at") else None
    
    # Compute date_began
    if earliest_event_date_obj:
        date_began = min(issue_created_date, earliest_event_date_obj)
    else:
        date_began = issue_created_date
    
    # Set up upsert(s)
    SQL_UPSERT_BOOK = sql_upsert("books", BOOKS_COLUMNS, "issue_id")
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

    ## Events table updates
    # Create events list
    ## Explore comments
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

    ## Perform events upsert
    SQL_UPSERT_EVENT = sql_upsert("reading_events", READING_EVENTS_COLUMNS, "source_id")
    # Iterate 
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

# Execute
if __name__ == "__main__":
    main()