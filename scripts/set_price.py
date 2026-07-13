# TODO: Create an API Key, create a local cache (new table to check before calling API again), etc.
# This should be used for more than just price, depending on what's available.
'''Try to get price by querying external db for ISBN or similar.'''
import requests, sqlite3, sys, time

# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import * 
##########

headers = {
    "User-Agent": "my-reading/1.0"
}
# def fetch_price_from_google(isbn):
#     """Try to fetch book price from Google Books API by ISBN.
#     Returns (price, currency) or (None, None)."""
#     # Set url
#     url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
#     try:
#         r = requests.get(url, timeout=5)
#         if r.status_code != 200:
#             print(f"Error: Unsuccessful Google Books response for isbn:{isbn}")
#             return None, None
#         data = r.json()
#         items = data.get("items")
#         if not items:
#             return None, None
#         # Get sale info
#         sale_info = items[0].get("saleInfo", {})
#         list_price = sale_info.get("listPrice")
#         # Check for price
#         if list_price:
#             return list_price.get("amount"), list_price.get("currencyCode")
#     except Exception:
#         pass
#     # Return
#     return None, None

def fetch_google_book(isbn, headers=headers, retries=1):
    """Fetch metadata from Google Books by ISBN."""
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 429:
                wait = 2 ** attempt
                print(f"Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            # Continue
            r.raise_for_status()
            data = r.json()
            if not data.get("items"):
                return None
            # Parse
            book = data["items"][0]
            volume = book.get("volumeInfo", {})
            sale = book.get("saleInfo", {})
            return {
                "title": volume.get("title"),
                "authors": volume.get("authors"),
                "publisher": volume.get("publisher"),
                # "publish_date": volume.get("publishedDate"),
                "page_count": volume.get("pageCount"),
                "language": volume.get("language"),
                "print_type": volume.get("printType"),
                "categories": volume.get("categories"),
                "rating_avg": volume.get("averageRating"),
                "rating_count": volume.get("ratingsCount"),
                "saleability": sale.get("saleability"),
                "country": sale.get("country"),
                "price_list": sale.get("listPrice"),
                "price_retail": sale.get("retailPrice"),
            }
        except requests.RequestException as e:
            print(e)
            return None
    return None
def estimate_price_by_format(format_type, page_count=None):
    """Rough price heuristic based on format. Returns estimated USD price."""
    # Check format type
    format_type = (format_type or "").lower()
    if "hardcover" in format_type:
        base = 28
    elif "paperback" in format_type:
        base = 18
    elif "massmarket" in format_type:
        base = 9
    else:
        base = 20  # default fallback
    # Book length adjustment
    if page_count:
        if page_count > 600:
            base += 4
        elif page_count > 400:
            base += 2
    # Return
    return round(base, 2)

def get_book_price(isbn, format_type=None, page_count=None):
    """Attempt API lookup first. If unavailable, use heuristic estimate. """
    gb = fetch_google_book(isbn)
    if gb:
        price = gb.get("price_retail") or gb.get("price_list")
        if price is not None:
            return {
                "price": price,
                "currency": "USD",
                "source": "google_books_api"
            }
    # Return
    return {
        "price": estimate_price_by_format(format_type, page_count),
        "currency": "USD",
        "source": "heuristic_estimate"
    }

# Connect
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
# Get unique authors from books
books = cur.execute("""
    SELECT DISTINCT issue_id, isbn
    FROM books
    WHERE author IS NOT NULL;
""").fetchall()

for row in books:
    id, isbn = row["issue_id"], row["isbn"].strip().replace("-","")
    result = get_book_price(
        isbn=str(isbn),
        format_type="paperback",
        page_count=320
    )
    time.sleep(2)
    print(id)
    print(result)
