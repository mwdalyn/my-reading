import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import subprocess, sys, os

from create_visuals import (
    create_bar_chart_discrete,
    create_bar_chart_cumulative,
    create_bar_book_velocity,
    create_pie_chart_pages,
    create_pie_chart_dowfreq,
    create_pie_zero_nonzero_days,
    create_pie_chart_genre,
    create_heatmap_streak,
    create_height_stack,
    create_histogram_daily_pages,
    create_histogram_book_lengths,
    create_timeline_books,
)

def create_streamlit():
    # Sns theme
    sns.set_theme(style="whitegrid")
    # Input tray
    st.sidebar.header("Settings")
    to_date = st.sidebar.date_input(
        "Show data as of",
        value=pd.Timestamp.today().date()
    )
    to_date = pd.Timestamp(to_date)
    
    # Title
    st.title("Reading Dashboard")
    # H1
    st.header("Pace")
    st.subheader("Daily Reading vs. Goal")
    fig = create_bar_chart_discrete(to_date=to_date, chart_name=None)
    st.pyplot(fig)
    plt.close(fig)
    st.subheader("Cumulative Reading vs. Goal")
    fig = create_bar_chart_cumulative(to_date=to_date, chart_name=None)
    st.pyplot(fig)
    plt.close(fig)
    st.subheader("Pages per Day Histogram")
    fig = create_histogram_daily_pages(to_date=to_date, chart_name=None)
    st.pyplot(fig)
    plt.close(fig)
    # H2
    st.header("Habits")
    st.subheader("Reading Streak Heatmap")
    fig = create_heatmap_streak(to_date=to_date, chart_name=None)
    st.pyplot(fig)
    plt.close(fig)
    # Pie charts
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Pages by Day of Week")
        fig = create_pie_chart_pages(to_date=to_date, chart_name=None)
        st.pyplot(fig)
        plt.close(fig)
    with col2:
        st.subheader("Days You Read")
        fig = create_pie_chart_dowfreq(to_date=to_date, chart_name=None)
        st.pyplot(fig)
        plt.close(fig)
    with col3:
        st.subheader("Zero vs Non-Zero Days")
        fig = create_pie_zero_nonzero_days(to_date=to_date, chart_name=None)
        st.pyplot(fig)
        plt.close(fig)
    # H3
    st.header("Books")
    st.subheader("Book Completion Velocity")
    fig = create_bar_book_velocity(chart_name=None)
    st.pyplot(fig)
    plt.close(fig)
    st.subheader("Genre Distribution")
    fig = create_pie_chart_genre(chart_name=None)
    st.pyplot(fig)
    plt.close(fig)
    st.subheader("Book Length Distribution")
    fig = create_histogram_book_lengths(chart_name=None)
    st.pyplot(fig)
    plt.close(fig)
    st.subheader("Height Stack")
    fig = create_height_stack(chart_name=None)
    st.pyplot(fig)
    plt.close(fig)
    st.subheader("Publication Timeline")
    fig = create_timeline_books(chart_name=None)
    st.pyplot(fig)
    plt.close(fig)

# Run app
if __name__ == "__main__":
    if os.environ.get("STREAMLIT_RUNNING") != "1":
        os.environ["STREAMLIT_RUNNING"] = "1"
        subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])
    else:
        create_streamlit()