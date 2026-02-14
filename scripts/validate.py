'''Validate entries in database against issue and event history.
TODO: Add a dry run mode that doesn't edit the db, just reports changes.
TODO: Add unit tests (yay!)
'''
# Imports
from datetime import date
from datetime import datetime
from collections import defaultdict
from functools import lru_cache
from dateutil.parser import parse as parse_date

import os, requests, sqlite3, sys

# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import * 

# Setup
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN not set")

if not GITHUB_REPOSITORY:
    raise RuntimeError("GITHUB_REPOSITORY not set")

# Reporting class for logging/stashing updates
class ValidationReport:
    def __init__(self):
        self.changes = defaultdict(list)

    def record(self, rule, table, identifier, column, old, new):
        self.changes[rule].append({
            "table": table,
            "id": identifier,
            "column": column,
            "old": old,
            "new": new,
        })

    def is_empty(self):
        return not any(self.changes.values())

    def to_markdown(self):
        lines = []
        lines.append("# Database Validation Report")
        lines.append("")
        lines.append(f"_Generated: {datetime.now().isoformat()}")
        lines.append("")

        if self.is_empty():
            lines.append("No changes were required.")
            return "\n".join(lines)

        for rule, items in self.changes.items():
            lines.append(f"## {rule}")
            lines.append("")
            for item in items:
                lines.append(f"- **Table:** `{item['table']}`")
                lines.append(f"  - **Row:** `{item['id']}`")
                lines.append(
                    f"  - `{item['column']}`: `{item['old']}` to `{item['new']}`"
                )
            lines.append("")

        return "\n".join(lines)

# Functions
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@lru_cache(maxsize=256) # Fetch each issue once per run, ISO dates
def get_issue_metadata(issue_number):
    '''Return a dict of issue history.'''
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO}/issues/{issue_number}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    resp = requests.get(url, headers=headers)
    resp.raise_for_status()

    issue = resp.json()

    created_at = issue["created_at"][:10]
    closed_at = issue["closed_at"][:10] if issue["closed_at"] else None

    return {
        "created_at": created_at,
        "closed_at": closed_at,
    }

## Fix table 'books'
def fix_books_dates(conn, report=None):
    cur = conn.cursor()
    books = cur.execute("SELECT * FROM books").fetchall()

    for book in books:
        updates = {}
        issue_meta = get_issue_metadata(book["issue_number"])

        # date_began
        if book["date_began"] is None:
            updates["date_began"] = issue_meta["created_at"]
            if report:
                report.record(
                    rule="Books: date_began backfill",
                    table="books",
                    identifier=f"issue_number={book['issue_number']}",
                    column="date_began",
                    old=None,
                    new=issue_meta["created_at"],
                )

        # date_ended
        if book["date_ended"] is None and book["status"] == "completed":
            updates["date_ended"] = issue_meta["closed_at"]
            if report:
                report.record(
                    rule="Books: date_ended backfill",
                    table="books",
                    identifier=f"issue_number={book['issue_number']}",
                    column="date_began",
                    old=None,
                    new=issue_meta["closed_at"],
                )

        # created_on
        if book["created_on"] is None and (book["date_began"] or updates.get("date_began")):
            updates["created_on"] = updates.get("date_began", book["date_began"])
            # TODO: Add report

        # updated_on
        if book["updated_on"] is None:
            if book["status"] == "completed":
                updates["updated_on"] = updates.get("date_ended", book["date_ended"])
                # TODO: Add report
            else:
                event = cur.execute(
                    """
                    SELECT date
                    FROM reading_events
                    WHERE issue_id = ?
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    (book["issue_id"],),
                ).fetchone()
                if event:
                    updates["updated_on"] = event["date"]
                    # TODO: Add report
        
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            cur.execute(
                f"UPDATE books SET {set_clause} WHERE issue_id = ?",
                (*updates.values(), book["issue_id"]),
            )
    print("Validated books table")

def calculate_word_count(conn, report=None):
    # Fetch all books without a word_count yet
    cur = conn.cursor()
    cur.execute("SELECT issue_id, width, length, total_pages FROM books WHERE word_count IS NULL")
    rows = cur.fetchall()
    # Calculate and apply
    for issue_id, width, length, total_pages in rows:
        words_est = ((width * 0.8) / (0.153 * 0.5 * 5.5)) * ((length * 0.75) / (0.153 * 1.3)) * total_pages
        cur.execute(
            "UPDATE books SET word_count = ? WHERE issue_id = ?",
            (round(words_est,0), issue_id)
        ) # TODO: Add report
    print("Word count estimates calculated and applied.")

## Fix table 'reading_events'
def fix_reading_events_dates(conn, report=None):
    cur = conn.cursor()
    today = date.today().isoformat()
    valid_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    # TODO: Try to enforce reacing_events datetime typing here
    cur.execute("""
        UPDATE reading_events
        SET created_on = date
        WHERE created_on IS NULL
        """)
    cur.execute(
        """
        UPDATE reading_events
        SET updated_on = COALESCE(date, ?)
        WHERE updated_on IS NULL
        """,
        (today,),
    )
    print("Fill NULL updated_ and created_on entries with date where missing.")

def ensure_page_one_events(conn, report=None):
    cur = conn.cursor()
    issues = cur.execute(
        "SELECT DISTINCT issue_id FROM reading_events"
    ).fetchall()

    for row in issues:
        issue_id = row["issue_id"]
        has_page_one = cur.execute(
            """
            SELECT 1 FROM reading_events
            WHERE issue_id = ? AND page = 1
            LIMIT 1
            """,
            (issue_id,),
        ).fetchone()

        if has_page_one:
            continue
        # If there is no "page 1" entry, create one on the first day of reading
        earliest = cur.execute(
            """
            SELECT * FROM reading_events
            WHERE issue_id = ?
            ORDER BY date ASC
            LIMIT 1
            """,
            (issue_id,),
        ).fetchone()

        if earliest: # Create earliest entry, set page = 1
            cur.execute(
                """
                INSERT INTO reading_events (source_id, issue_id, date, page, source, created_on, updated_on)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    ":".join(earliest["source"],str(issue_id),parse_date(earliest['date']).strftime("%Y-%m-%d") ,str(1)), # source_id convention
                    issue_id,
                    earliest["date"],
                    earliest["source"],
                    earliest["created_on"],
                    earliest["updated_on"],
                ),
            )
    print("Ensured all issues have page = 1 reading_events entry")

def ensure_page_final_events(conn, report=None):
    cur = conn.cursor()

    issues = cur.execute(
        """SELECT issue_id, total_pages, date_ended
           FROM books"""
    ).fetchall()

    for row in issues:
        issue_id = row["issue_id"]
        total_pages = row["total_pages"]
        date_ended = row["date_ended"]

        # Skip unfinished books
        if date_ended is None:
            continue

        # Check if final-page event already exists
        existing = cur.execute(
            """
            SELECT source_id FROM reading_events
            WHERE issue_id = ?
              AND page = ?
            LIMIT 1
            """,
            (issue_id, total_pages),
        ).fetchone()

        # Deterministic source_id (adjust convention as you like)
        source_id = f"final:{issue_id}:{total_pages}"

        if existing:
            # Ensure date matches books.date_ended
            cur.execute(
                """
                UPDATE reading_events
                SET date = ?, updated_on = DATETIME('now')
                WHERE source_id = ?
                """,
                (date_ended, existing["source_id"]),
            )
        else:
            # Insert final-page event
            cur.execute(
                """
                INSERT INTO reading_events
                (source_id, issue_id, date, page, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    issue_id,
                    date_ended,
                    total_pages,
                    "auto-finalize",
                ),
            )
    # Commit
    conn.commit()
    print("Ensured all finished books have final-page reading_events entry")


def ensure_source_id_reading_events(conn, report=None): # NOTE: This may not be needed; edge case arose 
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT * FROM reading_events WHERE source_id = NULL"
    ).fetchall()

    for row in rows:
        cur.execute(
            """
            INSERT INTO reading_events (source_id, issue_id, date, page, source, created_on, updated_on)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            """,
            (
                ":".join(row['source'],row['issue_id'],parse_date(row['date']).strftime("%Y-%m-%d"),str(row['page'])), # source_id convention
                row['issue_id'],
                row['date'],
                row['source'],
                row['created_on'],
                row['updated_on'],
            ),
        )
    print("Ensured all reading_events have proper source_id.")

def dedupe_reading_events(conn, report=None):
    cur = conn.cursor()
    duplicates = cur.execute(
        """
        SELECT issue_id, date, page, source, MAX(page) as max_page
        FROM reading_events
        GROUP BY issue_id, date, page, source
        HAVING COUNT(*) > 1
        """
    ).fetchall()

    for d in duplicates:
        cur.execute(
            """
            DELETE FROM reading_events
            WHERE issue_id = ?
              AND date = ?
              AND source = ?
              AND page < ?
            """,
            (d["issue_id"], d["date"], d["source"], d["max_page"]),
        ) # TODO: How to enter this in the report?
    print("Duplicate reading_events removed")


def main():
    conn = get_db()
    val_report = ValidationReport()  # Create report
    report_path = os.path.join("data", "validation_report.md")

    try:
        fix_books_dates(conn, report=val_report)
        calculate_word_count(conn)
        fix_reading_events_dates(conn)
        ensure_source_id_reading_events(conn)
        ensure_page_one_events(conn)
        ensure_page_final_events(conn) # New
        dedupe_reading_events(conn)

        conn.commit() # Commit; report has been written if this is all successful
        print("Database validation complete")

    except Exception as e:
        # Log a failure into the report
        val_report.record(
            rule="FATAL",
            table="N/A",
            identifier="validate.py",
            column="exception",
            old="none",
            new=str(e),
        )
        raise  # Write report even in failure

    finally:
        # Write the report regardless of content
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(val_report.to_markdown())
        # Close and show success
        conn.close()
        print(f"Validation report written to {report_path}")

if __name__ == "__main__":
    main()
