# Imports
import os, re, json, sqlite3

from datetime import datetime

from core.constants import DB_PATH 

# Constants
DB_PATH = os.path.join(os.getcwd(), DB_PATH) # Similar in function to Path usage in other files; uncertain about which I prefer
# TODO: Test and see if I can replace Path usage elsewhere with this; does it work locally?

# Main
def main():
    # Connect to db
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Create (other) 'works' table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS works (
            work_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT,
            work_type TEXT DEFAULT 'book',
            notes TEXT,
            created_on TEXT DEFAULT (DATETIME('now')),
            updated_on TEXT DEFAULT (DATETIME('now')),
        );
        """
    ) # References to works 'external' to the current books table
    # Create associations table
    cur.execute(
        """
        CREATE TABLE associations (
            association_id INTEGER PRIMARY KEY,
            source_work_id INTEGER NOT NULL,
            target_work_id INTEGER NOT NULL,
            page INTEGER,
            association_type TEXT,
            context TEXT,
            created_on TEXT DEFAULT (DATETIME('now')),
            updated_on TEXT DEFAULT (DATETIME('now')),
            FOREIGN KEY (source_work_id) REFERENCES books(issue_id),
            FOREIGN KEY (target_work_id) REFERENCES works(work_id)
        );
        """
    )

    # Commit
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()





