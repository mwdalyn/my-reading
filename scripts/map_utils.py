'''Utilities for manipulating shapefiles, mapping actions, etc..'''
import geopandas as gpd

def create_geojson(shapefile_path, output_json_path):
    # Load your shapefile
    gdf = gpd.read_file(shapefile_path) # Requires necessary files colocated
    # Confirm in WGS84 (lat/lon)
    gdf = gdf.to_crs(epsg=4326)
    gdf["geometry"] = gdf["geometry"].simplify(0.05, preserve_topology=True)
    # Output to file
    gdf.to_file(output_json_path, driver="GeoJSON")
