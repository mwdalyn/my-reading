'''Script to run with GitHub Actions (less frequent) that sets or updates reading_goals table.'''
# Imports
import os, sys, sqlite3

# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import * 

# Functions
def parse_goal_files():
    '''TEMPORARY: Using the set_goals.txt to update the db, read this and update.'''
    goals = []

    if not os.path.isdir(GOALS_DIR):
        return goals

    for filename in os.listdir(GOALS_DIR):
        if not filename.endswith(".txt"):
            continue

        path = os.path.join(GOALS_DIR, filename)
        data = {}

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                # Skip blanks and comments
                if not line or line.startswith("#"):
                    continue

                # Remove inline comments
                if "#" in line:
                    line = line.split("#", 1)[0].strip()
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()
        # Use filename (without .txt) as stable identity
        data["goal_id"] = os.path.splitext(filename)[0]
        goals.append(data)
    # Return
    return goals

def ensure_table_and_columns(conn):
    '''Create table and check existing columns, alter if necessary.'''
    # Connect
    cur = conn.cursor()
    # Create table if it doesn't exist
    column_defs = ", ".join(
        "{} {}".format(col, dtype) for col, dtype in GOAL_COLUMNS.items()
    )
    cur.execute("""
        CREATE TABLE IF NOT EXISTS {} (
            {},
            PRIMARY KEY (goal_id)
        )
    """.format(GOALS_TABLE_NAME, column_defs))
    # Get existing columns
    cur.execute("PRAGMA table_info({})".format(GOALS_TABLE_NAME))
    existing_cols = set(row[1] for row in cur.fetchall())
    # Add missing columns
    for col, dtype in GOAL_COLUMNS.items():
        if col not in existing_cols:
            cur.execute(
                "ALTER TABLE {} ADD COLUMN {} {}".format(
                    GOALS_TABLE_NAME, col, dtype
                )
            )
    # Commit updates
    conn.commit()

def cast_value(col, val):
    '''Enforce values set in the GOALS_COLUMN dict.'''
    if val == "":
        return None
    dtype = GOAL_COLUMNS[col]
    if "INTEGER" in dtype:
        return int(val)
    if "FLOAT" in dtype:
        return float(val)
    return val

def upsert_goal(conn, data):
    '''Perform upsert, including checks for missing inputs.'''
    # Establish connection
    cur = conn.cursor()
    # Required columns
    if "year" not in data or data["year"] == "":
        raise ValueError("Missing required field: year")
    if "book_goal" not in data or data["book_goal"] == "":
        raise ValueError("Missing required field: book_goal")
    
    # Default book_goal, page_goal if missing or empty
    book_goal = int(data["book_goal"])
    if book_goal <= 0:
        raise ValueError("book_goal must be a positive integer")
    if "page_goal" not in data or data["page_goal"] == "":
        data["page_goal"] = book_goal * 300

    # Auto-calc avg_page_per_book (after ensuring page_goal is present, above)
    page_goal = int(data["page_goal"])
    if page_goal > 1200 * book_goal:
        raise ValueError("Input page_goal value exceeds 1,200 pages per book estimate.")
    if page_goal > 0 and book_goal > 0:
        data["avg_page_per_book"] = page_goal / book_goal

    # Let SQLite handle timestamps
    data.setdefault("created_on", "CURRENT_TIMESTAMP")
    data["updated_on"] = "CURRENT_TIMESTAMP"
    # Prepare for up/insert
    columns = []
    values = []
    sql_values = []
    # Set goal
    for col in GOAL_COLUMNS:
        if col in data:
            columns.append(col)
            if data[col] == "CURRENT_TIMESTAMP":
                sql_values.append("CURRENT_TIMESTAMP")
            else:
                sql_values.append("?")
                values.append(cast_value(col, data[col]))
    assignments = ", ".join(
        "{}=excluded.{}".format(col, col)
        for col in columns if col != "year"
    )
    # Execute insert
    cur.execute("""
        INSERT INTO {} ({})
        VALUES ({})
        ON CONFLICT(goal_id) DO UPDATE SET
        {}
    """.format(
        GOALS_TABLE_NAME,
        ", ".join(columns),
        ", ".join(sql_values),
        assignments
    ), values)
    # Commit
    conn.commit()

def main():
    '''Establish overall procedure, order of operations.'''
    conn = sqlite3.connect(DB_PATH)
    ensure_table_and_columns(conn)
    # Parse
    goals = parse_goal_files()
    for goal in goals:
        upsert_goal(conn, goal)
    conn.close()

if __name__ == "__main__":
    main() # Run it all
