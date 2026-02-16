# Imports
import sqlite3, sys

# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import DB_PATH, ASSOCIATE_RE, ASSOCIATION_TABLE_NAME, ASSOCIATION_COLUMNS, WORKS_TABLE_NAME, WORKS_COLUMNS
from sql_utils import * 

# Functions
def extract_associations(text):
    '''Extracting reading progress events from the body of an issue and from comments, as applicable; handles both.'''
    events = []
    text = text.strip()
    # Match
    m = ASSOCIATE_RE.match(text)
    if not m:
        return events
    rest = m.group(1)
    parts = [p.strip() for p in rest.split("/", maxsplit=3)]
    # Pad to ensure exactly 4 fields
    while len(parts) < 4:
        parts.append(None)
    events.append({
        "title": parts[0],
        "author": parts[1],
        "format": parts[2],
        "notes": parts[3]
    })
    return events

# Main
def main():
    # Connect to db
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Create (other) 'works' table
    cur.execute(
        sql_create_table_cmd(WORKS_TABLE_NAME, WORKS_COLUMNS)
    ) # References to works 'external' to the current books table
    # Create associations table
    cur.execute(
        sql_create_table_cmd(ASSOCIATION_TABLE_NAME, ASSOCIATION_COLUMNS)
    )
    # Commit
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()





