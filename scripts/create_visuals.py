import sqlite3, sys, textwrap, hashlib

import pandas as pd
import numpy as np
import seaborn as sns

import matplotlib.pyplot as plt
import matplotlib.dates as mdates # Special dates
import matplotlib.cm as cm # Color mapping generally
import matplotlib.image as mpimg # Overlaying images on plots
from matplotlib.colors import LinearSegmentedColormap # Special colormap

import streamlit as st

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
    # fig_obj.savefig(f"{out_path}.png", dpi=300, bbox_inches="tight") # Pause generating png as an inferior file type
    
## Text and label handling
def truncate_label(label, max_char=LEGEND_MAX_CHARS):
    return label if len(label) <= max_char else label[:max_char] + "…"

def wrap_label(label, width=LEGEND_MAX_CHARS):
    return "\n".join(textwrap.wrap(label, width=width))

## Color handling
def title_to_color(title, cmap=plt.cm.tab20):
    """Deterministically map title to color. Requires a string."""
    hash_val = int(hashlib.md5(title.encode()).hexdigest(), 16)
    return cmap(hash_val % cmap.N)

def genre_to_color(genre, cmap=plt.cm.tab20): # Same as title_to_color but distinct map
    """Return a deterministic color for a genre string. Requires and accepts"""
    return cmap(abs(hash(genre)) % cmap.N)

def load_ts_reading():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM ts_reading", conn, parse_dates=["date_est"])
    conn.close()
    df = df.sort_values("date_est")
    df["date_est"] = pd.to_datetime(df["date_est"])
    current_year = pd.Timestamp.today().year
    return df[df["date_est"].dt.year == current_year].copy()

# Begin charts
## Hair chart
def create_bar_chart_discrete(to_date=None, db_path=DB_PATH, chart_name='bar_pages_daily_v2'):
    # Load ts and to_date
    if to_date is None:
        to_date = pd.Timestamp.today().normalize()
    df = load_ts_reading()
    df = df[df["date_est"] <= to_date]
    conn = sqlite3.connect(db_path)
    df2 = pd.read_sql(
        """
        SELECT v.date_est, b.title, v.pages_read
        FROM v_daily_book_progress v
        LEFT JOIN books b ON v.issue_id = b.issue_id
        WHERE v.date_est <= :to_date
        """,
        conn,
        params={"to_date": to_date.strftime("%Y-%m-%d")}) # Get titles
    conn.close()
    df2["date_est"] = pd.to_datetime(df2["date_est"])
    # Aggregate in case multiple rows per day/title
    df_stack = (
        df2.groupby(["date_est", "title"], as_index=False)["pages_read"]
        .sum()
    )
    # Pivot so each title becomes a column
    df_pivot = (
        df_stack.pivot(index="date_est", columns="title", values="pages_read")
        .fillna(0)
        .sort_index()
    )
    df_pivot = df_pivot.reindex(df["date_est"]).fillna(0) # Reindex just in case to match "my_goal" df
    # Set up 
    fig, ax = plt.subplots(figsize=(17.5, 5))
    bar_width = 0.4 
    # Semi-transparent shaded area under goal
    ax.fill_between(
        df["date_est"],
        0,
        df["my_goal"],
        color=GOAL_COLOR,
        alpha=0.15  # adjust transparency
    ) # TODO: Can I add a label to a fill_between?
    # Reading bars
    bar_width = 0.6
    bottom = np.zeros(len(df_pivot))

    # Generate distinct colors automatically
    for i, column in enumerate(df_pivot.columns):
        ax.bar(
            df_pivot.index + pd.Timedelta(hours=12),
            df_pivot[column],
            width=bar_width,
            bottom=bottom,
            label=column,
            color=title_to_color(column), # colors[i % len(colors)],
            edgecolor="none"
        )
        bottom += df_pivot[column].values # Stack on bottom
    # Total pages per day
    daily_totals = bottom
    # Find max day
    max_idx = np.argmax(daily_totals)
    max_pages = daily_totals[max_idx]
    max_date = df_pivot.index[max_idx]
    # Add callout
    ax.annotate(
        f"Max: {int(max_pages)}",
        xy=(max_date + pd.Timedelta(hours=12), max_pages),
        xytext=(0, 8), # Offset in points
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=16,
        # fontweight="bold"
    )
    # Axes
    upper = max(max_pages, df["my_goal"].max())
    ax.set_ylim(0, upper * 1.1) # Dynamic
    ax.set_ylabel("Pages Read")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlim(
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-12-31") # TODO: Consider making this dynamic? 
    )
    # Legend
    ax.legend(frameon=False)
    ax.set_title("Daily Reading vs. Goal (2026)")
    # Create layout
    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_bar_chart_cumulative(to_date=None, chart_name='bar_cumulative'):
    if to_date is None:
        to_date = pd.Timestamp.today().normalize()
    df = load_ts_reading()
    # Filter and remove cumulative (my_reading) after today's date
    df_reading = df[df["date_est"] <= to_date].copy()
    # Set up
    fig, ax = plt.subplots(figsize=(17.5, 5))
    # Plot
    ax.plot(
        df["date_est"], # df["date_est"],
        df["my_goal_cumulative"], # df["my_goal_cumulative"],
        color=GOAL_COLOR,
        alpha=0.5,
        linewidth=2,
        label="Goal (c_)"
    )
    # Lower tolerance band (75% → 100%)
    ax.fill_between(
        df["date_est"],
        df["my_goal_cumulative"] * 0.75,
        df["my_goal_cumulative"],
        color=GOAL_COLOR,
        alpha=0.15,
        label="Good"
    )
    # Upper tolerance band (100% → 120%)
    ax.fill_between(
        df["date_est"],
        df["my_goal_cumulative"],
        df["my_goal_cumulative"] * 1.2,
        color=GOAL_COLOR,
        alpha=0.08,
        label="Great"
    )
    ax.bar(
        df_reading["date_est"],
        df_reading["my_reading_cumulative"],
        color=MY_COLOR,
        edgecolor="none",
        linewidth=3,
        label="Reading (c_)"
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

def create_bar_book_velocity(db_path=DB_PATH, chart_name='bar_book_velocity'):
    """Bar chart showing book reading velocity (pages/day)."""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        """
        SELECT title, total_pages, 
            -- Floor speed of 1 day, which matches intent, and adds 1 for inclusive calendar days
            MAX(1, CAST(JULIANDAY(date_ended) - JULIANDAY(date_began) AS INTEGER) + 1) AS days_taken
        FROM books
        WHERE status='completed'
            AND total_pages IS NOT NULL
            AND date_began IS NOT NULL
            AND date_ended IS NOT NULL
        """, conn)
    conn.close()
    # Avoid division by zero
    df = df[df['days_taken'] > 0].copy()
    df['velocity'] = df['total_pages'] / df['days_taken']
    # Sort fastest first (left to right)
    df = df.sort_values("velocity", ascending=False)
    # Plot
    fig, ax = plt.subplots(figsize=(10, 8))
    titles = [truncate_label(t.replace("The ","")) for t in df["title"]]
    ax.barh(titles, 
            df['velocity'], 
            color=MY_COLOR, 
            edgecolor="none")
    ax.invert_yaxis()  # Fastest at top
    # Labels
    ax.set_xlabel("Pages per Day")
    ax.set_title("Book Completion Velocity")
    # Layout
    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_heatmap_streak(to_date=None, chart_name='heatmap_ytd'):
    if to_date is None:
        to_date = pd.Timestamp.today().normalize()
    df = load_ts_reading()  
    
    # Calculate streak/day
    df = df.sort_values("date_est")
    full_range = pd.date_range( # Prepare to fill in missing dates with "0" reading values
        df["date_est"].min(),
        df["date_est"].max(),
        freq="D"
    )
    df = df.set_index("date_est").reindex(full_range).rename_axis("date_est").reset_index()
    df["my_reading"] = df["my_reading"].fillna(0) # Fill dates not in table with "0"
    # Set flag
    df["read_flag"] = df["my_reading"] > 0
    # Create groups that reset after each False
    groups = (~df["read_flag"]).cumsum()
    df["streak"] = df["read_flag"].groupby(groups).cumsum()
    # Build grid
    df["week"] = ((df["date_est"] - df["date_est"].min()).dt.days // 7) # 'Anchor' weeks by first Monday vs. iso
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
        "streaks", [ABSENT_COLOR, MY_COLOR])
    cmap = sns.light_palette(MY_COLOR, as_cmap=True) # Test new cmap
    # Plot
    fig, ax = plt.subplots(figsize=(18, 4))
    sns.heatmap(
        pivot,
        cmap=cmap,
        cbar=False, # Remove color bar (legend)
        linewidths=0.2,
        linecolor=ABSENT_COLOR,
        ax=ax
    )
    # Set up axes and labels
    ax.set_ylabel("")
    ax.set_yticks(range(7))
    ax.set_yticklabels(
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        rotation=0
    )
    ax.set_title("Reading Streaks — 2026")
    # X-axis
    ax.set_xlabel("Week of Year")
    month_starts = df.groupby(df["date_est"].dt.month)["week"].min()
    ax.set_xticks(month_starts)
    ax.set_xticklabels(
        ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
        rotation=0
    )
    # Layout
    fig.tight_layout()
    # Output
    if chart_name: 
        output_fig(fig, chart_name)
    return fig 

def create_height_stack(reference_simple=False, overlay_image=False, chart_name='height_stack_ytd'):
    # Set connection and query for book data
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """
        SELECT title, height, length
        FROM books
        WHERE status = 'completed'
          AND height IS NOT NULL
        ORDER BY created_on ASC
        """, # First-read books go at bottom; length = length at spine
        conn,
    )
    conn.close()
    # Just in case something is wrong with 'height' column
    if df.empty:
        raise ValueError("No completed books with height found.")
    # Set reference height (fixed)
    reference_height, reference_width = MY_HEIGHT, MY_HEAD_HEIGHT*1.25
    # Set up figure
    fig, ax = plt.subplots(figsize=(8, 10))  # portrait orientation
    # Basic layout
    x_ref, x_stack = 0.3, 1
    width_scalar = 0.3 # Desired "standard width" in graphical terms
    
    # Reference bar
    if reference_simple:
        ax.bar(
            x_ref,
            reference_height,
            width=width_scalar,
            color="#121111",
            edge_color="none",
            label="My Height"
        )
    else:
        # Reference bar with proportions estimated
        parts = list(HUMAN_PROPORTIONS.keys())[::-1]  # Feet on bottom
        heights = [HUMAN_PROPORTIONS[p] * MY_HEAD_HEIGHT for p in parts]
        # Colors
        colors = cm.viridis(np.linspace(0, 1, len(parts))) # TBD
        # Plot
        bottom = 0
        for part, h, color in zip(parts, heights, colors):
            ax.bar(
                x_ref,
                h,
                bottom=bottom,
                width=width_scalar,
                color=color,
                edgecolor="none",
                # label=part # To ignore, set = None or possibly "none"
            )
            bottom += h
    if overlay_image: 
        # Draw your reference bar (can be empty or just for spacing)
        ax.bar(0, MY_HEIGHT, width=0.4, color="#444444", edgecolor="none")
        # Load PNG stick figure
        img = mpimg.imread("stick_figure.png")  # path to your PNG
        # Scale and position: match bar height and center on x=0
        x_center, bar_width = 0, 0.4
        ax.imshow(
            img,
            extent=[x_center - bar_width/2, x_center + bar_width/2, 0, MY_HEIGHT],
            aspect='auto',   # stretch image to fill the vertical space
            alpha=0.6,       # semi-transparent
            zorder=5         # make sure it draws on top of bars
        )
    # Stacked books bar
    bottom = 0
    # Generate distinct colors
    colors = cm.tab20(np.linspace(0, 1, len(df))) # Color map for various books
    for (idx, row), color in zip(df.iterrows(), colors):
        # TODO: Add width to query; get book widths; already centered so nothing else changes
        ax.bar(
            x_stack,
            row["height"],
            bottom=bottom,
            width=row["length"]*(width_scalar/reference_width), # Add "width" to input data and set width=row["width"] to get the correct width data # TODO
            color=title_to_color(row["title"]),
            edgecolor="none",
            label=row["title"]
        )
        bottom += row["height"]
    # Add label
    total_height = bottom
    ax.text(
        x_stack,
        total_height + 1,  # small vertical offset
        f"{total_height:.1f}\"",
        ha="center",
        va="bottom",
        fontsize=20,
        # fontweight="bold"
    )
    # Format axes
    ax.set_xticks([x_ref, x_stack])
    ax.set_xticklabels(["Reference Height", "Completed Books (Stacked)"])
    ax.set_ylabel("Height (inches)", fontsize=18)
    ax.tick_params(labelsize=16)
    # Optional: Clean
    ax.spines["top"].set_alpha(0.3)
    ax.spines["right"].set_alpha(0.3) # formerly: .set_visible(False)
    # Legend: Hide legend automatically if too many books AND set limitation on label length 
    ## Truncate only
    handles, labels = ax.get_legend_handles_labels()
    labels = [truncate_label(l.replace("The ","")) for l in labels] # TODO: Also remove "The " from the beginning to save space before trunc
    # Set up legend
    if len(df) <= 10: 
        ax.legend(
            handles, # New
            labels, # New
            # bbox_to_anchor=(1.05, 1), # Want it to float, so hide
            loc="upper right",
            frameon=False,
            fontsize=14,
            facecolor="white",
            # edgecolor="none", # frameon=False does the trick
            framealpha=0.95
        )
        # lgnd.get_frame().set_linewidth(0) # If you want to remove border, set ax.legend() = leg and apply this
    # Set title
    ax.set_title("Total Height of Completed Books vs. Reference", fontsize=18)
    # Layout
    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_pie_chart_pages(to_date=None, chart_name='pie_dow_pages'):
    if to_date is None:
        to_date = pd.Timestamp.today().normalize()
    df = load_ts_reading()
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
    # Set colors
    dow_colors = [DOW_COLORS[d] for d in dow_pages.index]
    # Set fig, ax
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(
        dow_pages,
        labels=dow_pages.index,
        autopct="%1.1f%%",
        colors=dow_colors,
        startangle=90
    )
    # Plot
    ax.set_title("Share of Pages Read by Day of Week (2026 YTD)")
    # Output
    if chart_name: 
        output_fig(fig, chart_name)
    return fig 

def create_pie_chart_dowfreq(to_date=None, chart_name='pie_dow_freq'):
    if to_date is None:
        to_date = pd.Timestamp.today().normalize()
    df = load_ts_reading()
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
    # Set colors
    dow_colors = [DOW_COLORS[d] for d in dow_days.index]
    # Set figure, axes
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(
        dow_days,
        labels=dow_days.index,
        autopct="%1.1f%%",
        colors=dow_colors,
        startangle=90
    )
    # Plot
    ax.set_title("Which Days You Read (Non-Zero Days, 2026 YTD)")
    # Output
    if chart_name: 
        output_fig(fig, chart_name)
    return fig 

def create_pie_zero_nonzero_days(to_date=None, chart_name='pie_zero_days'):
    """Pie chart of Zero vs Non-Zero reading days year-to-date."""
    if to_date is None:
        to_date = pd.Timestamp.today().normalize()
    df = load_ts_reading()
    df = df[df["date_est"]<=to_date].copy()
    counts = [
        (df['my_reading'] == 0).sum(),
        (df['my_reading'] > 0).sum()
    ]
    labels = ["Zero Days", "Non-Zero Days"]
    colors = [ABSENT_COLOR, MY_COLOR]
    
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(counts, labels=labels, autopct="%1.1f%%", startangle=90, colors=colors)
    ax.set_title("Zero vs. Non-Zero Reading Days")
    
    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_pie_chart_genre(chart_name="pie_genre_distribution"):
    # Connect + query
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """
        SELECT genre_primary, genre_secondary
        FROM books
        WHERE genre_primary IS NOT NULL
        """,
        conn,
    )
    conn.close()
    if df.empty:
        raise ValueError("No books found with genre_primary.")

    # Count books per primary genre
    genre_counts = (
        df["genre_primary"]
        .value_counts()
        .sort_values(ascending=False)
    )
    # Optional: collapse very small slices (<5%) into "Other"
    total = genre_counts.sum() # Used later 
    threshold = 0.05  # 5%
    small = genre_counts / total < threshold
    if small.any():
        other_total = genre_counts[small].sum()
        genre_counts = genre_counts[~small]
        genre_counts["Other"] = other_total
    # Colors (consistent per genre if using deterministic mapping)
    colors = [genre_to_color(g) for g in genre_counts.index]
    # Figure
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(
        genre_counts,
        labels=genre_counts.index,
        autopct=lambda pct: f"{int(round(pct/100 * total))} ({pct:.1f}%)", # autopct="%1.1f%%",
        colors=colors,
        startangle=90,
        counterclock=False
    )
    # Title and labeling
    ax.set_title("Books by Primary Genre")
    # Layout
    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_histogram_book_lengths(db_path=DB_PATH, chart_name='hist_book_lengths'):
    """Histogram of total_pages for completed books."""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        "SELECT total_pages FROM books WHERE status='completed' AND total_pages IS NOT NULL",
        conn)
    conn.close()
    # Set fig
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.hist(df['total_pages'], 
            bins=range(0, int(df['total_pages'].max()) + 50, 5),
            color=MY_COLOR, alpha=0.7, edgecolor="none")
    # Labels
    ax.set_xlabel("Total Pages")
    ax.set_ylabel("Number of Books")
    ax.set_title("Distribution of Total Pages (Completed Books)")
    # Layout
    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_histogram_daily_pages(to_date=None, chart_name='hist_pages_per_day'):
    """Histogram of pages read per day with goal line."""
    if to_date is None:
        to_date = pd.Timestamp.today().normalize()
    df = load_ts_reading()
    # Set fig
    fig, ax = plt.subplots(figsize=(12, 6))
    # Histogram
    vals = df.loc[df["my_reading"] > 0, "my_reading"]
    ax.hist(
        vals,
        bins = range(0, int(vals.max()) + 25, 5),
        color=MY_COLOR,
        alpha=0.7,
        edgecolor="none"
    ) # TODO: Plot a label somewhere that notes the number of (non-zero) points constituting the hist; how many days accounted for?
    # Overlay goal line (assumes single fixed value)
    goal_value = df['my_goal'].iloc[0] if 'my_goal' in df.columns else None
    if goal_value:
        ax.axvline(goal_value, color=GOAL_COLOR, linestyle='--', linewidth=2, label=f"Goal: {goal_value}")
    # Labels
    ax.set_xlim(left=0)
    ax.margins(x=0)
    ax.set_xlabel("Pages Read per Day")
    ax.set_ylabel("Frequency")
    ax.set_title("Histogram of Pages Read per Day")
    ax.legend(frameon=False)
    # Layout
    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_timeline_books(chart_name="timeline_books", plot_height=10, label_fontsize=14):
    """Timeline of books published with flags and labels."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """
        SELECT year_published, title
        FROM books
        WHERE year_published IS NOT NULL
        """,
        conn
    )
    conn.close()
    # Get publication range
    df["year_published"] = pd.to_numeric(df["year_published"], errors="coerce")
    df = df.dropna(subset=["year_published"])
    df["year_published"] = df["year_published"].astype(int)
    # Truncate title
    df["title"] = df["title"].str.removeprefix("The ").apply(truncate_label)

    min_year = df["year_published"].min()
    max_year = df["year_published"].max()
    x_min, x_max = min_year - 5, max_year + 5
    x_center = (x_min + x_max) / 2
    
    # Set flag height logic
    max_flag_len = plot_height * 0.85
    sorted_indices = df["year_published"].sort_values().index.tolist()
    left_indices = [idx for idx in sorted_indices if df.loc[idx, "year_published"] <= x_center]
    right_indices = [idx for idx in sorted_indices if df.loc[idx, "year_published"] > x_center]
    y_step = max_flag_len / max(len(left_indices), len(right_indices))
    
    # Rank heights 
    rank_from_end = {}    
    for rank, idx in enumerate(reversed(left_indices)):
        rank_from_end[idx] = rank  # 0 = closest to center, highest = furthest left
    for rank, idx in enumerate(right_indices):
        rank_from_end[idx] = rank  # 0 = closest to center, highest = furthest right
    
    # Establish plot
    fig, ax = plt.subplots(figsize=(20, plot_height))
    ax.axhline(0, color="gray", linestyle="--", linewidth=1, alpha=0.5, zorder=0)

    # Plot
    for _, row in df.iterrows():
        x = row["year_published"]
        flag_len = (rank_from_end[_] + 1) * y_step * (1 if x <= x_center else -1)
        # Plotting and labeling
        ax.plot([x, x], [0, flag_len], color=MY_COLOR, linewidth=0.8, alpha=0.6, zorder=1)
        ax.text(x, flag_len, truncate_label(row["title"].removeprefix("The ")),
                fontsize=label_fontsize, 
                ha="left" if x <= x_center else "right",
                va="bottom" if flag_len >= 0 else "top",
                color="black", alpha=0.85)

    ax.scatter(df["year_published"], [0] * len(df), color=MY_COLOR, alpha=0.7, zorder=2, s=20)

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(plot_height*-1, plot_height)

    step = 10 if (max_year - min_year) > 40 else 5
    xticks = range(int(x_min // step * step), int((x_max // step + 1) * step), step)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(y) for y in xticks], fontsize=label_fontsize, rotation=0)

    ax.set_yticks([])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(True)

    ax.set_xlabel("Year Published", fontsize=label_fontsize+2)
    ax.set_title("Books Published Timeline", fontsize=label_fontsize+4)

    fig.tight_layout()

    if chart_name:
        output_fig(fig, chart_name)
    return fig

def create_error_plot_distance_from_goal(to_date=None, chart_name='error_distance_from_goal'):
    # TODO: #65  
    """
    Plot the 'distance' from the cumulative page target for each day of the year.
    
    y = my_goal_cumulative - my_reading_cumulative
    
    Positive values mean behind goal; negative means ahead.
    y=0 is the midline. X-axis is days of the year with no tick labels.
    """
    if to_date is None:
        to_date = pd.Timestamp.today().normalize()

    df = load_ts_reading()
    df = df.sort_values("date_est").reset_index(drop=True)

    # Split into past (has actual reading data) and future (goal only)
    df_past = df[df["date_est"] <= to_date].copy()
    df_future = df[df["date_est"] > to_date].copy()

    # Compute distance: positive = behind goal, negative = ahead of goal
    df_past["distance"] = df_past["my_goal_cumulative"] - df_past["my_reading_cumulative"]

    # Day-of-year as x (integer 1–365/366)
    df["day_of_year"] = df["date_est"].dt.dayofyear
    df_past["day_of_year"] = df_past["date_est"].dt.dayofyear
    df_future["day_of_year"] = df_future["date_est"].dt.dayofyear

    # Figure setup 
    fig, ax = plt.subplots(figsize=(17.5, 5))

    # Zero midline
    ax.axhline(0, color="gray", linewidth=1, linestyle="--", alpha=0.6, zorder=1)

    # Shade regions: behind (above 0) vs ahead (below 0)
    ax.fill_between(
        df_past["day_of_year"],
        0,
        df_past["distance"],
        where=df_past["distance"] >= 0,
        color=GOAL_COLOR,
        alpha=0.25,
        label="Behind goal"
    )
    ax.fill_between(
        df_past["day_of_year"],
        0,
        df_past["distance"],
        where=df_past["distance"] < 0,
        color=MY_COLOR,
        alpha=0.25,
        label="Ahead of goal"
    )

    # Main distance line (past only)
    ax.plot(
        df_past["day_of_year"],
        df_past["distance"],
        color=MY_COLOR,
        linewidth=2,
        zorder=2
    )

    # Vertical "today" marker
    today_doy = to_date.dayofyear
    ax.axvline(today_doy, color="gray", linewidth=0.8, linestyle=":", alpha=0.5)

    # Annotate current distance
    if not df_past.empty:
        last = df_past.iloc[-1]
        current_dist = last["distance"]
        label_text = (
            f"{'–' if current_dist < 0 else '+'}{abs(int(current_dist))} pages"
        )
        ax.annotate(
            label_text,
            xy=(last["day_of_year"], current_dist),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=14,
            color=MY_COLOR if current_dist < 0 else GOAL_COLOR
        )

    ## Axes 
    # Symmetric y-axis centered on 0
    y_abs_max = df_past["distance"].abs().max() * 1.2 if not df_past.empty else 100
    ax.set_ylim(-y_abs_max, y_abs_max)

    # X: full year span, no tick labels
    ax.set_xlim(1, 366)
    ax.xaxis.set_major_locator(plt.NullLocator())
    ax.set_xlabel("")

    ax.set_ylabel("Pages Behind / Ahead of Goal")
    ax.set_title("Distance from Cumulative Reading Goal (2026)")
    ax.legend(frameon=False)

    fig.tight_layout()
    if chart_name:
        output_fig(fig, chart_name)
    return fig

def main():
    # Load theme
    sns.set_theme(style="whitegrid")
    # Run plotting functions: Charts
    print("begin creating graphics")
    f2 = create_bar_chart_discrete()
    f3 = create_bar_chart_cumulative()
    f4 = create_bar_book_velocity()
    f5 = create_pie_chart_pages()
    f6 = create_pie_chart_dowfreq()
    f7 = create_pie_zero_nonzero_days()
    f8 = create_pie_chart_genre()
    f9 = create_heatmap_streak()
    f10 = create_height_stack()
    f11 = create_histogram_daily_pages()
    f12 = create_histogram_book_lengths()
    f13 = create_timeline_books()
    f14 = create_error_plot_distance_from_goal()
    plt.close('all')
    
if __name__ == "__main__":
    main()
