from datetime import timedelta

import pandas as pd
import streamlit as st

from modules.analysis import WEEKLY_WEATHER_PROPERTIES, RESERVOIR_CORRELATION_PROPERTIES, sliding_window_correlation
from modules.magasinstatistikk_data import load_magasinstatistikk_data
from modules.weather import load_weekly_weather


st.title("Weather-Reservoir Correlation")
st.write("Explore how the relationship between weather and reservoir filling changes over time.")

# Use the region selected in the global sidebar
selected_area_type = st.session_state["selected_area_type"]
selected_area_number = st.session_state["selected_area_number"]
region = f"{selected_area_type}{selected_area_number}"

st.caption(f"Selected region: **{region}** · Change in the sidebar")

df = load_magasinstatistikk_data()

reservoir = df.loc[(df["area_type"] == selected_area_type) & (df["area_number"] == selected_area_number),
                   ["date_id", "reservoir_fill_ratio", "reservoir_fill_ratio_change"]].dropna(subset=["date_id"]).set_index("date_id").sort_index()

if reservoir.empty:
    st.info("No reservoir observations are available for this region.")
    st.stop()

if not reservoir.index.is_unique:
    st.warning("The reservoir data contain duplicate dates.")
    st.stop()

# Allow enough time for ERA5 publication and precipitation aggregation
latest_weather_date = pd.Timestamp.now(tz="Europe/Oslo").date() - timedelta(days=7)

weeks = pd.date_range(start=max(reservoir.index.min(), pd.Timestamp("1995-01-01")),
                      end=min(reservoir.index.max(), pd.Timestamp(latest_weather_date)), freq="W-SUN")

if len(weeks) < 4:
    st.info("Not enough weekly observations are available.")
    st.stop()

min_date = weeks[0].date()
max_date = weeks[-1].date()

# Default to the latest 52 available weeks
default_start = max(min_date, max_date - timedelta(weeks=51))

saved_range = st.session_state.get("correlation_period")

if (not isinstance(saved_range, (tuple, list)) or len(saved_range) != 2 or not (min_date <= saved_range[0] <= saved_range[1] <= max_date)):
    st.session_state["correlation_period"] = (default_start, max_date)

first_week, last_week = st.slider("Analysis period", min_value=min_date, max_value=max_date, step=timedelta(weeks=1),
                                  format="DD MMM YYYY", key="correlation_period", persist_state="session")
n_points = st.number_input("Number of sampled locations", min_value=25, max_value=200, value=100, step=25,
                           key="correlation_n_points", persist_state="session")
selected_weeks = pd.date_range(first_week, last_week, freq="W-SUN")

st.caption(f"{len(selected_weeks)} selected weeks · Weekly mean temperature and accumulated precipitation.")

if len(selected_weeks) > 52 or n_points > 100:
    st.warning("Large weather requests may take longer or reach Open-Meteo's API limits.")

if len(selected_weeks) < 4:
    st.info("Select at least four weeks for the correlation analysis.")
    st.stop()

requested_data = (region, first_week, last_week, n_points)

# Download only when requested
if st.button("Load weather data", key="load_correlation_weather"):
    try:
        with st.spinner("Loading weekly weather data..."):
            weather = load_weekly_weather(region, first_week, last_week, n_points=n_points)
        st.session_state["correlation_weather_data"] = weather
        st.session_state["correlation_loaded_for"] = requested_data

    except Exception as exc:
        st.error(f"Could not load weather data: {exc}")
        st.stop()

# Do not display results for a previous region or period
if st.session_state.get("correlation_loaded_for") != requested_data:
    st.info("Click 'Load weather data' to load the selected period and region.")
    st.stop()

weather = st.session_state["correlation_weather_data"]

# Align both datasets by Sunday date labels
weekly_data = reservoir.reindex(selected_weeks).join(weather)
weekly_data.index.name = "date_id"

complete_weather = weather.notna().all(axis=1).sum()
message = f"Weather data available for {complete_weather} of {len(selected_weeks)} selected weeks."

if complete_weather == len(selected_weeks):
    st.success(message)
else:
    st.warning(message)

with st.expander("Weekly data"):
    st.dataframe(weekly_data, width="stretch", height=300)

st.subheader("Sliding window correlation")

c1, c2 = st.columns(2)

with c1:
    weather_property = st.selectbox("Weather property", options=list(WEEKLY_WEATHER_PROPERTIES), format_func=lambda name: WEEKLY_WEATHER_PROPERTIES[name][0],
                                    key="correlation_weather_property", persist_state="session")
with c2:
    reservoir_property = st.selectbox("Reservoir property", options=list(RESERVOIR_CORRELATION_PROPERTIES), format_func=lambda name: RESERVOIR_CORRELATION_PROPERTIES[name][0],
                                      key="correlation_reservoir_property", persist_state="session")

c1, c2 = st.columns(2)

with c1:
    lag = st.number_input("Weather lag (weeks)", min_value=0, max_value=52, value=0, step=1, key="correlation_lag",
                      persist_state="session", help="A positive lag compares earlier weather with later reservoir observations.")
with c2:
    window = st.number_input("Window length (weeks)", min_value=4, max_value=52, value=13, step=1, key="correlation_window",
                             persist_state="session", help="Number of consecutive weeks used to calculate each correlation coefficient.")

try:
    fig, results = sliding_window_correlation(weekly_data, weather_property=weather_property, reservoir_property=reservoir_property, window=window, lag=lag)
    st.plotly_chart(fig, width="stretch")
    st.caption("Correlation is calculated using centred windows. Missing or incomplete windows are excluded. Correlation does not imply causation.")
    with st.expander("Correlation results"):
        reservoir_label, reservoir_unit = RESERVOIR_CORRELATION_PROPERTIES[reservoir_property]
        weather_label, weather_unit = WEEKLY_WEATHER_PROPERTIES[weather_property]

        display_results = results.copy()
        display_results["reservoir"] *= 100
        display_results = display_results.rename(columns={"reservoir": f"{reservoir_label} ({reservoir_unit})",
                                                          "lagged_weather": f"{weather_label} ({weather_unit}), lag {lag} weeks",
                                                          "correlation": "Pearson correlation"})
        st.dataframe(display_results.round(3), width="stretch", height=300)

except ValueError as exc:
    st.warning(f"Correlation analysis could not run: {exc}")

with st.expander("Data sources"):
    st.markdown("- [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/)\n- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)")
    