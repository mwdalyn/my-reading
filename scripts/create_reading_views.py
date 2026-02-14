import sqlite3, sys

###################
# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import * 
####################

def main():
    # Set connection
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # Make rows behave like dicts, not tuples
    cur = conn.cursor()
    # Create views
    ## Daily book progress
    cur.executescript(
        """
        DROP VIEW IF EXISTS v_daily_book_progress;
        CREATE VIEW IF NOT EXISTS v_daily_book_progress AS
        WITH re_with_prev AS (
            SELECT
                issue_id,
                date(datetime(date, '-5 hours')) AS date_est,
                page,
                LAG(page) OVER (PARTITION BY issue_id ORDER BY date) AS prev_page
            FROM reading_events
        ),
        daily_counts AS (
            SELECT
                issue_id,
                date_est,
                COUNT(*) AS cnt,
                MIN(page) AS min_page,
                MAX(page) AS max_page,
                MAX(prev_page) AS prev_page
            FROM re_with_prev
            GROUP BY issue_id, date_est
        )
        SELECT
            issue_id,
            date_est,
            CASE
                WHEN cnt > 1 THEN max_page - min_page
                ELSE max_page - prev_page
            END AS pages_read
        FROM daily_counts
        ORDER BY issue_id, date_est;
        """
    )

    ## Books completed per day
    cur.executescript(
        """
        DROP VIEW IF EXISTS v_books_completed;
        CREATE VIEW IF NOT EXISTS v_books_completed AS
        SELECT
            date(datetime(date_ended, '-5 hours')) AS date_est,
            COUNT(*) AS books_completed
        FROM books
        WHERE date_ended IS NOT NULL
        GROUP BY date_est;
        """
    )

    ## Goal-based daily pages
    cur.executescript(
        """
        DROP VIEW IF EXISTS v_goal_daily_pages;
        CREATE VIEW IF NOT EXISTS v_goal_daily_pages AS
        SELECT
            c.date as date_est,
            rg.goal_id AS progress_id,
            CAST(
                rg.page_goal * 1.0 /
                (julianday(rg.year || '-12-31') - julianday(rg.year || '-01-01') + 1)
                AS INTEGER
            ) AS pages_read
        FROM reading_goals rg
        JOIN calendar c
          ON c.year = rg.year;
        """
    )

    ## Daily pages, by book
    cur.executescript(
        """
        DROP VIEW IF EXISTS v_book_daily_pages;
        CREATE VIEW IF NOT EXISTS v_book_daily_pages AS
        SELECT
            c.date as date_est,
            CAST(b.issue_id AS TEXT) AS progress_id,
            COALESCE(p.pages_read, 0) AS pages_read
        FROM books b
        JOIN calendar c
          ON c.year = CAST(strftime('%Y', b.created_on) AS INTEGER)
        LEFT JOIN v_daily_book_progress p
          ON p.issue_id = b.issue_id
         AND p.date_est = c.date;
        """
    )

    # Final ts_reading view
    cur.executescript(
        """
        DROP VIEW IF EXISTS ts_reading;
        CREATE VIEW IF NOT EXISTS ts_reading AS
        WITH daily AS (
            SELECT
                date_est,
                SUM(CASE WHEN progress_id NOT GLOB '*_*' THEN pages_read ELSE 0 END) AS my_reading,
                SUM(CASE WHEN progress_id GLOB '*_*' THEN pages_read ELSE 0 END) AS my_goal,
                COALESCE(MAX(books_completed), 0) AS books_completed
            FROM (
                SELECT date_est, progress_id, pages_read, NULL AS books_completed FROM v_goal_daily_pages
                UNION ALL
                SELECT date_est, progress_id, pages_read, NULL AS books_completed FROM v_book_daily_pages
                UNION ALL
                SELECT date_est, NULL, 0, books_completed FROM v_books_completed
            )
            GROUP BY date_est
        )
        SELECT
            date_est,
            my_reading,
            my_goal,
            books_completed,
            SUM(my_reading) OVER (ORDER BY date_est ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS my_reading_cumulative,
            SUM(my_goal) OVER (ORDER BY date_est ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS my_goal_cumulative
        FROM daily
        ORDER BY date_est;
    """
    )
    # Commit
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
