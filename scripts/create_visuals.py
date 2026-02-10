import sqlite3, sys

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap
# from datetime import datetime

###################
# Necessary for chart/graphic handling (and local testing)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VIS_DIR = ROOT / "visuals"
VIS_DIR.mkdir(exist_ok=True)
####################

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


def output_fig(fig_obj, fig_label): # TODO: Can this be more robust?
    out_path = (VIS_DIR / fig_label).with_suffix("")
    fig_obj.savefig(f"{out_path}.svg", bbox_inches="tight")
    fig_obj.savefig(f"{out_path}.png", dpi=300, bbox_inches="tight")
    
## Hair chart
def create_bar_chart_discrete(df, chart_name='bar_daily_2026'):
    # Set up 
    fig, ax = plt.subplots(figsize=(17.5, 5))
    bar_width = 0.4
    ax.bar(
        df["date_est"] - pd.Timedelta(hours=12),
        df["my_goal"],
        width=bar_width,
        color=GOAL_COLOR,
        edgecolor=GOAL_COLOR,
        alpha=0.6,
        label="Goal"
    )
    ax.bar(
        df["date_est"] + pd.Timedelta(hours=12),
        df["my_reading"],
        width=bar_width,
        color=MY_COLOR,
        edgecolor=MY_COLOR,
        label="Progress"
    )
    # Axes
    ax.set_ylim(0, 300) # Approx. maximum pages per day = 300
    ax.set_ylabel("Pages Read")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlim(
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-12-31")
    )
    # Legend
    ax.legend(frameon=False)
    ax.set_title("Daily Reading vs. Goal (2026)")
    # Create layout
    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_bar_chart_cumulative(df, chart_name='bar_cumulative_2026'):
    # Set up
    fig, ax = plt.subplots(figsize=(17.5, 5))
    ax.plot(
        df["date_est"],
        df["my_goal_cumulative"],
        color=GOAL_COLOR,
        alpha=0.5,
        linewidth=2,
        label="Goal (cumulative)"
    )
    ax.plot(
        df["date_est"],
        df["my_reading_cumulative"],
        color=MY_COLOR,
        linewidth=2,
        label="Reading (cumulative)"
    )
    # Axes
    ax.set_ylabel("Total Pages Read")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlim(
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-12-31")
    )
    # Legend
    ax.legend(frameon=False)
    ax.set_title("Cumulative Reading vs. Goal (2026)")
    # Layout
    fig.tight_layout()
    if chart_name: 
        output_fig(fig, chart_name)
    return fig 

def create_pie_chart_pages(df, to_date, chart_name='pie_dow_pages_2026'):
    dow_pages = (
    df[df["date_est"] < to_date]
    .assign(dow=lambda d: d["date_est"].dt.day_name())
    .groupby("dow")["my_reading"]
    .sum()
    .reindex(
        ["Monday", "Tuesday", "Wednesday", "Thursday",
         "Friday", "Saturday", "Sunday"]
            )
    ).fillna(0)
    # Set fig, ax
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(
        dow_pages,
        labels=dow_pages.index,
        autopct="%1.1f%%",
        startangle=90
    )
    # Plot
    ax.set_title("Share of Pages Read by Day of Week (2026 YTD)")
    # Output
    if chart_name: 
        output_fig(fig, chart_name)
    return fig 

def create_pie_chart_dowfreq(df, to_date, chart_name='pie_dow_freq_2026'):
    dow_days = (
    df[df["date_est"] < to_date]
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
    ).fillna(0)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(
        dow_days,
        labels=dow_days.index,
        autopct="%1.1f%%",
        startangle=90
    )
    # Plot
    ax.set_title("Which Days You Read (Non-Zero Days, 2026 YTD)")
    # Output
    if chart_name: 
        output_fig(fig, chart_name)
    return fig 

def create_heatmap_streak(df, to_date, chart_name='heatmap_ytd_2026'):
    # Calculate streak/day
    df["read_flag"] = df["my_reading"] > 0
    df["streak"] = 0
    current_streak = 0
    for i, row in df.iterrows(): # TODO: Not scalable beyond 1 year most likely...? Could lag. Is there a better way? 
        if row["read_flag"]:
            current_streak += 1
        else:
            current_streak = 0
        df.at[i, "streak"] = current_streak
    # Build grid
    df["week"] = df["date_est"].dt.isocalendar().week
    df["dow"] = df["date_est"].dt.weekday  # Monday = 0 index
    pivot = df.pivot(
        index="dow",
        columns="week",
        values="streak"
    )
    # Mask future dates
    future_mask = df["date_est"] > to_date
    for _, r in df[future_mask].iterrows():
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
    # Set up axes and labels
    ax.set_yticks(range(7))
    ax.set_yticklabels(
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        rotation=0
    )
    ax.set_title("Reading Streaks — 2026")
    ax.set_xlabel("Week of Year")
    ax.set_ylabel("")
    # Layout
    fig.tight_layout()
    # Output
    if chart_name: 
        output_fig(fig, chart_name)
    return fig 

def main():
    # Load theme
    sns.set_theme(style="whitegrid")
    ## Setup graphics plot
    df = load_ts_reading(DB_PATH)
    # Ensure full 2026 calendar alignment
    df = df.sort_values("date_est")
    df["date_est"] = pd.to_datetime(df["date_est"])
    df_2026 = df[df["date_est"].dt.year == 2026].copy()
    today = pd.Timestamp.today().normalize() # NOTE: normalize() is good practice for handling date/datetimes (revisit)
    # Run plotting functions
    print("begin creating graphics")
    f1 = create_bar_chart_discrete(df_2026)
    f2 = create_bar_chart_cumulative(df_2026)
    f3 = create_pie_chart_pages(df_2026, today)
    f4 = create_pie_chart_dowfreq(df_2026, today)
    f5 = create_heatmap_streak(df_2026, today)
    # TODO: Create GridSpec dashboard with these figs
    plt.close('all')
    
if __name__ == "__main__":
    main()
