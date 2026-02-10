import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime

# from core.constants import * 

# Local testing
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.constants import *

# Functions
## Universal load
def load_ts_reading(db_path):
    '''Load table or view data for plotting.''' # TODO: Make flexible to different table or view names!
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        "SELECT * FROM ts_reading",
        conn,
        parse_dates=["date_est"]
    )
    conn.close()
    return df

## Hair chart
def create_hair_chart_discrete(df_2026):
    # Set up 
    fig, ax = plt.subplots(figsize=(20, 5))
    bar_width = 0.4
    ax.bar(
        df_2026["date_est"] - pd.Timedelta(hours=12),
        df_2026["my_goal"],
        width=bar_width,
        color=GOAL_COLOR,
        edgecolor=GOAL_COLOR,
        alpha=0.6,
        label="My goal"
    )

    ax.bar(
        df_2026["date_est"] + pd.Timedelta(hours=12),
        df_2026["my_reading"],
        width=bar_width,
        color=MY_COLOR,
        edgecolor=MY_COLOR,
        label="My reading"
    )

    ax.set_ylim(0, 300)
    ax.set_ylabel("Pages read")

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    ax.set_xlim(
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-12-31")
    )

    ax.legend(frameon=False)
    ax.set_title("Daily Reading vs Goal (2026)")

    plt.tight_layout()
    plt.show()

def create_hair_chart_cumulative(df_2026):
    # Set up
    fig, ax = plt.subplots(figsize=(20, 5))
    ax.plot(
        df_2026["date_est"],
        df_2026["my_goal_cumulative"],
        color=GOAL_COLOR,
        alpha=0.5,
        linewidth=2,
        label="Goal (cumulative)"
    )
    ax.plot(
        df_2026["date_est"],
        df_2026["my_reading_cumulative"],
        color=MY_COLOR,
        linewidth=2,
        label="Reading (cumulative)"
    )

    ax.set_ylabel("Total pages")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    ax.set_xlim(
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-12-31")
    )

    ax.legend(frameon=False)
    ax.set_title("Cumulative Reading vs Goal (2026)")

    plt.tight_layout()
    plt.show()

def create_pie_chart_pages(df_2026, today):
    dow_pages = (
    df_2026[df_2026["date_est"] < today]
    .assign(dow=lambda d: d["date_est"].dt.day_name())
    .groupby("dow")["my_reading"]
    .sum()
    .reindex(
        ["Monday", "Tuesday", "Wednesday", "Thursday",
         "Friday", "Saturday", "Sunday"]
            )
    )

    fig, ax = plt.subplots(figsize=(6, 6))

    ax.pie(
        dow_pages,
        labels=dow_pages.index,
        autopct="%1.1f%%",
        startangle=90
    )
    # Plot
    ax.set_title("Share of Pages Read by Day of Week (2026 YTD)")
    plt.show()

def create_pie_chart_dowfreq(df_2026, today):
    dow_days = (
    df_2026[df_2026["date_est"] < today]
    .assign(
        dow=lambda d: d["date_est"].dt.day_name(),
        read_day=lambda d: d["my_reading"] > 0
    )
    .query("read_day")
    .groupby("dow")
    .size()
    .reindex(
        ["Monday", "Tuesday", "Wednesday", "Thursday",
         "Friday", "Saturday", "Sunday"]
        )
    )

    fig, ax = plt.subplots(figsize=(6, 6))

    ax.pie(
        dow_days,
        labels=dow_days.index,
        autopct="%1.1f%%",
        startangle=90
    )
    # Plot
    ax.set_title("Which Days You Read (Non-Zero Days, 2026 YTD)")
    plt.show()

def create_heatmap_streak(df_2026, today):
    # Calculate streak/day
    df_2026["read_flag"] = df_2026["my_reading"] > 0
    df_2026["streak"] = 0
    current_streak = 0
    for i, row in df_2026.iterrows():
        if row["read_flag"]:
            current_streak += 1
        else:
            current_streak = 0
        df_2026.at[i, "streak"] = current_streak
    # Build grid
    df_2026["week"] = df_2026["date_est"].dt.isocalendar().week
    df_2026["dow"] = df_2026["date_est"].dt.weekday  # Mon=0
    pivot = df_2026.pivot(
        index="dow",
        columns="week",
        values="streak"
    )
    # Mask future dates
    future_mask = df_2026["date_est"] > today
    for _, r in df_2026[future_mask].iterrows():
        pivot.loc[r["dow"], r["week"]] = -1
    # Custom colormap
    cmap = LinearSegmentedColormap.from_list(
    "streaks",
    [ABSENT_COLOR, MY_COLOR]
    )
    # Plot
    fig, ax = plt.subplots(figsize=(18, 4))
    sns.heatmap(
        pivot,
        cmap=cmap,
        cbar=True,
        linewidths=0.2,
        linecolor=ABSENT_COLOR,
        ax=ax
    )

    ax.set_yticks(range(7))
    ax.set_yticklabels(
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        rotation=0
    )

    ax.set_title("Reading Streaks — 2026")
    ax.set_xlabel("Week of Year")
    ax.set_ylabel("")

    plt.tight_layout()
    plt.show()


def main():
    # Load theme
    sns.set_theme(style="whitegrid")
    ## Setup graphics plot
    df = load_ts_reading(DB_PATH)
    # Ensure full 2026 calendar alignment
    df = df.sort_values("date_est")
    df["date_est"] = pd.to_datetime(df["date_est"])
    df_2026 = df[df["date_est"].dt.year == 2026].copy()
    today = pd.Timestamp.today().normalize()
    # Run plotting functions
    print("begin creating graphics")
    create_hair_chart_discrete(df_2026)
    create_hair_chart_cumulative(df_2026)
    create_pie_chart_pages(df_2026, today)
    create_pie_chart_dowfreq(df_2026, today)
    create_heatmap_streak(df_2026, today)

if __name__ == "__main__":
    main()
