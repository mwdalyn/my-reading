'''Triggered upon completion or a book; or, alternatively, triggered on workflow dispatch.
For books that are closed or status == "completed" and review is missing, parse their comments and look for a comment
with the substring "review:{}" and parse the review text from {}. Must handle multiline reviews neatly.'''
# Imports
import os, re, json, sqlite3, sys

from datetime import datetime

###################
# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import * 
####################

# Functions
def extract_review(comment_body):
    """Parse comment starting with 'review:' and return all text following it as a single string (including newlines)."""
    match = re.match(r"^\s*review\s*:\s*(.*)", comment_body, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).rstrip()
    return None

def main():
    # GitHub sends payload via env or stdin (depends on workflow)
    event_path = os.environ.get("GITHUB_EVENT_PATH", "event.json")
    with open(event_path) as f:
        payload = json.load(f)

    comment_body = payload["comment"]["body"]
    issue = payload["issue"]

    # Only proceed if issue is closed and labeled 'reading'
    labels = [l["name"].lower() for l in issue.get("labels", [])]
    if issue["state"] != "closed" or "reading" not in labels:
        print("Issue not closed or not labeled 'reading', exiting.")
        return
    # Get review text (all) from comment body
    review = extract_review(comment_body)
    if review is None:
        print("No valid review found, exiting.")
        return
    # Create 
    now = datetime.now().isoformat()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) # Add to ensure exists
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Ensure ratings table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER NOT NULL,
            review TEXT NOT NULL,
            created_on TEXT DEFAULT (DATETIME('now')),
            updated_on TEXT DEFAULT (DATETIME('now')),
            UNIQUE(issue_id)
        )
    """)
    # Insert or update rating
    cur.execute("""
        INSERT INTO reviews (issue_id, review, created_on, updated_on)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(issue_id) DO UPDATE SET
            review=excluded.review,
            updated_on=excluded.updated_on
    """, (issue["id"], review, now, now))
    # Commit close and report
    conn.commit()
    # Report out tables to confirm:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()
    print("Tables in DB:", tables)
    # Close
    conn.close()
    print(f"Saved review {review} for issue {issue['number']}.")

if __name__ == "__main__":
    main()
