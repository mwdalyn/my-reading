import sqlite3, requests, sys, re

from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import quote

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
def create_table_if_not_exists(db_path, table_name, columns_dict):
    """Create a table from a dict of column definitions. Like books table in sync.py."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    columns_sql = ",\n    ".join(f"{col} {col_type}" for col, col_type in columns_dict.items())
    sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {columns_sql}\n);" 
    cur.execute(sql)
    
    conn.commit()
    conn.close()

def upsert_author(cur, table_name, data, conflict_key="full_name"):
    """Inserts or updates an author dynamically. Uses COALESCE to avoid overwriting."""
    # Set columns
    columns = list(data.keys())
    placeholders = ", ".join("?" for _ in columns)
    # Build update clause (skip conflict key and created_on)
    update_cols = ", ".join(
        f"{col}=COALESCE(excluded.{col},{col})"
        for col in columns
        if col not in {conflict_key, "created_on"}
    )
    sql = f"""
        INSERT INTO {table_name} ({', '.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT({conflict_key}) DO UPDATE SET
            {update_cols},
            updated_on = DATETIME('now')
    """
    cur.execute(sql, tuple(data[col] for col in columns))

def sync_authors_from_books(db_path=DB_PATH):
    """Function to collect authors from 'books' table and inject into 'authors' table."""
    # Connect
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # 1Create authors table if it doesn't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS authors (
            author_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL UNIQUE,
            first_name TEXT,
            last_name TEXT,
            birth_year INTEGER,
            death_year INTEGER,
            age INTEGER,
            birth_country TEXT,
            nationality TEXT,
            home_country TEXT,
            ref_count INTEGER DEFAULT 0,
            created_on TEXT DEFAULT (DATETIME('now')),
            updated_on TEXT DEFAULT (DATETIME('now'))
        );
    """)
    # Get unique authors from books
    authors = cur.execute("""
        SELECT DISTINCT author
        FROM books
        WHERE author IS NOT NULL
          AND TRIM(author) != '';
    """).fetchall()

    for row in authors:
        full_name = row["author"].strip() # Designed to be robust to multipart first or last names
        if "," in full_name:
            # Split on the first comma; allow optional whitespace immediately after
            match = re.match(r"^(.*?),\s*(.*)$", full_name)
            if match:
                last_name = match.group(1)  # Keeps internal spaces like for middle names
                first_name = match.group(2)
            else:
                last_name, first_name = full_name, None
        else:
            # Fallback: split on whitespace
            parts = full_name.split()
            first_name = parts[0]
            last_name = parts[-1] if len(parts) > 1 else None

        # Upsert: skip if full_name is already present, and COALESVE first, last just in case
        cur.execute("""
            INSERT INTO authors (
                full_name,
                first_name,
                last_name,
                created_on,
                updated_on
            )
            VALUES (?, ?, ?, DATETIME('now'), DATETIME('now'))
            ON CONFLICT(full_name) DO UPDATE SET
                first_name = COALESCE(excluded.first_name, first_name),
                last_name = COALESCE(excluded.last_name, last_name),
                updated_on = DATETIME('now');
        """, (
            full_name,
            first_name,
            last_name
        ))
    # Commit
    conn.commit()
    conn.close()
    print("Authors table synced successfully.")

def build_candidate_urls(full_name):
    """Function to attempt /wiki/First_Last as well as /wiki/Last,_First."""
    if "," in full_name:
        last, first = [p.strip() for p in full_name.split(",", 1)]
    else:
        parts = full_name.split()
        first = parts[0]
        last = parts[-1] if len(parts) > 1 else None
    candidates = []
    if first and last:
        candidates.append(f"{WIKI_BASE}{quote(first + '_' + last)}")
        candidates.append(f"{WIKI_BASE}{quote(last + ',_' + first)}")
    # Fallback: raw full name
    candidates.append(f"{WIKI_BASE}{quote(full_name.replace(' ', '_'))}")
    return candidates

def fetch_page(url):
    headers = {'User-Agent':WIKI_USER_AGENT}
    response = requests.get(url, headers=headers, timeout=10)
    # Get status 
    if response.status_code == 200:
        return response.text # Return text on success
    return None # If failure, None

def parse_infobox(html):
    soup = BeautifulSoup(html, "html.parser")
    infobox = soup.find("table", class_="infobox")
    # Handle infobox
    if not infobox:
        return None
    data = {}
    rows = infobox.find_all("tr")
    for row in rows:
        header = row.find("th")
        value = row.find("td")
        # Parse content
        if header and value:
            key = header.get_text(strip=True)
            val = value.get_text(" ", strip=True)
            data[key] = val
    # Return data
    return data

def scrape_author_wikipedia(full_name):
    # Use build_urls
    urls = build_candidate_urls(full_name) # Return list of poss url
    print("URLs:", urls)
    for url in urls: # Test urls
        html = fetch_page(url) # If failure, 
        if html: # If "not", try next possible url
            infobox_data = parse_infobox(html)
            if infobox_data:
                print(f"Found page: {url}")
                return {
                    "url": url,
                    "infobox": infobox_data
                }
    # If failure:
    print("No valid Wikipedia page found.")
    return None

def fetch_wiki_references(url):
    """One of several ways to attempt to measure popularity: references in-page to other articles."""
    # Fetch page right away
    html = fetch_page(url)
    if not html:
            return None # Fail
    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")    
    # Count <ref> tags (Wikipedia citations)
    num_refs = len(soup.find_all("ref"))
    return num_refs

def extract_author_fields(infobox):
    # Set current year
    current_year = datetime.now().year
    # Set defaults
    birth_year = None
    death_year = None
    age = None
    birth_country = None
    nationality = None
    ref_count = None
    # Birth
    born = infobox.get("Born") # TODO: Would "Birth" be one to check for? Or "__ Birth/Born:"
    if born:
        years = re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", born)
        if years:
            birth_year = int(years[0])
        # Birth country (last comma segment)
        parts = [p.strip() for p in born.split(",")]
        if len(parts) > 1:
            birth_country = parts[-1]

    # Death
    died = infobox.get("Died") # TODO: Would "Death" be one to check for? Or "__ Died:"
    if died:
        years = re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", died)
        if years:
            death_year = int(years[0])

        age_match = re.search(r"aged\s+(\d+)", died)
        if age_match:
            age = int(age_match.group(1))
            
    # Age fallback
    if birth_year and not age:
        if death_year:
            age = death_year - birth_year
        else:
            age = current_year - birth_year

    # Nationality
    nationality = infobox.get("Nationality")
    # Fallback: use birth country
    if not nationality and birth_country:
        nationality = birth_country
    # Return dict
    return {
        "birth_year": birth_year,
        "death_year": death_year,
        "age": age,
        "birth_country": birth_country,
        "nationality": nationality,
        "home_country": None,  # future logic
        "ref_count":ref_count
    }

# Execute
if __name__ == "__main__":
    # Ensure authors table exists
    create_table_if_not_exists(DB_PATH, AUTHORS_TABLE_NAME, AUTHORS_COLUMNS)
    # Sync authors from books table
    sync_authors_from_books(DB_PATH)
    # Connect and query
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # Set row factory
    cur = conn.cursor()
    # Get list authors and rows ids
    authors = cur.execute("""
        SELECT author_id, full_name
        FROM authors
    """).fetchall() # Already sync'd from 'books' table
    # Get Wikipedia info
    print(f"Enriching {len(authors)} authors from Wikipedia...\n")
    for row in authors:
        author_id = row["author_id"]
        full_name = row["full_name"]
        print(f"Processing: {full_name}")
        # Begin scraping
        result = scrape_author_wikipedia(full_name)
        if not result:
            print(f"No Wiki page found for {full_name}. Skipping.\n")
            continue
        # If found, extract and update
        extracted = extract_author_fields(result["infobox"])
        extracted["ref_count"] = fetch_wiki_references(result["url"]) 
        # TODO: Add other popularity metrics here
        # Prepare upsert data
        upsert_data = {
            "full_name": full_name,
            "first_name": extracted.get("first_name"),
            "last_name": extracted.get("last_name"),
            "birth_year": extracted.get("birth_year"),
            "death_year": extracted.get("death_year"),
            "age": extracted.get("age"),
            "birth_country": extracted.get("birth_country"),
            "nationality": extracted.get("nationality"),
            "home_country": extracted.get("home_country"),
            "ref_count": extracted.get("ref_count")
        }
        # Upsert
        upsert_author(cur, AUTHORS_TABLE_NAME, upsert_data)
        conn.commit()
        print("Updated.\n")
    # Close
    conn.close()
    print("Author enrichment complete.")
