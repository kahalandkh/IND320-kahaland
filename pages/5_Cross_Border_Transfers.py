import pandas as pd
import plotly.express as px
import streamlit as st

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from modules.mongodb import get_cross_border_collection


collection = get_cross_border_collection()
oslo_tz = ZoneInfo("Europe/Oslo")

st.title("Cross-border Transfers")
st.write("Choose a connection and year to explore cross-border electricity transfers, and select months for the flow plot.")

st.write("")


@st.cache_data
def get_connections():
    """Return the cross-border connections available in MongoDB."""
    pipeline = [{"$group": {"_id": {"norway_area": "$norway_area", "foreign_area": "$foreign_area"}}},
                {"$sort": {"_id.norway_area": 1, "_id.foreign_area": 1}}]
    return list(collection.aggregate(pipeline))


def get_utc_bounds(year, month=None):
    """Return UTC bounds for a Norwegian calendar year or month."""
    if month is None:
        start = datetime(year, 1, 1, tzinfo=oslo_tz)
        end = datetime(year + 1, 1, 1, tzinfo=oslo_tz)
    else:
        start = datetime(year, month, 1, tzinfo=oslo_tz)
        end = (datetime(year + 1, 1, 1, tzinfo=oslo_tz) if month == 12 else datetime(year, month + 1, 1, tzinfo=oslo_tz))

    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


@st.cache_data
def get_yearly_transfer(norway_area, foreign_area, year):
    """Return total transferred energy by direction for one year."""
    start_utc, end_utc = get_utc_bounds(year)

    # Sum in MongoDB so only the two direction totals are returned
    pipeline = [{"$match": {"norway_area": norway_area,
                            "foreign_area": foreign_area,
                            "timestamp": {"$gte": start_utc, "$lt": end_utc}}},
                {"$group": {"_id": "$direction", "energy_mwh": {"$sum": "$energy_mwh"}}},
                {"$sort": {"_id": 1}}]

    return pd.DataFrame(list(collection.aggregate(pipeline)))


@st.cache_data
def get_monthly_flow(norway_area, foreign_area, year, month):
    """Return physical flow data for one month."""
    start_utc, end_utc = get_utc_bounds(year, month)

    query = {"norway_area": norway_area,
             "foreign_area": foreign_area,
             "timestamp": {"$gte": start_utc, "$lt": end_utc}}
    projection = {"_id": 0, "timestamp": 1, "direction": 1, "flow_mw": 1}

    data = pd.DataFrame(list(collection.find(query, projection).sort("timestamp", 1)))

    if not data.empty:
        # Show the stored UTC timestamps in Norwegian local time
        data["timestamp"] = (pd.to_datetime(data["timestamp"], utc=True).dt.tz_convert(oslo_tz))
        
    return data


# Create the connection labels shown in the radio buttons
connections = get_connections()
connection_options = {f'{item["_id"]["norway_area"].replace("BZN|", "")} - {item["_id"]["foreign_area"].replace("BZN|", "")}':
    (item["_id"]["norway_area"], item["_id"]["foreign_area"]) for item in connections}
connection_labels = list(connection_options.keys())

# Restore the previous connection
if "cross_border_connection" not in st.session_state or st.session_state.cross_border_connection not in connection_labels:
    st.session_state.cross_border_connection = None

connection_index = (connection_labels.index(st.session_state.cross_border_connection) if st.session_state.cross_border_connection is not None else None)

# The connection controls both plots, so keep it above the two columns
selected_connection = st.radio("Choose a connection:", connection_labels, index=connection_index, horizontal=True)
                               
st.session_state.cross_border_connection = selected_connection

if selected_connection is not None:
    norway_area, foreign_area = connection_options[selected_connection]
else:
    norway_area = foreign_area = None

years = [2024, 2025]

# Restore the previous year
if "cross_border_year" not in st.session_state or st.session_state.cross_border_year not in years:
    st.session_state.cross_border_year = None

year_index = (years.index(st.session_state.cross_border_year) if st.session_state.cross_border_year is not None else None)

months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Restore the previous month selections
if ("cross_border_months" not in st.session_state or st.session_state.cross_border_months is None or any(month not in months for month in st.session_state.cross_border_months)):
    st.session_state.cross_border_months = []

# Use the same colours for directions in both plots
direction_colors = {"Into Norway": "#0072B2", "Out of Norway": "#D55E00"}
direction_order = ["Into Norway", "Out of Norway"]

left_col, right_col = st.columns(2)

with left_col:
    st.subheader("Annual transfer")

    selected_year = st.selectbox("Year", years, index=year_index, placeholder="Choose a year", disabled=selected_connection is None)
    st.session_state.cross_border_year = selected_year

    if selected_connection is not None and selected_year is not None:
        yearly_data = get_yearly_transfer(norway_area, foreign_area, selected_year)

        if not yearly_data.empty:
            yearly_data = yearly_data.rename(columns={"_id": "direction"})
            yearly_data["energy_twh"] = yearly_data["energy_mwh"] / 1_000_000
            yearly_data["Direction"] = yearly_data["direction"].map({"in": "Into Norway", "out": "Out of Norway"})

            fig = px.pie(yearly_data, values="energy_twh", names="Direction", color="Direction",
                         color_discrete_map=direction_colors, category_orders={"Direction": direction_order},
                         title=f"{selected_connection}: annual transfer ({selected_year})")

            fig.update_traces(sort=False, texttemplate="%{label}<br>%{value:.2f} TWh<br>%{percent}",
                              textposition="inside", hovertemplate="%{label}<br>%{value:.2f} TWh<extra></extra>")
            fig.update_layout(legend_title_text="Direction")

            st.plotly_chart(fig, width="stretch")
        else:
            st.warning("No data found for the selected connection and year.")


with right_col:
    st.subheader("Monthly flow")

    selected_months = st.pills("Months", months, selection_mode="multi",
                               default=st.session_state.cross_border_months,
                               disabled=selected_connection is None or selected_year is None)
    st.session_state.cross_border_months = selected_months

    if selected_connection is not None and selected_year is not None and selected_months:
        month_numbers = sorted(months.index(month) + 1 for month in selected_months)

        # Each month is cached separately, so adding a month only fetches the new month
        monthly_data = [get_monthly_flow(norway_area, foreign_area, selected_year, month) for month in month_numbers]
        monthly_data = [data for data in monthly_data if not data.empty]

        if monthly_data:
            flow_data = pd.concat(monthly_data, ignore_index=True)
            flow_data["Direction"] = flow_data["direction"].map({"in": "Into Norway", "out": "Out of Norway"})

            # Keep unselected months from being joined by a line
            flow_data["month"] = flow_data["timestamp"].dt.month

            fig = px.line(flow_data, x="timestamp", y="flow_mw", color="Direction", line_group="month",
                          color_discrete_map=direction_colors, category_orders={"Direction": direction_order},
                          render_mode="webgl", title=f"{selected_connection}: physical flow ({selected_year})")

            fig.update_layout(xaxis_title="Time", yaxis_title="Physical flow (MW)",
                              legend_title_text="Direction", hovermode="x unified")
            fig.update_xaxes(hoverformat="%d %b %Y %H:%M")
            fig.update_yaxes(rangemode="tozero")
            fig.update_traces(line=dict(width=1.2), hovertemplate="%{y:.0f} MW<extra>%{fullData.name}</extra>")

            st.plotly_chart(fig, width="stretch")
        else:
            st.warning("No data found for the selected period.")


st.write("")

with st.expander("Data source"):
    st.markdown("""
        Data shown on this page are from the [**ENTSO-E Transparency Platform**](https://transparency.entsoe.eu/) and
        represent physical cross-border electricity flows between Norwegian and
        neighbouring bidding zones. The available data cover 2024 and 2025.""")