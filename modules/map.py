import os
from dotenv import load_dotenv
import folium
import json
from pathlib import Path
from shapely.geometry import Point, shape
import streamlit as st


load_dotenv()
carto_api_key = os.getenv("CARTO_API_KEY")


@st.cache_data
def load_geojson():
    """Load the geographical boundaries for all Magasinstatistikk areas."""
    data_path = Path(__file__).resolve().parents[1] / "data" / "geographical"

    with open(data_path / "reservoir_areas.geojson", encoding="utf-8") as file:
        return json.load(file)


def create_map(area_type, area_number):
    """Create a map showing the selected geographical area type."""
    areas = load_geojson()
    selected_area = f"{area_type}{area_number}"

    # Display only areas of the selected type to avoid overlapping geometries
    features = [feature for feature in areas["features"] if feature["properties"]["area_type"] == area_type]

    geojson = {"type": "FeatureCollection", "features": features}

    # Use CARTO Dark Matter when the API key is available
    if carto_api_key:
        m = folium.Map(location=[64.5, 15], zoom_start=5, tiles=None)

        folium.TileLayer(tiles="https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key=" + carto_api_key,
                         attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
                         name="Dark Matter").add_to(m)
    else:
        # Fall back to OpenStreetMap if no API key is available
        m = folium.Map(location=[64.5, 15], zoom_start=5, tiles="OpenStreetMap")

    # Highlight the region selected in the sidebar
    def style_function(feature):
        selected = feature["properties"]["area_id"] == selected_area

        return {"fillColor": "#BCD7D0",
                "fillOpacity": 0.35 if selected else 0.15,
                "color": "#FFFFFF" if selected else "#829995",
                "weight": 3 if selected else 1}

    layer = folium.GeoJson(geojson, style_function=style_function, tooltip=folium.GeoJsonTooltip(fields=["area_id"], aliases=["Area:"]))

    # Keep the polygons separate so they can be updated without recreating the map
    area_layer = folium.FeatureGroup(name="Reservoir areas")
    layer.add_to(area_layer)

    if features:
        m.fit_bounds(layer.get_bounds())

    return m, area_layer


def get_clicked_area(area_type, latitude, longitude):
    """Return the area number containing the clicked location."""
    point = Point(longitude, latitude)

    for feature in load_geojson()["features"]:
        properties = feature["properties"]

        if properties["area_type"] == area_type:
            if shape(feature["geometry"]).covers(point):
                return properties["area_number"]

    return None
