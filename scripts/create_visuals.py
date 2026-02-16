import sqlite3, sys, textwrap, hashlib

import pandas as pd
import numpy as np
import seaborn as sns

import matplotlib.pyplot as plt
import matplotlib.dates as mdates # Special dates
import matplotlib.cm as cm # Color mapping generally
import matplotlib.image as mpimg # Overlaying images on plots
from matplotlib.colors import LinearSegmentedColormap # Special colormap

import folium
from folium.plugins import MarkerCluster

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
def truncate_label(label):
    return label if len(label) <= LEGEND_MAX_CHARS else label[:LEGEND_MAX_CHARS] + "…"

def wrap_label(label, width=LEGEND_MAX_CHARS):
    return "\n".join(textwrap.wrap(label, width=width))

## Color handling
def title_to_color(title, cmap=plt.cm.tab20):
    """Deterministically map title to color."""
    hash_val = int(hashlib.md5(title.encode()).hexdigest(), 16)
    color_index = hash_val % cmap.N
    return cmap(color_index)

# Begin charts
## Hair chart
def create_bar_chart_discrete_v1(df, chart_name='bar_pages_daily_v1'):
    # Set up 
    fig, ax = plt.subplots(figsize=(17.5, 5))
    bar_width = 0.4 
    # Goal line
    ax.plot( 
        df["date_est"], # - pd.Timedelta(hours=12), # 12 hour offset for the sake of spacing
        df["my_goal"],
        color=GOAL_COLOR,
        alpha=0.6,
        linewidth=2,
        linestyle="--",
        label="Goal"
    )
    # Semi-transparent shaded area under goal
    ax.fill_between(
        df["date_est"],
        0,
        df["my_goal"],
        color=GOAL_COLOR,
        alpha=0.15  # adjust transparency
    )
    # Reading bars
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

def create_bar_chart_discrete_v2(df, db_path=DB_PATH, chart_name='bar_pages_daily_v2'):
    conn = sqlite3.connect(db_path)
    df2 = pd.read_sql(
        """
        SELECT v.date_est, b.title, v.pages_read
        FROM v_daily_book_progress v
        LEFT JOIN books b
            ON v.issue_id = b.issue_id
        """, conn) # Get titles
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
    # Goal line
    ax.plot( 
        df["date_est"], # - pd.Timedelta(hours=12), # 12 hour offset for the sake of spacing
        df["my_goal"],
        color=GOAL_COLOR,
        alpha=0.6,
        linewidth=2,
        linestyle="--",
        label="Goal"
    )
    # Semi-transparent shaded area under goal
    ax.fill_between(
        df["date_est"],
        0,
        df["my_goal"],
        color=GOAL_COLOR,
        alpha=0.15  # adjust transparency
    )
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

def create_bar_chart_cumulative(df, chart_name='bar_cumulative'):
    # Set up
    fig, ax = plt.subplots(figsize=(17.5, 5))
    # Filter and remove cumulative (my_reading) after today's date
    today = pd.Timestamp.today().normalize()
    df_reading = df[df["date_est"] <= today].copy()
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
               JULIANDAY(date_ended) - JULIANDAY(date_began) AS days_taken
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

def create_heatmap_streak(df, to_date, chart_name='heatmap_ytd'):
    # Calculate streak/day
    df = df.sort_values("date_est")
    df["read_flag"] = df["my_reading"] > 0
    # Create groups that reset after each False
    groups = (~df["read_flag"]).cumsum()
    df["streak"] = df["read_flag"].groupby(groups).cumsum()
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

def create_pie_chart_pages(df, to_date, chart_name='pie_dow_pages'):
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

def create_pie_chart_dowfreq(df, to_date, chart_name='pie_dow_freq'):
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

def create_pie_zero_nonzero_days(df, chart_name='pie_zero_days'):
    """Pie chart of Zero vs Non-Zero reading days year-to-date."""
    today = pd.Timestamp.today().normalize()
    df_2026 = df[df["date_est"].dt.year == 2026].copy()
    counts = [
        (df_2026['my_reading'] == 0).sum(),
        (df_2026['my_reading'] > 0).sum()
    ]
    labels = ["Zero Days", "Non-Zero Days"]
    colors = [ABSENT_COLOR, MY_COLOR]
    
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(counts, labels=labels, autopct="%1.1f%%", startangle=90, colors=colors)
    ax.set_title("Zero vs Non-Zero Reading Days (YTD)")
    
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
            bins=range(0, int(df['total_pages'].max())+50, 25),
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

def create_histogram_daily_pages(df, chart_name='hist_pages_per_day'):
    """Histogram of pages read per day with goal line."""
    # Set fig
    fig, ax = plt.subplots(figsize=(12, 6))
    # Histogram
    vals = df.loc[df["my_reading"] > 0, "my_reading"]
    ax.hist(
        vals,
        bins = range(0, int(vals.max()) + 25, 25),
        color=MY_COLOR,
        alpha=0.7,
        edgecolor="none"
    )
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

def create_timeline_books(chart_name="timeline_books", plot_height=2.5):
    """Timeline of books published with a horizontal reference line."""
    # Connect and fetch data
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """
        SELECT year_published
        FROM books
        WHERE year_published IS NOT NULL
        """,
        conn
    )
    conn.close()

    # Ensure numeric years
    df["year_published"] = pd.to_numeric(df["year_published"], errors="coerce")
    df = df.dropna(subset=["year_published"])
    df["year_published"] = df["year_published"].astype(int)

    min_year = df["year_published"].min()
    max_year = df["year_published"].max()

    # Set figure height and width
    fig, ax = plt.subplots(figsize=(20, plot_height))

    # Horizontal reference line at y=1
    ax.axhline(1, color="gray", linestyle="--", linewidth=1, alpha=0.5, zorder=0)

    # Scatter dots at y=1
    ax.scatter(df["year_published"], [1] * len(df),
               color=MY_COLOR, alpha=0.7, zorder=1)

    # X-axis limits and ticks
    ax.set_xlim(min_year - 2, max_year + 2)
    step = 10 if (max_year - min_year) > 40 else 5
    xticks = range(int(min_year // step * step),
                   int((max_year // step + 1) * step),
                   step)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(y) for y in xticks], rotation=45)

    # Hide y-axis ticks
    ax.set_yticks([])

    # Remove top and right spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    # Optional: remove bottom spine if you want only left border
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(True)

    # Labels and title
    ax.set_xlabel("Year Published")
    ax.set_title("Books Published Timeline")

    # Layout
    fig.tight_layout()

    if chart_name:
        output_fig(fig, chart_name)
    return fig

# Map visuals
def create_map_authors_country(chart_name="map_authors_birth_country"):
    """Folium map with a pin per author based on birth_country. Add tooltip: first_name, last_name, birth_year."""
    # Load authors with birth_country
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """
        SELECT first_name, last_name, birth_year, birth_country
        FROM authors
        WHERE birth_country IS NOT NULL
        """,
        conn
    )
    conn.close()

    if df.empty:
        raise ValueError("No authors with birth_country found.")
    
    # Approximate lat/lon using a simple country lookup
    import geopy
    from geopy.geocoders import Nominatim
    geolocator = Nominatim(user_agent="my_reading_map")
    
    # Create folium map centered roughly
    fmap = folium.Map(location=[20,0], zoom_start=2)
    cluster = MarkerCluster().add_to(fmap)
    
    country_cache = {}
    
    for _, row in df.iterrows():
        country = row["birth_country"]
        tooltip = f"{row['first_name']} {row['last_name']}, {row['birth_year']}"
        
        # Geocode country (with caching)
        if country not in country_cache:
            try:
                loc = geolocator.geocode(country)
                if loc:
                    country_cache[country] = (loc.latitude, loc.longitude)
                else:
                    country_cache[country] = None
            except Exception:
                country_cache[country] = None
        
        coords = country_cache.get(country)
        if coords:
            folium.Marker(
                location=coords,
                tooltip=tooltip,
                icon=folium.Icon(color="blue", icon="user")
            ).add_to(cluster)
    
    # Save as HTML
    out_path = (VIS_DIR / f"{chart_name}.html").with_suffix("")
    fmap.save(f"{out_path}.html")
    return fmap

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
    f1 = create_bar_chart_discrete_v1(df_2026)
    f1_2 = create_bar_chart_discrete_v2(df_2026)
    # f2 = create_bar_chart_cumulative(df_2026)
    # f9 = create_bar_book_velocity()
    # f3 = create_pie_chart_pages(df_2026, today)
    # f4 = create_pie_chart_dowfreq(df_2026, today)
    # f8 = create_pie_zero_nonzero_days(df_2026)
    # f5 = create_heatmap_streak(df_2026, today)
    f6 = create_height_stack()
    # f7 = create_histogram_daily_pages(df_2026)
    # f10 = create_histogram_book_lengths()
    # f11 = create_timeline_books()
    # m1 = create_map_authors_country()
    # TODO: Create GridSpec dashboard with these figs
    plt.close('all')
    
if __name__ == "__main__":
    main()
