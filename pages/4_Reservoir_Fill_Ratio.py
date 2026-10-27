import pandas as pd
import plotly.express as px
import streamlit as st

from modules.magasinstatistikk_data import load_magasinstatistikk_data


df = load_magasinstatistikk_data()

st.title("Reservoir Fill Ratio")
st.write("Choose an area type and date range to view reservoir fill ratios over time.")

area_types = ["EL", "NO", "VASS"]

# Restore the previous area type
if "fill_area_type" not in st.session_state or st.session_state.fill_area_type not in area_types:
    st.session_state.fill_area_type = area_types[0]

selected_area_type = st.radio("Area type", area_types, index=area_types.index(st.session_state.fill_area_type), horizontal=True)
st.session_state.fill_area_type = selected_area_type

# Define the available date range
min_date = df["date_id"].min().date()
max_date = df["date_id"].max().date()

# Restore the previous date range
if "fill_date_range" not in st.session_state:
    st.session_state.fill_date_range = (min_date, max_date)

start_date, end_date = st.session_state.fill_date_range

# Reset the stored range if it is outside the current dataset
if start_date < min_date or end_date > max_date:
    st.session_state.fill_date_range = (min_date, max_date)

selected_dates = st.slider("Date range",
                           min_value=min_date,
                           max_value=max_date,
                           value=st.session_state.fill_date_range,
                           format="MMM YYYY")
st.session_state.fill_date_range = selected_dates

start_date, end_date = selected_dates

# Filter to the selected area type and date range
filtered_data = df[(df["area_type"] == selected_area_type) & (df["date_id"] >= pd.Timestamp(start_date)) & (df["date_id"] <= pd.Timestamp(end_date))].copy()

# Create labels for the individual areas
filtered_data["area"] = filtered_data["area_type"] + filtered_data["area_number"].astype(str)
filtered_data = filtered_data.sort_values(["area", "date_id"])

# Plot fill ratios for all areas belonging to the selected type
fig = px.line(filtered_data, x="date_id", y="reservoir_fill_ratio",
              color="area", title=f"Reservoir Fill Ratio – {selected_area_type}")

fig.update_layout(xaxis_title="Date", yaxis_title="Reservoir fill ratio",
                  legend_title_text="Area", hovermode="x unified")

# Format dates and fill ratios for display
fig.update_xaxes(hoverformat="%d %b %Y")
fig.update_yaxes(tickformat=".0%")
fig.update_traces(hovertemplate="%{y:.1%}<extra>%{fullData.name}</extra>")

st.plotly_chart(fig, width="stretch")

# Show the fill-ratio trend for each area in the selected area type
trend_data = (filtered_data.groupby("area")["reservoir_fill_ratio"].apply(list).reset_index(name="Fill ratio trend"))

st.dataframe(trend_data, 
             column_config={"area": st.column_config.TextColumn("Area"),
                            "Fill ratio trend": st.column_config.LineChartColumn(
                                "Fill ratio trend", width="large", y_min=0, y_max=1, color="primary")},
             hide_index=True,
             width="stretch")

st.write("")

with st.expander("Data source"):
    st.markdown(
        """The data shown on this page come from [**NVE Magasinstatistikk**](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/).""")