'''CREATE TABLE IF NOT EXISTS ts_goals_actual (
    goal_id TEXT NOT NULL,
    date TEXT NOT NULL,
    daily_page_avg FLOAT,
    cumulative_pages FLOAT,
    pages_read FLOAT,
    cumulative_pages_read FLOAT,
    PRIMARY KEY (goal_id, date),
    FOREIGN KEY (goal_id) REFERENCES reading_goals(goal_id)
);'''
