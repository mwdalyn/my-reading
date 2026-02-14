import sqlite3, sys, textwrap

import pandas as pd
import numpy as np
import seaborn as sns

import matplotlib.pyplot as plt
import matplotlib.dates as mdates # Special dates
import matplotlib.cm as cm # Color mapping generally
import matplotlib.image as mpimg # Overlaying images on plots
from matplotlib.colors import LinearSegmentedColormap # Special colormap

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
    fig_obj.savefig(f"{out_path}.png", dpi=300, bbox_inches="tight")
    
## Text and label handling
def truncate_label(label):
    return label if len(label) <= LEGEND_MAX_CHARS else label[:LEGEND_MAX_CHARS] + "…"

def wrap_label(label, width=LEGEND_MAX_CHARS):
    return "\n".join(textwrap.wrap(label, width=width))

# Begin charts
## Hair chart
def create_bar_chart_discrete(df, chart_name='bar_daily_2026'):
    # Set up 
    fig, ax = plt.subplots(figsize=(17.5, 5))
    bar_width = 0.4 
    ax.plot( 
        df["date_est"], # - pd.Timedelta(hours=12), # 12 hour offset for the sake of spacing
        df["my_goal"],
        color=GOAL_COLOR,
        alpha=0.6,
        linewidth=2,
        label="Goal"
    )
    ax.bar(
        df["date_est"] + pd.Timedelta(hours=12), # 12 hour offset for the sake of spacing
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

def create_bar_chart_cumulative(df, chart_name='bar_cumulative_2026'):
    # Set up
    fig, ax = plt.subplots(figsize=(17.5, 5))
    ax.plot(
        df["date_est"],
        df["my_goal_cumulative"],
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
    ax.plot(
        df["date_est"],
        df["my_reading_cumulative"],
        color=MY_COLOR,
        linewidth=2,
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
        ax.bar(0, MY_HEIGHT, width=0.4, color="#444444")
        # Load PNG stick figure
        img = mpimg.imread("stick_figure.png")  # path to your PNG
        # Scale and position: match bar height and center on x=0
        x_center = 0
        bar_width = 0.4
        # extent = [x_min, x_max, y_min, y_max]
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
            color=color,
            edgecolor="none",
            label=row["title"]
        )
        bottom += row["height"]
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
    # f1 = create_bar_chart_discrete(df_2026)
    # f2 = create_bar_chart_cumulative(df_2026)
    # f3 = create_pie_chart_pages(df_2026, today)
    # f4 = create_pie_chart_dowfreq(df_2026, today)
    # f5 = create_heatmap_streak(df_2026, today)
    f6 = create_height_stack()
    # TODO: Create GridSpec dashboard with these figs
    plt.close('all')
    
if __name__ == "__main__":
    main()
