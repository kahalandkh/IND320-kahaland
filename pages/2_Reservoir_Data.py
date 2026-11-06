import pandas as pd
import streamlit as st

from modules.magasinstatistikk_data import load_magasinstatistikk_data


df = load_magasinstatistikk_data()

st.title("Reservoir Data")

st.write("")

st.write("Select an area and month range to explore weekly reservoir data.")

# Select an area type from the values available in the dataset
area_types = sorted(df["area_type"].unique())

# Keep the selected area when navigating between pages
if st.session_state.get("table_area_type") not in area_types:
    st.session_state["table_area_type"] = area_types[0]

col1, col2 = st.columns([2, 1])

with col1:
    selected_area_type = st.selectbox("Area type", area_types, key="table_area_type", persist_state="session")

# The available area numbers depend on the selected area type
area_numbers = sorted(df.loc[df["area_type"] == selected_area_type, "area_number"].dropna().unique())

# Reset the area number if it isn't available for the selected area type
if st.session_state.get("table_area_number") not in area_numbers:
    st.session_state["table_area_number"] = area_numbers[0]

with col2:
    selected_area_number = st.selectbox("Area number", area_numbers, key="table_area_number", persist_state="session")


# Filter the selected area and sort by date
selected_data = df.loc[(df["area_type"] == selected_area_type) & (df["area_number"] == selected_area_number)].sort_values("date_id")


# Get the available calendar months
months = sorted(selected_data["date_id"].dt.to_period("M").unique())

# Use dates for the slider, covering the complete available months
min_date = months[0].start_time.date()
max_date = months[-1].end_time.date()

# Default to the two most recent months with observations
default_range = (months[max(0, len(months) - 2)].start_time.date(), max_date)

# Keep the previous selection if it is still valid
saved_range = st.session_state.get("table_date_range")

if (not isinstance(saved_range, (tuple, list)) or len(saved_range) != 2 or not (min_date <= saved_range[0] <= saved_range[1] <= max_date)):
    st.session_state["table_date_range"] = default_range

# Show month/year labels, although the slider still moves by day
selected_dates = st.slider("Month range", min_value=min_date, max_value=max_date, format="MMM YYYY", key="table_date_range", persist_state="session")

# Convert the selected dates to calendar months
start_month = pd.Period(selected_dates[0], freq="M")
end_month = pd.Period(selected_dates[1], freq="M")

# Include all weekly observations in the selected months
period_data = selected_data.loc[selected_data["date_id"].dt.to_period("M").between(start_month, end_month)]

st.caption(f"{len(period_data):,} weekly observations for {selected_area_type}{selected_area_number} ({start_month.strftime('%b %Y')} – {end_month.strftime('%b %Y')})")

# Remember which view was selected when returning to this page
view_options = ["Overview", "Weekly observations"]

if st.session_state.get("table_view") not in view_options:
    st.session_state["table_view"] = view_options[0]

view = st.segmented_control("View", view_options, key="table_view", persist_state="session")


if period_data.empty:
    st.info("No weekly observations are available for these dates.")

elif view == "Overview":

    # Only reservoir measurements have meaningful numerical trends
    trend_columns = ["reservoir_fill_ratio",
                     "reservoir_capacity_twh",
                     "stored_energy_twh",
                     "previous_week_reservoir_fill_ratio",
                     "reservoir_fill_ratio_change"]

    def format_value(value, values):
        if pd.isna(value):
            return "—"
        if isinstance(value, pd.Timestamp):
            return value.strftime("%d %b %Y")
        if pd.api.types.is_numeric_dtype(values):
            return f"{value:.4g}"
        return str(value)

    overview_rows = []

    for column in period_data.columns:
        values = period_data[column]

        # Charts need at least two observations
        if column in trend_columns and len(values) >= 2:
            chart_values = pd.to_numeric(values, errors="coerce").tolist()
        else:
            chart_values = []

        overview_rows.append({"Variable": column,
                              "First value": format_value(values.iloc[0], values),
                              "Last value": format_value(values.iloc[-1], values),
                              "Trend": chart_values})

    overview_df = pd.DataFrame(overview_rows)

    st.dataframe(overview_df,
                 column_config={"Variable": st.column_config.TextColumn("Variable", width="medium"),
                                "First value": st.column_config.TextColumn("First value"),
                                "Last value": st.column_config.TextColumn("Last value"),
                                "Trend": st.column_config.LineChartColumn("Trend", width="large")}, hide_index=True, width="stretch", height="content", row_height=50)

    if len(period_data) == 1:
        st.caption("Select at least two weekly observations to see trends.")

# Show the individual records
elif view == "Weekly observations":
    # The selected area is already shown above
    display_data = period_data.drop(columns=["area_type", "area_number"])

    st.dataframe(display_data, column_config={"date_id": st.column_config.DatetimeColumn("Date", format="DD MMM YYYY")}, hide_index=True, width="stretch", height="auto")


with st.expander("Data source"):
    st.markdown("The data shown on this page come from [**NVE Magasinstatistikk**](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/).")
