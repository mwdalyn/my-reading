import sqlite3, requests, sys, re

from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urlparse
import requests, sys
from dateutil.parser import parse as parse_date
###################
# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import * 
from sql_utils import *
####################

# Functions
def sync_authors_from_books(db_path=DB_PATH):
    """Function to collect authors from 'books' table and inject into 'authors' table."""
    # Connect
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Create authors table if it doesn't exist
    cur.execute(
        sql_create_table_cmd(AUTHORS_TABLE_NAME, AUTHORS_COLUMNS)
    )
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
            parts = full_name.split() # TODO: For two-term first names and pronounced middles, need this to split on only the LAST whitespace
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
        candidates.append(f"{WIKI_BASE}{quote(first + ' ' + last)}") # quote() = URL friendly handling of special chars
        candidates.append(f"{WIKI_BASE}{quote(first + ' ' + last + ' (author)')}") # quote() = URL friendly handling of special chars
        candidates.append(f"{WIKI_BASE}{quote(first + ' ' + last + ' (writer)')}") # quote() = URL friendly handling of special chars
        candidates.append(f"{WIKI_BASE}{quote(first + '_' + last)}") # quote() = URL friendly handling of special chars
        candidates.append(f"{WIKI_BASE}{quote(first + '_' + last + '_(author)')}")
        candidates.append(f"{WIKI_BASE}{quote(first + '_' + last + '_(writer)')}")
        candidates.append(f"{WIKI_BASE}{quote(last + ',_' + first)}")
        candidates.append(f"{WIKI_BASE}{quote(last + ',_' + first + '_(author)')}")
        candidates.append(f"{WIKI_BASE}{quote(last + ',_' + first + '_(writer)')}")
    # Fallback: raw full name
    candidates.append(f"{WIKI_BASE}{quote(full_name.replace(' ', '_'))}")
    # Fallback: (writer), (author)
    candidates.append(f"{WIKI_BASE}{quote(full_name.replace(' ', '_')  + '_(author)')}")
    candidates.append(f"{WIKI_BASE}{quote(full_name.replace(' ', '_')  + '_(writer)')}") 
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
    birth_place = None
    home_country = None
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
            birth_place = parts[-2]
            if birth_place:
                birth_place = re.sub(r'[^a-zA-Z\s-]', birth_place).lstrip() # Remove all not a letter, space, or dash; then leading whitespace
        print("Born parts:",parts)

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
    nationality = infobox.get("Nationality") # TODO: Check for other terms?
    # Fallback: use birth country
    if not nationality and birth_country:
        try:
            nationality = STANDARDIZE_COUNTRIES.get(birth_country, {}).get("nationality") 
        except:
            nationality = birth_country
    # Standardize birth_country
    if birth_country:
        birth_country = STANDARDIZE_COUNTRIES.get(birth_country, {}).get("birth_country") 
    # Fix up home_country as well, for now
    if not home_country:
        home_country = birth_country
    # Return dict
    return {
        "birth_year": birth_year,
        "death_year": death_year,
        "age": age,
        "birth_country": birth_country,
        "birth_place": birth_place,
        "nationality": nationality,
        "home_country": home_country,
        "ref_count":ref_count
    }

# Additional metrics
def get_page_creation_date(title):
    """Return ISO timestamp when the page was created, e.g., '2001-03-10T12:34:56Z'."""
    HEADERS = {'User-Agent':WIKI_USER_AGENT}
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "revisions",
        "rvdir": "newer",
        "rvlimit": 1,          # first revision
        "rvprop": "timestamp"
    }
    try:
        r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        pages = r.json()["query"]["pages"]
        for page_id, page in pages.items():
            revs = page.get("revisions")
            if revs:
                return revs[0]["timestamp"]
    except Exception as e:
        print(f"Error fetching creation date for {title}: {e}")
    return None

def get_total_pageviews(title):
    """Return total views in last 60 days using Pageviews API."""
    # Use Wikimedia REST API for pageviews
    HEADERS = {'User-Agent':WIKI_USER_AGENT}
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{title}/daily/20230101/20231231"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        views = sum(item["views"] for item in data.get("items", []))
        return views
    except Exception:
        return None

def get_total_edit_count(title):
    """Return total number of edits/revisions for a page."""
    HEADERS = {'User-Agent':WIKI_USER_AGENT}
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "revisions",
        "rvprop": "ids",
        "rvlimit": "max"  # will fetch first 500; can iterate for full count
    }
    try:
        total_edits = 0
        cont = {}
        while True:
            full_params = params.copy()
            full_params.update(cont)
            r = requests.get(WIKI_API, params=full_params, headers=HEADERS, timeout=10)
            r.raise_for_status()
            pages = r.json()["query"]["pages"]
            for page_id, page in pages.items():
                revs = page.get("revisions", [])
                total_edits += len(revs)
            if "continue" in r.json():
                cont = r.json()["continue"]
            else:
                break
        return total_edits
    except Exception:
        return None

def extract_wiki_title(url):
    """Convert URL to MediaWiki title string for API usage."""
    path = urlparse(url).path  # e.g., '/wiki/John_Smith'
    title = path.replace("/wiki/", "")
    title = unquote(title)
    return title

# Execute
if __name__ == "__main__":
    # Sync authors from books table (includes creating the table initially)
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
        # Begin scraping author's page
        result = scrape_author_wikipedia(full_name)
        if not result:
            print(f"No Wiki page found for {full_name}. Skipping.\n")
            continue
        # If found, extract and update
        extracted = extract_author_fields(result["infobox"])
        extracted["ref_count"] = fetch_wiki_references(result["url"]) 
        # Other data collection
        wiki_title = extract_wiki_title(result["url"])
        # Fetch new metrics
        creation_date = parse_date(get_page_creation_date(wiki_title)).replace(tzinfo=None).strftime("%Y-%m-%d")
        total_views = get_total_pageviews(wiki_title)
        edit_count = get_total_edit_count(wiki_title)
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
            "wiki_url":result["url"],
            "wiki_ref_count": extracted.get("ref_count"),
            "wiki_creation_date": creation_date,
            "wiki_total_views": total_views,
            "wiki_edit_count": edit_count
        }
        # Upsert
        # TODO: Compare upsert_data to AUTHORS_COLUMNS or AUTHORS METADATA KEYS. Verify the above has everything that's expected so that it's actually fully dynamic.
        sql = sql_upsert(AUTHORS_TABLE_NAME, upsert_data, "full_name")
        columns_for_insert = [
            c for c in upsert_data.keys()
            if c not in {"created_on", "updated_on"}
        ]
        cur.execute(sql, tuple(upsert_data[c] for c in columns_for_insert))
        conn.commit()
        print("Updated.\n")
    # Close
    conn.close()
    print("Author enrichment complete.")
