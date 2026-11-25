import math
import os
from dotenv import load_dotenv
from branca.colormap import LinearColormap
import folium
import json
from pathlib import Path
import pandas as pd
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


def get_map_colour_scale(measurement, area_data):
    """Create a colour scale for the selected measurement."""
    water_colours = ["#E2F5E9", "#A3DFD1", "#52C5C9", "#3191CD", "#5458C1", "#572172"]
    
    if measurement == "Reservoir filling":
        return LinearColormap(water_colours, vmin=0, vmax=100)

    if measurement == "Weekly change":
        # Use fixed limits to make typical weekly changes more visible
        change_colours = ["#A34462", "#CF849A", "#D3D9D7", "#69B5A5", "#238A82"]
        return LinearColormap(change_colours, vmin=-10, vmax=10)
    
    if measurement == "Temperature":
        temperature_colours = ["#2166AC", "#92C5DE", "#FFFFFF", "#F4A582", "#B2182B"]
        return LinearColormap(temperature_colours, vmin=-30, vmax=30)

    if measurement == "Precipitation":
        return LinearColormap(water_colours, vmin=0, vmax=150)

    # Use the same scale for stored energy and reservoir capacity
    maximum = area_data[["reservoir_capacity_twh", "stored_energy_twh"]].max().max()
    limit = max(1, math.ceil(maximum)) if pd.notna(maximum) and math.isfinite(maximum) else 1
    return LinearColormap(water_colours, vmin=0, vmax=limit)


def create_map(area_type, area_number, values, colour_scale, measurement, unit):
    """Create a map coloured by the selected measurement."""
    areas = load_geojson()
    selected_area = f"{area_type}{area_number}"

    # Display only areas of the selected type to avoid overlapping geometries
    features = []

    for feature in areas["features"]:
        if feature["properties"]["area_type"] != area_type:
            continue

        properties = feature["properties"].copy()
        value = values.get(properties["area_number"])

        # Assign a colour and tooltip value to each area
        if pd.notna(value) and math.isfinite(value):
            properties["map_color"] = colour_scale.rgb_hex_str(value)

            if measurement == "Weekly change":
                properties["map_value"] = f"{value:+.2f} {unit}"
            else:
                properties["map_value"] = f"{value:.2f} {unit}"
        else:
            properties["map_color"] = "#536064"
            properties["map_value"] = "No data"

        features.append({**feature, "properties": properties})

    geojson = {"type": "FeatureCollection", "features": features}

    # Use CARTO Dark Matter when the API key is available
    if carto_api_key:
        m = folium.Map(location=[64.5, 15], zoom_start=5, tiles=None)

        folium.TileLayer(tiles="https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key=" + carto_api_key,
                         attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, &copy; <a href="https://carto.com/">CARTO</a>',
                         name="Dark Matter").add_to(m)
    else:
        # Fall back to OpenStreetMap if no API key is configured
        m = folium.Map(location=[64.5, 15], zoom_start=5, tiles="OpenStreetMap")

    # Highlight the selected region without changing its measurement colour
    def style_function(feature):
        properties = feature["properties"]
        selected = properties["area_id"] == selected_area

        return {"fillColor": properties["map_color"],
                "fillOpacity": 0.80,
                "color": "#FFFFFF" if selected else "#829995",
                "weight": 3 if selected else 1}

    layer = folium.GeoJson(geojson, style_function=style_function,
                           tooltip=folium.GeoJsonTooltip(fields=["area_id", "map_value"], aliases=["Area:", f"{measurement}:"]))

    # Keep the polygons separate so they can be updated without recreating the map
    area_layer = folium.FeatureGroup(name="Reservoir areas")
    layer.add_to(area_layer)

    if features:
        m.fit_bounds(layer.get_bounds())

    return m, area_layer


def show_map_legend(colour_scale, measurement, unit):
    """Display the colour scale below the map."""
    colours = [colour_scale.rgb_hex_str(value) for value in colour_scale.index]
    gradient = ", ".join(colours)

    labels = [f"{value:.1f}".rstrip("0").rstrip(".") for value in colour_scale.index]
    
    # Indicate that values outside the scale use the endpoint colours
    if measurement in ["Weekly change", "Temperature"]:
        labels[0] = f"≤ {labels[0]}"

    if measurement in ["Weekly change", "Temperature", "Precipitation", "Reservoir filling"]:
        labels[-1] = f"≥ {labels[-1]}"

    ticks = "".join(f"<span>{label}</span>" for label in labels)

    st.caption(f"{measurement} ({unit})")

    st.html(f"""
        <div style="height: 12px;
                    border-radius: 4px;
                    background: linear-gradient(to right, {gradient});">
        </div>
        <div style="display: flex;
                    justify-content: space-between;
                    font-size: 12px;
                    margin-top: 4px;">
            {ticks}
        </div>
        <div style="display: flex;
                    gap: 24px;
                    align-items: center;
                    margin-top: 10px;
                    font-size: 12px;">
            <span>
                <span style="display: inline-block;
                             width: 12px;
                             height: 12px;
                             background: #536064;
                             border-radius: 2px;
                             vertical-align: middle;
                             margin-right: 4px;"></span>
                No data
            </span>
            <span>
                <span style="display: inline-block;
                             width: 12px;
                             height: 12px;
                             border: 2px solid #FFFFFF;
                             border-radius: 2px;
                             vertical-align: middle;
                             margin-right: 4px;"></span>
                Selected region
            </span>
        </div>
        """)


def get_clicked_area(area_type, latitude, longitude):
    """Return the area number containing the clicked location."""
    point = Point(longitude, latitude)

    for feature in load_geojson()["features"]:
        properties = feature["properties"]

        if properties["area_type"] == area_type:
            if shape(feature["geometry"]).covers(point):
                return properties["area_number"]

    return None