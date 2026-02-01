my-reading
# My Reading
Attempt at a new method to track reading.

**Purpose:** Learn new techniques, and GitHub native features. Build automations.

**Goal:** Want as minimal user intervention as possible to track reading. Minimal phone interaction. 
Want all reading data in a singular location 

## Outline
- Create an Issue for each book started (any manual logs covering previous progress go in the body)
- Comment the new page on the date it was reached (with backdating allowable, if necessary)
- Develop an automation via GitHub Actions to scrape the Issues and their comments (and contents) for the info needed
- Create a database with relevant tables (for now: "log" and "books")

> **Note:** 
> Had previously pursued building an SMS automation but Twilio/Google Voice (for Workspace) put me off. My preferred method in the past was taking photos of pages (and the cover at start/finish), but that became hard to log in a spreadsheet consistently. 

## Future 
1. Expand the database with external inputs
- Pull in ISBN, external data (rating, populatrity metric e.g. Goodreads reviews or Wikipedia entry)
- Query book stats (publication, genre, author nationality, etc.)
    - Estimate the words read in a book using page size and publication info
- Integrate "want to read" books (e.g. Goodreads) or a "shelf" feature
2. Add visualizations
- Add a (static) dashboard that updates with each workflow trigger
- Metrics could include: 
    - Aggregate statistics (pages and/or books per month)
    - Streaks on/off (heatmap, pages per day barchart or line graph)
    - Velocity (pages/day or pages/day/book) 
    - Genre breakdown
    - Abandoned book statistics
    - Height of book stack I've read
3. Incorporate small ML features
- Develop a recommender system for new books
- Develop a "reading WPM" test that could estimate my reading speed over the computer


