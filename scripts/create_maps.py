## For GeoJSON loading 
import json, sqlite3, os, sys
import pandas as pd
import plotly.express as px

# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import *
from map_utils import create_geojson 

# Script constants
shapefile_path, geojson_path = ADM0_SHAPEFILE_PATH, ADM0_GEOJSON_PATH
output_html = VIS_DIR / "maps" / "world_map_author_counts.html"

# Check for presence of desired geojson 
if not Path(geojson_path).exists(): 
    create_geojson(shapefile_path, geojson_path)

# Get data you want to assign to the map
conn = sqlite3.connect(DB_PATH)
# Count authors per country
df_counts = pd.read_sql("""
    SELECT birth_country, COUNT(*) AS author_count
    FROM authors
    GROUP BY birth_country
""", conn)
# Close conn
conn.close()

# Get geojson data
with open(geojson_path) as f:
    geojson = json.load(f)
print("Collected geojson data.")

# Set condition for having an id; changes behavior in plotting
has_id = any("id" in feature for feature in geojson["features"])

# Clean geojson
filtered_features = [
    feature for feature in geojson["features"]
    if feature["properties"]["shapeName"] not in COUNTRIES_TO_REMOVE
]
geojson["features"] = filtered_features

# Grab valid countries for filtering/translating 'authors' table content
if has_id:
    valid_countries = {f["id"] for f in geojson["features"]}
else:
    valid_countries = {f["properties"]["shapeName"] for f in geojson["features"]}
# Filter authors table counts for valid country names
df_counts = df_counts[df_counts['birth_country'].isin(valid_countries)]

print("Identified nonzero author countries: ", list(df_counts["birth_country"].unique()))
# Begin data wrangling and mapping
if has_id: # Change to : does feature in geojson["features"] have feature["id"]?
    countries = [f["id"] for f in geojson["features"]]
    df_geo = pd.DataFrame({"country": countries})
    df_geo = df_geo.merge(
        df_counts, 
        how="left", 
        left_on="country", 
        right_on="birth_country"
    )
    df_geo["author_count"] = df_geo["author_count"].fillna(0)
    # Plot
    fig = px.choropleth(
        df_geo,
        geojson=geojson,
        locations="country",
        color="author_count",
        color_continuous_scale=COLORSCALE,  # Custom scale set above
        range_color=(0, df_geo["author_count"].max()), # Calibrate color scale
        # color = "" # If color exists in the db
    )
else: 
    countries = (f["properties"]["shapeName"] for f in geojson["features"])
    df_geo = pd.DataFrame({"country": countries})
    df_geo = df_geo.merge(
        df_counts, 
        how="left", 
        left_on="country", 
        right_on="birth_country"
    ) 
    df_geo["author_count"] = df_geo["author_count"].fillna(0)
    # Plot
    fig = px.choropleth(
        df_geo,
        geojson=geojson,
        featureidkey="properties.shapeName",
        locations="country",
        color="author_count",
        color_continuous_scale=COLORSCALE, # Custom scale set above
        range_color=(0, df_geo["author_count"].max()), # Calibrate color scale
    )

# Plot setup
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), autosize=True)
# Output
fig.write_html(output_html); # No echo
#