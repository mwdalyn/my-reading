import sqlite3, sys

###################
# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import * 
####################

# TODO: Add upsert functionality so that changing the calendar end date constant allows for new rows to be added
def main():
    # Connect to db
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Set calendar table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar (
            date TEXT PRIMARY KEY,
            year INTEGER NOT NULL
        );
        """
    )
    # Populate table using recursive CTE
    cur.execute(
        """
        WITH RECURSIVE dates(d) AS (
            SELECT date(?) 
            UNION ALL
            SELECT date(d, '+1 day')
            FROM dates
            WHERE d < date(?)
        )
        INSERT OR IGNORE INTO calendar(date, year)
        SELECT
            d,
            CAST(strftime('%Y', d) AS INTEGER)
        FROM dates;
        """,
        (CALENDAR_START, CALENDAR_END)
    )

    # Commit
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()