import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from modules.magasinstatistikk_data import load_magasinstatistikk_data
from modules.map import create_map, get_clicked_area, get_map_colour_scale, show_map_legend
from modules.weather import load_weather_week


# Configure the application layout and browser tab
st.set_page_config(page_title="IND320 Energy Project", layout="wide")


def update_map_selection():
    """Update the selected region after a map click."""
    area_type = st.session_state["selected_area_type"]
    map_data = st.session_state.get(f"reservoir_map_{area_type}", {})
    clicked = map_data.get("last_object_clicked")

    if clicked:
        area_number = get_clicked_area(area_type, clicked["lat"], clicked["lng"])

        if area_number is not None:
            st.session_state["selected_area_number"] = area_number


def main():
    """Render the home page."""
    st.title("IND320 Energy Project")

    st.write("")
    st.write("Explore Norwegian reservoir, weather, electricity transfer and currency exchange data.")

    measurements = {"Reservoir filling": ("reservoir_fill_ratio", 100, "%"),
                    "Stored energy": ("stored_energy_twh", 1, "TWh"),
                    "Reservoir capacity": ("reservoir_capacity_twh", 1, "TWh"),
                    "Weekly change": ("reservoir_fill_ratio_change", 100, "pp"),
                    "Temperature": ("temperature_mean_c", 1, "°C"),
                    "Precipitation": ("precipitation_total_mm", 1, "mm")}

    date_column, measurement_column = st.columns(2)

    with date_column:
        reference_week = st.selectbox("Reference week", observation_dates,
                                      format_func=lambda date: date.strftime("%d %b %Y"),
                                      key="reference_week",
                                      persist_state="session",
                                      help="Select the week for which reservoir and weather data are displayed.")

    with measurement_column:
        measurement = st.selectbox("Colour map by", list(measurements), key="map_measurement", persist_state="session")

    selected_column, scale, unit = measurements[measurement]

    # Select all regions of the current area type for the reference week
    area_data = df.loc[df["area_type"] == selected_area_type]
    week_data = area_data.loc[area_data["date_id"].dt.date == reference_week]

    # Keep loaded weather separate for each area type and reference week
    weather_key = (selected_area_type, reference_week)
    weather_data = st.session_state.setdefault("map_weather_data", {}).setdefault(weather_key, {})

    if measurement in ["Temperature", "Precipitation"]:
        st.caption("Weekly weather estimates based on 100 sampled locations per region.")

        # ERA5 data are published with a five-day delay
        today = pd.Timestamp.now(tz="Europe/Oslo").date()
        latest_weather_date = today - pd.Timedelta(days=5)

        # Precipitation requires data from the following Monday
        required_end_date = reference_week + pd.Timedelta(days=1)

        missing_areas = [number for number in area_numbers if number not in weather_data]

        if missing_areas and required_end_date > latest_weather_date:
            st.info("ERA5 weather data are published with a delay of approximately five days. "
                    "Please select an earlier reference week.")

        elif missing_areas:
            button_label = "Load weather data" if not weather_data else "Load missing weather data"

            if st.button(button_label, key="load_map_weather"):
                progress = st.progress(0, text="Loading regional weather data...")
                failed_areas = []

                for i, number in enumerate(missing_areas):
                    region = f"{selected_area_type}{number}"

                    try:
                        weather_data[number] = load_weather_week(region, reference_week, n_points=100)
                    except Exception as exc:
                        failed_areas.append(f"{region}: {exc}")

                    progress.progress((i + 1) / len(missing_areas), text=f"Processed {region}")

                progress.empty()

                if failed_areas:
                    st.warning(f"Weather data unavailable for {len(failed_areas)} region(s).")

                    with st.expander("Error details"):
                        for error in failed_areas:
                            st.write(error)

        st.caption(f"Weather available for {len(weather_data)} of {len(area_numbers)} regions.")
        values = {number: row[selected_column] for number, row in weather_data.items()}

    else:
        values = (week_data.set_index("area_number")[selected_column] * scale).to_dict()

    colour_scale = get_map_colour_scale(measurement, area_data)

    map_column, info_column = st.columns([3, 2])

    with map_column:
        m, area_layer = create_map(selected_area_type, selected_area_number,
                                   values, colour_scale, measurement, unit)

        st_folium(m, key=f"reservoir_map_{selected_area_type}", height=800, width=None, feature_group_to_add=area_layer,
                  returned_objects=["last_object_clicked"], on_change=update_map_selection)

        show_map_legend(colour_scale, measurement, unit)

        st.caption("Click an area on the map or use the region selectors in the sidebar.")

    with info_column:
        st.subheader("Selected region")
        st.write(f"**{selected_area_type}{selected_area_number}**")
        st.caption(f"Observation: {reference_week:%d %b %Y}")

        # Select the observation for the chosen region
        observation = week_data.loc[week_data["area_number"] == selected_area_number]
        
        if observation.empty:
            st.info("No reservoir observations are available for the selected week.")
        else:
            row = observation.iloc[0]
            metrics = [("Reservoir filling", "reservoir_fill_ratio", ".2%", 1, ""),
                       ("Stored energy", "stored_energy_twh", ".3f", 1, " TWh"),
                       ("Reservoir capacity", "reservoir_capacity_twh", ".3f", 1, " TWh"),
                       ("Weekly change", "reservoir_fill_ratio_change", "+.2f", 100, " pp")]

            for label, column, fmt, scale, unit in metrics:
                value = row[column]

                with st.container(border=True):
                    st.metric(label, f"{value * scale:{fmt}}{unit}" if pd.notna(value) else "Unavailable")

        # Show both weather measurements once the selected region has been loaded
        if selected_area_number in weather_data:
            weather = weather_data[selected_area_number]

            with st.container(border=True):
                st.metric("Mean weekly temperature", f"{weather['temperature_mean_c']:.2f} °C")

            with st.container(border=True):
                st.metric("Total weekly precipitation", f"{weather['precipitation_total_mm']:.2f} mm")
        elif measurement in ["Temperature", "Precipitation"]:
            st.info("Weather data have not been loaded or are unavailable for the selected region.")

    st.write("")
    st.subheader("What you can explore")

    st.markdown(
        "- **Magasinstatistikk:** Explore weekly reservoir measurements, trends and comparisons between regions.\n"
        "- **Electricity Transfers:** Explore annual electricity transfers and monthly flows between Norway and neighbouring bidding zones.\n"
        "- **Currency Exchange Rates:** Explore historical EUR and USD exchange rates against NOK.\n"
        "- **Reservoir Analysis:** Explore seasonal patterns in reservoir filling degree using STL and spectrograms.\n"
        "- **Weather Analysis:** Download hourly ERA5 weather data and analyse unusual precipitation (SPC) and temperature (LOF).")

    st.write("")
    st.subheader("Getting started")

    st.write(
        "Select a region on the map or in the sidebar to explore reservoir and weather data. "
        "Use the reference week to view historical reservoir measurements. "
        "The analysis pages have their own date and analysis settings.")

    st.caption("Electricity Transfers and Currency Exchange Rates are independent of the selected region.")

    with st.expander("Data sources"):
        st.markdown(
            "- [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/): Weekly reservoir measurements.\n"
            "- [NVE Atlas](https://atlas.nve.no/vertigisstudio/web/?app=e0080b63a0c445a5a47e6d8c3b53ad8c): Electricity bidding zones and hydrological regions.\n"
            "- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api): ERA5 weather data. "
            "Regional estimates are based on 100 sampled locations, with temperature averaged and precipitation accumulated over the selected week.")

# Register the pages and organise them into navigation groups
pages = {"": [st.Page(main, title="Home", icon=":material/home:", default=True)],
         "Data overview": [st.Page("pages/2_Magasinstatistikk.py", title="Magasinstatistikk", icon=":material/water_drop:"),
                           st.Page("pages/6_Cross_Border_Transfers.py", title="Electricity Transfers", icon=":material/bolt:"),
                           st.Page("pages/7_Currency_Exchange_Rates.py", title="Currency Exchange Rates", icon=":material/currency_exchange:")],
         "Data analysis": [st.Page("pages/4_Reservoir_Analysis.py", title="Reservoir Analysis", icon=":material/query_stats:"),
                           st.Page("pages/5_Weather_Analysis.py", title="Weather Analysis", icon=":material/cloud:")],
         "Forecasting": [st.Page("pages/8_Reservoir_Forecasting.py", title="Reservoir Forecasting", icon=":material/trending_up:")]}

page = st.navigation(pages)

# Get the available reservoir regions and observation dates
df = load_magasinstatistikk_data()
area_types = sorted(df["area_type"].dropna().unique())
observation_dates = sorted(df["date_id"].dropna().dt.date.unique(), reverse=True)

# Default to electricity area EL on a new session
if st.session_state.get("selected_area_type") not in area_types:
    st.session_state["selected_area_type"] = ("EL" if "EL" in area_types else area_types[0])

# Default to the latest available observation
if st.session_state.get("reference_week") not in observation_dates:
    st.session_state["reference_week"] = observation_dates[0]

# Keep the region selector visible across all pages
with st.sidebar:
    st.subheader("Selected region")

    selected_area_type = st.selectbox("Area type", area_types, key="selected_area_type",
                                      help="EL: Norwegian electricity bidding zones (NO1–NO5).\n\n"
                                           "VASS: Groups of NVE hydrological regions.\n\n"
                                           "NO: Norway as a whole.")

    # Area numbers depend on the selected area type
    area_numbers = sorted(df.loc[df["area_type"] == selected_area_type, "area_number"].dropna().unique())

    # Use EL1 by default, or the first valid area
    if st.session_state.get("selected_area_number") not in area_numbers:
        st.session_state["selected_area_number"] = (1 if selected_area_type == "EL" and 1 in area_numbers else area_numbers[0])

    selected_area_number = st.selectbox("Area number", area_numbers, key="selected_area_number")

    st.caption(f"Current selection: {selected_area_type}{selected_area_number}")


# Run the selected page
page.run()