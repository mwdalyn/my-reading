import os, re

from pathlib import Path
from dotenv import load_dotenv

# Get/set project root and get secrets
CORE_DIR = Path(__file__).resolve().parent  # core/
PROJECT_ROOT = CORE_DIR.parent              # my-reading/ for all executions
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
REQ_FILE = PROJECT_ROOT / "requirements.txt"

# Constants
GH_EVENT_PATH, GH_EVENT_PATH_TEST = "GITHUB_EVENT_PATH", "GITHUB_TEST_EVENT_PATH"
GITHUB_API = "https://api.github.com" # validate.py
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") # validate.py
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY") # validate.py
OWNER, REPO = GITHUB_REPOSITORY.split("/") # validate.py # TODO: Is this really needed? 

# Wikipedia contact
WIKI_BASE = "https://en.wikipedia.org/wiki/"
WIKI_USER_AGENT = os.environ.get("WIKI_USER_AGENT")

# DB path 
DATA_DIR = PROJECT_ROOT / "data"
VIS_DIR = PROJECT_ROOT / "visuals"
GOALS_DIR = DATA_DIR / "goals"
DB_PATH = os.path.join(DATA_DIR,"reading.sqlite")
# Skip mkdirs 

# Regex for sync.py and issue-body/comment parsing
PAGE_ONLY_RE = re.compile(r"^\s*(\d+)\s*$") 
DATED_PAGE_RE = re.compile(r"^\s*(\d{8})\s*:\s*(\d+)\s*$")

## SQL automation
# Books table
BOOKS_TABLE_NAME = 'books' # Not yet referenced anywhere but just in case
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
    "library":"TEXT", # Added later; default 0 = home library
    "translator": "TEXT", # last_name, first_name
    "original_language":"TEXT DEFAULT 'en'", # Default to english code for now; want to track original language 
    "collection": "INTEGER DEFAULT 0", # 1 = 'TRUE' = collection of (short) stories; 0 = 'FALSE' = novel
    # "format":"TEXT", # 'harcover' or 'paperback', opening things up to 'textbook' later (just in case)
    "read_count":"INTEGER DEFAULT 0", # Number of times read before this time
    "genre_primary":"TEXT", # Must be from a default list, see constants.py
    "genre_secondary":"TEXT", # Must be from a default list, see constants.py
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

# Reading Events table
EVENTS_TABLE_NAME = 'reading_events'
READING_EVENTS_COLUMNS = {
    "source_id": "TEXT PRIMARY KEY", 
    "issue_id": "INTEGER",
    "date": "TEXT",
    "page": "INTEGER",
    "source": "TEXT",
    "created_on": "TEXT DEFAULT (DATETIME('now'))",
    "updated_on": "TEXT DEFAULT (DATETIME('now'))",
}

# Goal table (and goal input file)
GOALS_TABLE_NAME = "reading_goals"
GOAL_COLUMNS = {
    "goal_id": "TEXT NOT NULL", # This is the file name
    "year": "INTEGER NOT NULL",
    "goal_name": "TEXT",
    "book_goal": "INTEGER NOT NULL",
    "page_goal": "INTEGER NOT NULL",
    "avg_page_per_book": "FLOAT",
    "created_on": "TIMESTAMP",
    "updated_on": "TIMESTAMP",
}

# Authors table
AUTHORS_TABLE_NAME = "authors"
AUTHORS_COLUMNS = {"author_id": "INTEGER PRIMARY KEY",
    "full_name": "TEXT NOT NULL UNIQUE",
    "first_name": "TEXT",
    "last_name": "TEXT",
    # Begin metadata
    "birth_year": "INTEGER",
    "death_year": "INTEGER",
    "age": "INTEGER",
    "birth_country": "TEXT",
    "nationality": "TEXT",
    "home_country": "TEXT",
    "ref_count": "INTEGER",
    # End metadata
    "created_on": "TEXT DEFAULT (DATETIME('now'))",
    "updated_on": "TEXT DEFAULT (DATETIME('now'))"}
AUTHORS_SYSTEM_COLUMNS = {
    "author_id",
    "full_name",
    "first_name",
    "last_name",
    "created_on",
    "updated_on",
} # Provided in EVERY case by the creation of a book issue, updated as changes are made to the issue
AUTHORS_METADATA_KEYS = {
    col for col in AUTHORS_COLUMNS
    if col not in AUTHORS_SYSTEM_COLUMNS
}


# Define 'books' table metadata options
GENRES = {
    "action",
    "adventure",
    "classic", # more of a label than a genre; assume this signifies "not-modern" and character-driven
    "collection",
    "comedy",
    "crime",
    "drama",
    "dystopian",
    "epic",
    "fantasy",
    "folklore",
    "gothic",
    "historical",
    "horror",
    "mystery",
    "mythology",
    "memoir",
    "noir",
    "postapoc", # postapocalyptic
    "romance",
    "scifi",
    "supernatural",
    "suspense",
    "thriller",
    "western",
}
FORMATS = {'paperback','hardcover','book'} # 'book' = unknown; default
ORIGINAL_LANGUAGES  = {
        "fr",    # French
        "en",    # English
        "it",    # Italian
        "ru",    # Russian
        "de",    # German
        "es",    # Spanish
        "ro",    # Romanian
        "el",    # Greek (Modern)
    }
# Reference: https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes

# Enable abandonment
ABANDON_KEYWORDS = {"abandon","give_up"}
AUTO_CLOSED_LABEL = "auto-closed" # For automatically closing books marked abandoned (and not going recursive)

# Set calendar table start, end
CALENDAR_START = "2026-01-01"
CALENDAR_END = "2026-12-31"

# Visuals
MY_COLOR="#008ddf"
GOAL_COLOR="#4a4a4a"
ABSENT_COLOR = "#eeeeee"
DOW_COLORS = {
    "Monday": "#6C3F81",
    "Tuesday": "#84B478",
    "Wednesday": "#DE895B",
    "Thursday": "#F05C5F",
    "Friday": "#B14D7A",
    "Saturday": "#2782EA",
    "Sunday": "#EDC948",
}
MY_HEIGHT = (5 * 12) + 6.5  
MY_HEAD_HEIGHT = MY_HEIGHT/7.5 # starting from top assume 7.5 head proportions; feet are 1/2 
HUMAN_PROPORTIONS = {"Head":1,
                     "Torso":2.5,
                     "Femurs":2,
                     "Shins":1.5,
                     "Feet":0.5}
LEGEND_MAX_CHARS = 26 # For text wrapping in legend(s), esp. with titles
### TODO: Add font_size defaults for graphics?
