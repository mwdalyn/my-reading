'''Triggered upon completion or a book; or, alternatively, triggered on workflow dispatch.
For books that are closed or status == "completed" and rating is missing, parse their comments and look for a comment
with the substring "rating:{}" and parse rating (out of 10) from {}.'''
# Imports
from datetime import datetime
from core.constants import * 

import os, re, json, sqlite3

# Constants
# DB_PATH = os.path.join("data", "reading.sqlite") # Doesn't work when defined here

# Functions
def extract_rating(comment_body):
    """Parse comment starting with 'rating:' and return a float 0-10."""
    match = re.match(r"^\s*rating\s*:\s*(\d+(?:\.\d+)?)", comment_body, re.IGNORECASE) # Looking for numeric after 'rating:' substring
    if match:
        val = float(match.group(1))
        if 0 <= val <= 10:
            return val
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
    # Get rating from comment body
    rating = extract_rating(comment_body)
    if rating is None:
        print("No valid rating found in comment, exiting.")
        return
    # Create 
    now = datetime.now().isoformat()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) # Add to ensure exists
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Ensure ratings table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER NOT NULL,
            rating REAL NOT NULL CHECK(rating >= 0 AND rating <= 10),
            created_on TEXT NOT NULL,
            updated_on TEXT NOT NULL,
            UNIQUE(issue_id)
        )
    """)
    # Insert or update rating
    cur.execute("""
        INSERT INTO ratings (issue_id, rating, created_on, updated_on)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(issue_id) DO UPDATE SET
            rating=excluded.rating,
            updated_on=excluded.updated_on
    """, (issue["id"], rating, now, now))
    # Commit close and report
    conn.commit()
    conn.close()
    print(f"Saved rating {rating} for issue {issue['number']}.")

if __name__ == "__main__":
    main()
