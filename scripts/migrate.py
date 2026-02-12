'''Script to handle schema migration.'''

# Imports
import os, sqlite3, sys

from core.constants import * 

# #############
# from pathlib import Path
# ROOT = Path(__file__).resolve().parents[1]
# sys.path.insert(0, str(ROOT))
# DATA_DIR = ROOT / "data"
# DATA_DIR.mkdir(exist_ok=True)

# Schema versioning
def ensure_schema_version(cur):
    """Ensure the schema_version table exists."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
    """)

def get_schema_version(cur):
    """Return current schema version (0 if none)."""
    cur.execute("SELECT MAX(version) FROM schema_version")
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0

def set_schema_version(cur, version):
    """Update schema_version table."""
    cur.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

def add_column_if_not_exists(cur, table, column, definition):
    cols = cur.execute(f"PRAGMA table_info({table})").fetchall()
    if not any(col[1] == column for col in cols):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

# Initial schema
def create_books_v1(cur):
    """Initial books table schema."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            issue_id INTEGER PRIMARY KEY,
            title TEXT,
            author TEXT,
            issue_number INTEGER,
            status TEXT,
            date_began TEXT,
            date_ended TEXT,
            publisher TEXT,
            year_published TEXT,
            year_edition TEXT,
            isbn TEXT,
            width REAL,
            length REAL,
            height REAL,
            total_pages INTEGER,
            translator TEXT,
            collection INTEGER,
            created_on TEXT DEFAULT (DATE('now')),
            updated_on TEXT DEFAULT (DATE('now')),
            word_count REAL
        )
    """)

def create_reading_events_v1(cur):
    """Initial reading_events table schema."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reading_events (
            source_id TEXT PRIMARY KEY,
            issue_id INTEGER,
            date TEXT,
            page INTEGER,
            source TEXT,
            created_on TEXT DEFAULT (DATE('now')),
            updated_on TEXT DEFAULT (DATE('now'))
        )
    """)

## Migration 1
def migration_1_initial_schema(cur):
    """Migration 1: initial schema creation."""
    create_books_v1(cur)
    create_reading_events_v1(cur)

## Migration 2
def migration_2_books_datetime(cur):
    """Upgrade books created_on / updated_on to DATETIME."""
    cur.executescript("""
    BEGIN;
    ALTER TABLE books RENAME TO books_old;
    CREATE TABLE books (
        issue_id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        issue_number INTEGER,
        status TEXT,
        date_began TEXT,
        date_ended TEXT,
        publisher TEXT,
        year_published TEXT,
        year_edition TEXT,
        isbn TEXT,
        width REAL,
        length REAL,
        height REAL,
        total_pages INTEGER,
        translator TEXT,
        collection INTEGER,
        created_on TEXT DEFAULT (DATETIME('now')),
        updated_on TEXT DEFAULT (DATETIME('now')),
        word_count REAL
    );
    INSERT INTO books
    SELECT
        issue_id, title, author, issue_number, status,
        CASE WHEN length(date_began)=10 THEN date_began || ' 00:00:00' ELSE date_began END,
        CASE WHEN length(date_ended)=10 THEN date_ended || ' 00:00:00' ELSE date_ended END,
        publisher, year_published, year_edition,
        isbn, width, length, height, total_pages,
        translator, collection,
        CASE WHEN length(created_on)=10 THEN created_on || ' 00:00:00' ELSE created_on END,
        CASE WHEN length(updated_on)=10 THEN updated_on || ' 00:00:00' ELSE updated_on END,
        word_count
    FROM books_old;
    DROP TABLE books_old;
    COMMIT;
    """)

def migration_2_reading_events_datetime(cur):
    """Upgrade reading_events date / created_on / updated_on to DATETIME."""
    cur.executescript("""
    BEGIN;
    ALTER TABLE reading_events RENAME TO reading_events_old;
    CREATE TABLE reading_events (
        source_id TEXT PRIMARY KEY,
        issue_id INTEGER,
        date TEXT,
        page INTEGER,
        source TEXT,
        created_on TEXT DEFAULT (DATETIME('now')),
        updated_on TEXT DEFAULT (DATETIME('now'))
    );
    INSERT INTO reading_events
    SELECT
        source_id, issue_id,
        CASE WHEN length(date)=10 THEN date || ' 00:00:00' ELSE date END,
        page, source,
        CASE WHEN length(created_on)=10 THEN created_on || ' 00:00:00' ELSE created_on END,
        CASE WHEN length(updated_on)=10 THEN updated_on || ' 00:00:00' ELSE updated_on END
    FROM reading_events_old;
    DROP TABLE reading_events_old;
    COMMIT;
    """)

def migration_2_datetime_defaults(cur):
    """Run datetime upgrades for books and reading_events."""
    migration_2_books_datetime(cur)
    migration_2_reading_events_datetime(cur)

## Migration 3
def migration_3_books_word_count_position(cur):
    """Move word_count column immediately after total_pages."""
    cur.executescript("""
    BEGIN;
    ALTER TABLE books RENAME TO books_old;
    CREATE TABLE books (
        issue_id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        issue_number INTEGER,
        status TEXT,
        date_began TEXT,
        date_ended TEXT,
        publisher TEXT,
        year_published TEXT,
        year_edition TEXT,
        isbn TEXT,
        width REAL,
        length REAL,
        height REAL,
        total_pages INTEGER,
        word_count REAL,
        translator TEXT,
        collection INTEGER,
        created_on TEXT DEFAULT (DATETIME('now')),
        updated_on TEXT DEFAULT (DATETIME('now'))
    );
    INSERT INTO books (
        issue_id, title, author, issue_number, status,
        date_began, date_ended,
        publisher, year_published, year_edition,
        isbn, width, length, height, total_pages,
        word_count, translator, collection,
        created_on, updated_on
    )
    SELECT
        issue_id, title, author, issue_number, status,
        date_began, date_ended,
        publisher, year_published, year_edition,
        isbn, width, length, height, total_pages,
        word_count, translator, collection,
        created_on, updated_on
    FROM books_old;
    DROP TABLE books_old;
    COMMIT;
    """)

def migration_4_add_library_books(cur):
    """Add column 'library' immediately after most recent metadata column, 'word_count.'"""
    cur.execute("ALTER TABLE books ADD COLUMN library TEXT;")
    """Move library column immediately after word_count."""
    cur.executescript("""
    BEGIN;
    ALTER TABLE books RENAME TO books_old;
    CREATE TABLE books (
        issue_id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        issue_number INTEGER,
        status TEXT,
        date_began TEXT,
        date_ended TEXT,
        publisher TEXT,
        year_published TEXT,
        year_edition TEXT,
        isbn TEXT,
        width REAL,
        length REAL,
        height REAL,
        total_pages INTEGER,
        word_count REAL,
        library TEXT,
        translator TEXT,
        collection INTEGER,
        created_on TEXT DEFAULT (DATETIME('now')),
        updated_on TEXT DEFAULT (DATETIME('now'))
    );
    INSERT INTO books (
        issue_id, title, author, issue_number, status,
        date_began, date_ended,
        publisher, year_published, year_edition,
        isbn, width, length, height, total_pages,
        word_count, library, translator, collection,
        created_on, updated_on
    )
    SELECT
        issue_id, title, author, issue_number, status,
        date_began, date_ended,
        publisher, year_published, year_edition,
        isbn, width, length, height, total_pages,
        word_count, library, translator, collection,
        created_on, updated_on
    FROM books_old;
    DROP TABLE books_old;
    COMMIT;
    """)

def migration_5_more_books_md(cur):
    """Add various columns to 'books' table.'"""
    add_column_if_not_exists(cur, "books", "original_language", "TEXT")
    add_column_if_not_exists(cur, "books", "read_count", "INTEGER")
    add_column_if_not_exists(cur, "books", "genre_primary", "TEXT")
    add_column_if_not_exists(cur, "books", "genre_secondary", "TEXT")

    """Move columns to desired places."""
    cur.executescript("""
    BEGIN;
    ALTER TABLE books RENAME TO books_old;
    CREATE TABLE books (
        issue_id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        issue_number INTEGER,
        status TEXT,
        date_began TEXT,
        date_ended TEXT,
        publisher TEXT,
        year_published TEXT,
        year_edition TEXT,
        isbn TEXT,
        width REAL,
        length REAL,
        height REAL,
        total_pages INTEGER,
        word_count REAL,
        library TEXT,
        translator TEXT,
        original_language TEXT DEFAULT 'en',
        collection INTEGER DEFAULT 0,
        read_count INTEGER DEFAULT 0, 
        genre_primary TEXT,
        genre_secondary TEXT,
        created_on TEXT DEFAULT (DATETIME('now')),
        updated_on TEXT DEFAULT (DATETIME('now'))
    );
    INSERT INTO books (
        issue_id, title, author, issue_number, status,
        date_began, date_ended,
        publisher, year_published, year_edition,
        isbn, width, length, height, total_pages,
        word_count, library, translator, original_language,
        collection, read_count, genre_primary, genre_secondary,
        created_on, updated_on
    )
    SELECT
        issue_id, title, author, issue_number, status,
        date_began, date_ended,
        publisher, year_published, year_edition,
        isbn, width, length, height, total_pages,
        word_count, library, translator,
        COALESCE(original_language, 'en'),
        COALESCE(collection, 0),
        COALESCE(read_count, 0),
        genre_primary,
        genre_secondary,
        created_on, updated_on
    FROM books_old;
    DROP TABLE books_old;
    COMMIT;
    """)
    
## Migration dictionary
MIGRATIONS = {
    1: migration_1_initial_schema,
    2: migration_2_datetime_defaults,
    3: migration_3_books_word_count_position,
    4: migration_4_add_library_books,
    5: migration_5_more_books_md,
}

# Run
def run_migrations(db_path):
    """Run pending migrations on the database."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ensure_schema_version(cur)
    current_version = get_schema_version(cur)
    print(f"Current schema version: {current_version}")
    # Iter versions
    for version in sorted(MIGRATIONS.keys()):
        if version > current_version:
            print(f"Running migration {version}...")
            MIGRATIONS[version](cur)
            set_schema_version(cur, version)
            conn.commit()
            print(f"Migration {version} complete.")
    # Close
    conn.close()
    print("All migrations complete.")

if __name__ == "__main__":
    run_migrations(DB_PATH)
