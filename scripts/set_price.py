'''Try to get price by querying external db for ISBN or similar.'''
import requests

def fetch_price_from_google(isbn):
    """Try to fetch book price from Google Books API by ISBN.
    Returns (price, currency) or (None, None)."""
    # Set url
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            print(f"Error: Unsuccessful Google Books response for isbn:{isbn}")
            return None, None
        data = r.json()
        items = data.get("items")
        if not items:
            return None, None
        # Get sale info
        sale_info = items[0].get("saleInfo", {})
        list_price = sale_info.get("listPrice")
        # Check for price
        if list_price:
            return list_price.get("amount"), list_price.get("currencyCode")
    except Exception:
        pass
    # Return
    return None, None

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

# TODO: Update "format" column for books in 'books' table.
def get_book_price(isbn, format_type=None, page_count=None):
    """Attempt API lookup first. If unavailable, use heuristic estimate. """
    price, currency = fetch_price_from_google(isbn)
    if price is not None:
        return {
            "price": price,
            "currency": currency,
            "source": "google_api"
        }
    # Fallback heuristic
    estimated = estimate_price_by_format(format_type, page_count)
    # Return
    return {
        "price": estimated,
        "currency": "USD",
        "source": "heuristic_estimate"
    }


result = get_book_price(
    isbn="9780143127741",
    format_type="Paperback",
    page_count=320
)

print(result)
