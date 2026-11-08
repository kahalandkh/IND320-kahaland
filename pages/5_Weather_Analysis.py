from datetime import date, timedelta

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from modules.analysis import precipitation_spc, temperature_lof
from modules.weather import sample_weather_locations, download_weather, regional_hourly_averages


TIMEZONE = "Europe/Berlin"
FIRST_SELECTABLE_DATE = date(1995, 1, 1)


@st.cache_data
def load_weather_for_selection(region, start_date, end_date, n_points):
    """Download and average ERA5 data for the selected Berlin calendar days."""
    locations = sample_weather_locations(region, n_points=n_points)

    # Request an extra day on each side to handle local-time boundaries
    request_start = start_date - timedelta(days=1)
    request_end = end_date + timedelta(days=1)

    responses = download_weather(region=region, start_date=request_start.isoformat(), 
                                 end_date=request_end.isoformat(), locations=locations, batch_size=100)
    hourly = regional_hourly_averages(responses)

    # Keep Berlin time: it uses the same daylight-saving rules as Norway.
    hourly["date"] = hourly["date"].dt.tz_convert(TIMEZONE)
    selected_days = hourly["date"].dt.date.between(start_date, end_date)
    hourly = hourly.loc[selected_days].reset_index(drop=True)
    
    if hourly.empty:
        raise ValueError("No hourly observations were returned for the selected period.")

    first_hour = pd.Timestamp(start_date, tz=TIMEZONE)
    next_day = pd.Timestamp(end_date + timedelta(days=1), tz=TIMEZONE)
    expected_hours = int((next_day - first_hour) / pd.Timedelta(hours=1))

    # Prevent incomplete or shifted downloads from reaching SPC and LOF.
    if (len(hourly) != expected_hours or hourly["date"].iloc[0] != first_hour or hourly["date"].iloc[-1] != next_day - pd.Timedelta(hours=1)
        or not hourly["date"].is_unique or not hourly["date"].diff().iloc[1:].eq(pd.Timedelta(hours=1)).all()):
        raise ValueError("The downloaded data do not cover all hours in the selected period.")

    return hourly


st.title("Weather Analysis")
st.write("Explore hourly temperature and precipitation data using SPC and LOF.")

# Use the same region as the reservoir pages
selected_area_type = st.session_state["selected_area_type"]
selected_area_number = st.session_state["selected_area_number"]
region = f"{selected_area_type}{selected_area_number}"
st.caption(f"Selected region: **{region}** · Change in the sidebar")

# Remember download settings when navigating between pages
max_date = date.today() - timedelta(days=7)
period = st.date_input("Download period", value=(date(2024, 1, 1), date(2024, 3, 31)), min_value=FIRST_SELECTABLE_DATE, max_value=max_date,
                       format="DD.MM.YYYY", key="weather_period", persist_state="session", help="Choose both the start and end dates.")

n_points = st.number_input("Number of sampled locations", min_value=25, max_value=200, value=100, step=25, key="weather_n_points", persist_state="session",
                           help=("Weather values are averaged across randomly sampled points in the region, not weather stations. More points require more API data. 100 locations is recommended for Streamlit."))
st.caption("Hourly ERA5 data · Times shown in Europe/Berlin (same as Norway)")

valid_period = isinstance(period, (tuple, list)) and len(period) == 2
if valid_period:
    start_date, end_date = period
    requested_data = (region, start_date, end_date, n_points)
else:
    requested_data = None
    st.warning("Please select both a start date and an end date.")

# Warn about large API requests
if valid_period:
    period_days = (end_date - start_date).days + 1

    if period_days > 365 or n_points > 100:
        st.warning("This request may take longer or reach Open-Meteo's API limits. Consider using up to one year and no more than 100 locations.")
        
# Avoid API calls on every widget change
load_clicked = st.button("Load weather data", disabled=not valid_period)
download_failed = False

if load_clicked:
    try:
        with st.spinner("Loading weather data..."):
            hourly_data = load_weather_for_selection(region, start_date, end_date, n_points)

        st.session_state["weather_hourly_data"] = hourly_data
        st.session_state["weather_loaded_for"] = requested_data

    except Exception as exc:
        download_failed = True
        message = str(exc).lower()
        if any(term in message for term in ("429", "rate limit", "too many requests", "limit exceeded", "daily limit", "minutely limit", "monthly limit",)):
            st.error("Open-Meteo's API limit was reached. Try again later, or choose fewer locations or a shorter period.")
        else:
            st.error(f"Could not load weather data: {exc}")

# The session may still contain data for a different region or period
has_data = (requested_data is not None and st.session_state.get("weather_loaded_for") == requested_data and "weather_hourly_data" in st.session_state)

if has_data:
    hourly_data = st.session_state["weather_hourly_data"]
    if download_failed:
        st.caption("Showing previously loaded data for this selection.")
    else:
        st.success(f"Loaded {len(hourly_data):,} hourly observations for {region} ({n_points} locations, {start_date:%d %b %Y} – {end_date:%d %b %Y}).")

    missing = hourly_data[["temperature_2m", "precipitation"]].isna().sum()
    if missing.any():
        st.warning("Some hours have missing weather values. Analyses need complete hourly data.")

    with st.expander("Downloaded data"):
        st.dataframe(hourly_data, hide_index=True, width="stretch", height=300)
        st.caption("Temperature in °C, precipitation in mm, timestamps in Europe/Berlin.")

elif valid_period and not download_failed:
    st.info("Click 'Load weather data' to load the selected period and region.")


# Remember the selected tab when navigating between pages
def save_weather_tab():
    st.session_state["weather_last_tab"] = st.session_state["weather_tabs"]


tab_names = ["Outlier / SPC", "Anomaly / LOF"]

spc_tab, lof_tab = st.tabs(tab_names, default=st.session_state.get("weather_last_tab", "Outlier / SPC"), key="weather_tabs", on_change=save_weather_tab)

with spc_tab:
    st.write("Find unusual precipitation hours using DCT filtering and robust SPC limits.")

    if not has_data:
        st.caption("Load weather data above to run the SPC analysis.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            cutoff_days = st.number_input("DCT cut-off (days)", min_value=1.0, max_value=365.0, value=30.0, step=1.0, key="spc_cutoff_days",
                                          persist_state="session", help="The period separating longer-term variations from shorter-term changes.",)
        with col2:
            n_std = st.number_input("SPC threshold (robust SD)", min_value=0.5, max_value=10.0, value=3.0, step=0.5, key="spc_n_std", persist_state="session",
                                    help="How far a residual must be from the median to be flagged.")

        if len(hourly_data) / 24 <= cutoff_days:
            st.warning("The chosen DCT cut-off is at least as long as the data period. Consider a shorter cut-off or a longer download period.")

        try:
            fig, results, summary = precipitation_spc(hourly_data, cutoff_days=cutoff_days, n_std=n_std)
            st.pyplot(fig, width="stretch")
            plt.close(fig)

            c1, c2, c3 = st.columns(3)
            c1.metric("Flagged hours", f"{summary['outliers']:,}")
            c2.metric("Flagged share", f"{summary['outlier_percent']:.2f}%")
            c3.metric("Upper / lower", f"{summary['upper_outliers']} / {summary['lower_outliers']}")
            st.caption("Flags represent individual hours, not necessarily independent rainfall events.")

            with st.expander("Flagged precipitation hours"):
                flagged = results.loc[results["outlier"], ["date", "precipitation", "lower", "upper", "side"]]
                st.dataframe(flagged, hide_index=True, width="stretch", height=300)

        except ValueError as exc:
            st.warning(f"SPC analysis could not run: {exc}")

with lof_tab:
    st.write("Find unusual temperatures using Local Outlier Factor (LOF).")

    if not has_data:
        st.caption("Load weather data above to run the LOF analysis.")
    else:
        max_neighbors = max(2, len(hourly_data) - 1)
        if not 2 <= st.session_state.get("lof_neighbors", 50) <= max_neighbors:
            st.session_state["lof_neighbors"] = min(50, max_neighbors)

        c1, c2, c3 = st.columns(3)
        with c1:
            n_neighbors = st.number_input("Neighbours", min_value=2, max_value=max_neighbors, value=min(50, max_neighbors), step=1,
                                          key="lof_neighbors", persist_state="session", help="How many nearby points LOF uses to estimate local density.")
        with c2:
            time_scale = st.number_input("Time scale", min_value=0.0, max_value=2.0, value=0.02, step=0.01, format="%.2f",
                                         key="lof_time_scale", persist_state="session", help="Weight of hourly time differences relative to temperature differences.")
        with c3:
            contamination_percent = st.number_input("Expected anomalies (%)", min_value=0.1, max_value=50.0, value=1.0, step=0.5, format="%.1f", key="lof_contamination_pct", persist_state="session",
                                                    help="Approximate fraction of observations LOF should label as anomalies.")

        try:
            fig, results, summary = temperature_lof(hourly_data, contamination=contamination_percent / 100, n_neighbors=n_neighbors, time_scale=time_scale)
            st.pyplot(fig, width="stretch")
            plt.close(fig)

            c1, c2 = st.columns(2)
            c1.metric("Anomalous hours", f"{summary['anomalies']:,}")
            c2.metric("Anomalous share", f"{summary['anomaly_percent']:.2f}%")
            st.caption("The contamination setting controls the approximate share of flagged hours; these are potential anomalies, not confirmed errors.")

            with st.expander("Flagged temperature hours"):
                flagged = results.loc[results["anomaly"], ["date", "temperature_2m", "lof_score"]]
                st.dataframe(flagged, hide_index=True, width="stretch", height=300)

        except ValueError as exc:
            st.warning(f"LOF analysis could not run: {exc}")

with st.expander("Data source"):
    st.markdown("Hourly ERA5 weather data from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api).")
