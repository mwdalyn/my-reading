## For GeoJSON loading
import json, sqlite3, os, sys
import pandas as pd
import plotly.express as px

from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import *
from map_utils import create_geojson

# Script constants
shapefile_path, geojson_path = ADM0_SHAPEFILE_PATH, ADM0_GEOJSON_PATH
output_html = VIS_DIR / "maps" / "world_map_author_counts.html"

if not Path(geojson_path).exists():
    create_geojson(shapefile_path, geojson_path)

# Get data
conn = sqlite3.connect(DB_PATH)
df_counts = pd.read_sql("""
    SELECT birth_country, COUNT(*) AS author_count
    FROM authors
    GROUP BY birth_country
""", conn)
conn.close()

# Get geojson
with open(geojson_path) as f:
    geojson = json.load(f)
print("Collected geojson data.")

# Clean geojson - remove unwanted countries
geojson["features"] = [
    feature for feature in geojson["features"]
    if feature["properties"]["shapeName"] not in COUNTRIES_TO_REMOVE
]

# Always key off shapeName - the ids in this file are arbitrary sequential ints, not country codes
valid_countries = {f["properties"]["shapeName"] for f in geojson["features"]}
df_counts = df_counts[df_counts["birth_country"].isin(valid_countries)]

print("Identified nonzero author countries: ", list(df_counts["birth_country"].unique()))

countries = [f["properties"]["shapeName"] for f in geojson["features"]]
df_geo = pd.DataFrame({"country": countries})
df_geo = df_geo.merge(
    df_counts,
    how="left",
    left_on="country",
    right_on="birth_country"
)
df_geo["author_count"] = df_geo["author_count"].fillna(0)

# Sanity check: catch silent join failures before they render as a blank map
matched = int((df_geo["author_count"] > 0).sum())
print(f"Matched rows: {matched}/{len(df_geo)}")
if matched == 0:
    print("WARNING: no rows matched — check for country-name mismatches "
          "between authors.birth_country and geojson shapeName values.")
    unmatched_sample = sorted(valid_countries)[:10]
    print("Sample shapeName values:", unmatched_sample)
    print("Sample birth_country values:", df_counts["birth_country"].unique()[:10].tolist())

fig = px.choropleth(
    df_geo,
    geojson=geojson,
    featureidkey="properties.shapeName",
    locations="country",
    color="author_count",
    color_continuous_scale=COLORSCALE,
    range_color=(0, max(df_geo["author_count"].max(), 1)),  # avoid (0,0) collapse
)

fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), autosize=True)
fig.write_html(output_html)