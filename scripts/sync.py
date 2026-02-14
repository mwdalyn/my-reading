'''Script to run with GitHub Actions in order to update database with new Issue interactions (publication, closure, comments).
Creates the database for books, reading progress.'''
# Imports
import json, os, sqlite3, requests, sys

# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import * 
from sync_utils import * 

from dateutil.parser import parse as parse_date
from dotenv import load_dotenv
# Load environment vars
load_dotenv(dotenv_path=os.path.join(".env"))

def main():
    # Begin tasks
    ## Prepare by grabbing events (from local or from remote/issue history)
    event_path = get_event_path()
    with open(event_path) as f: # EVENT_PATH fixed to eq file path for events.json
        event = json.load(f)
    # Dump json to offline file
    dump_github_payload(event)
    # Set headers for .get()
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
        comments = comments_resp.json() # If not fail state, set comments list as json response from comments_url 
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
    abandoned = False # Necessary for later reference; default is False
    for comment in comments:
        if is_abandoned(comment["body"]):
            abandoned = True
            break # TODO: Revisit this; if abandoned, shouldn't this section auto-close the issue before continuing? Or should auto-close come after processing existing comments, content?
    
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
                fallback_date=None, # fallback_date is unused if event is issue-body update; but if there is an issue, should throw NULL
                source='issue-body',
                source_id=None  # Set source_id later
            )
            for e in events_tmp:
                print(e["date"])
                e_date = e['date'].strftime("%Y-%m-%d") # .replace(tzinfo=None).strftime("%Y-%m-%d") # source_id only accepts date not datetime for that portion of the assignment
                e["source_id"] = f"issue:{issue['id']}:{e_date}:{e['page']}" # Create source_id deduped
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
    # Parse datetimes
    issue_created_date = parse_date(issue["created_at"]).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    earliest_event_date_obj = parse_date(earliest_event_date).strftime("%Y-%m-%d %H:%M:%S") if earliest_event_date else None
    # TODO: Move this down to where date_began is created?

    # QA/QC: Infill missing created_on values for books table
    fill_missing_created_on(conn) # NOTE: TODO: This could likely be removed? Function duplicated by validate.py

    # Determine status before upsert
    status = "abandoned" if abandoned else ("completed" if issue["state"] == "closed" else "reading")
    
    # If abandoned and still open, auto-close the GitHub Issue and add label
    if status == "abandoned" and issue["state"] != "closed" and os.environ.get("GITHUB_TOKEN"):
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
            json={"labels": [AUTO_CLOSED_LABEL]} # TODO: Need to test; worry this would remove the 'reading' label as-is, want auto-closed to be additive 
        )
        resp_labels.raise_for_status()
        # Print
        print(f"Issue #{issue['number']} marked as abandoned, closed, and labeled '{AUTO_CLOSED_LABEL}'.")

    # Determine date_began and date_ended
    date_ended = parse_date(issue["closed_at"]).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S") if issue.get("closed_at") else None # TODO: Should change this so that it reflects when the 'done' comment is made; easy to forget to close it simultaneously
    # date_ended = date_ended.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S") if date_ended is not None else None

    # Compute date_began
    if earliest_event_date_obj:
        date_began = min(issue_created_date, earliest_event_date_obj)
    else:
        date_began = issue_created_date
    # date_began = date_began.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S") # Already added this conversion above, including again for security

    # Set up upsert(s)
    SQL_UPSERT_BOOK = sql_upsert("books", BOOKS_COLUMNS, "issue_id")
    ## Define and perform book upsert
    book_row = {
        "issue_id": issue["id"],
        "title": title,
        "author": author,
        "issue_number": issue["number"],
        "status": status,
        "date_began": date_began if date_began else None,
        "date_ended": date_ended if date_ended else None,
        **book_metadata, # Non-system columns; book metadata columns
        # NOTE: Removed both created_on and updated_on, this was causing problems by overwriting as None
    }
    ## Upsert, with 'created_on' enforced as None
    cur.execute(
        SQL_UPSERT_BOOK, 
        tuple(book_row.get(c) for c in BOOKS_COLUMNS if c != "created_on" and c!= "updated_on") # Unfortunate must-have; 19 bindings expected
    )

    # Events table updates
    ## Create events list
    ### Explore comments
    for comment in comments:
        for line in comment["body"].splitlines():
            line = line.strip()
            if not line:
                continue # Skip empty
            fallback = parse_date(comment["created_at"]).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
            events_tmp = extract_events(
                text=line,
                fallback_date=fallback, 
                source="comment",
                source_id=None
            )
            for e in events_tmp:
                # Check DB for existing event with same issue_id and date
                e_datetime = parse_date(e['date']).strftime("%Y-%m-%d %H:%M:%S") # Need timestamp for querying 'date' column in db
                e_date = parse_date(e['date']).strftime("%Y-%m-%d") # Don't need timestamp for setting 'source_id'
                cur.execute("""
                    SELECT source_id FROM reading_events
                    WHERE issue_id=? AND date=? AND page=? and source=?
                """, (issue['id'], e_datetime, e['page'], e['source'])) # Datetime goes into table as 'date'
                existing = cur.fetchone()
                if existing:
                    e["source_id"] = existing[0]  # Overwrite (source_id = key)
                else:
                    e["source_id"] = f"comment:{comment['id']}:{e_date}:{e['page']}" # NOTE: May be able to enhance this for additional uniqueness?
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
            "date": e['date'],
            "page": e["page"],
            "source": e["source"],
            # NOTE: Removed both created_on and updated_on, this was causing problems by overwriting as None
        }

        # Upsert events
        # event_row['created_on'] = None  # Confusing but: must do this to ensure bindings match; SQL reads this the same as though nothing was provided, so default is set/applied; created_on is handled in the upsert in a way that you don't have to worry about overwriting when using this solution
        cur.execute(
            SQL_UPSERT_EVENT,
            tuple(event_row.get(c) for c in READING_EVENTS_COLUMNS  if c != "created_on" and c != "updated_on")
        )

    # End connection
    conn.commit()
    conn.close()

# Execute
if __name__ == "__main__":
    main()