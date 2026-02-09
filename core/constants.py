import os, re

# Constants
GH_EVENT_PATH, GH_EVENT_PATH_TEST = "GITHUB_EVENT_PATH", "GITHUB_TEST_EVENT_PATH"
GITHUB_API = "https://api.github.com" # validate.py
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") # validate.py
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY") # validate.py

# Regex for sync.py
PAGE_ONLY_RE = re.compile(r"^\s*(\d+)\s*$") 
DATED_PAGE_RE = re.compile(r"^\s*(\d{8})\s*:\s*(\d+)\s*$")
## SQL automation
BOOKS_COLUMNS = {
    "issue_id": "INTEGER PRIMARY KEY",
    "title": "TEXT", # Issue title
    "author": "TEXT", # Issue title
    "issue_number": "INTEGER",
    "status": "TEXT", # Set automatically upon sync workflow, script based on issue status and comments
    "date_began": "TEXT",
    "date_ended": "TEXT",
    "publisher": "TEXT",
    "year_published": "TEXT",
    "year_edition": "TEXT",
    "isbn": "TEXT",
    "width": "REAL",
    "length": "REAL",
    "height": "REAL",
    "total_pages": "INTEGER",
    "word_count":"REAL", # Added later; had used 'FLOAT' when creating in sql browser
    "library":"TEXT", # Added later; for use with 
    ## 
    "translator": "TEXT", # last_name, first_name
    "collection": "INTEGER", # 1 = 'TRUE' = collection of (short) stories; 0 = 'FALSE' = novel
    ##
    "created_on": "TEXT DEFAULT (DATETIME('now'))",
    "updated_on": "TEXT DEFAULT (DATETIME('now'))",
} # All BOOKS table columns including system columns (e.g. not about the book, about the entry of the book into the table)
BOOK_SYSTEM_COLUMNS = {
    "issue_id",
    "title",
    "author",
    "issue_number",
    "status",
    "date_began",
    "date_ended",
    "created_on",
    "updated_on",
} # Provided in EVERY case by the creation of a book issue, updated as changes are made to the issue
BOOK_METADATA_KEYS = {
    col for col in BOOKS_COLUMNS
    if col not in BOOK_SYSTEM_COLUMNS
} # This captures everything "else;" everything that's added into the body of the issue not explicitly defined above
READING_EVENTS_COLUMNS = {
    "source_id": "TEXT PRIMARY KEY", 
    "issue_id": "INTEGER",
    "date": "TEXT",
    "page": "INTEGER",
    "source": "TEXT",
    "created_on": "TEXT DEFAULT (DATETIME('now'))",
    "updated_on": "TEXT DEFAULT (DATETIME('now'))",
}

DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR,"reading.sqlite")

# Enable abandonment
ABANDON_KEYWORDS = {"abandon","give_up"}
AUTO_CLOSED_LABEL = "auto-closed" # For automatically closing books marked abandoned (and not going recursive)

# Set calendar table start, end
CALENDAR_START = "2026-01-01"
CALENDAR_END = "2026-12-31"

