import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from plotly.subplots import make_subplots
from modules.data import load_data


df = load_data()

st.title("Data Plot")

st.write("Select one or more areas, a column, and a month range to explore and compare the reservoir data over time.")

st.write("")

# Keep the original dataset columns for the column selector
data_columns = df.columns.tolist()

# Create the valid area combinations available in the dataset
area_options = df[["area_type", "area_number"]].drop_duplicates().sort_values(["area_type", "area_number"])
area_labels = [f"{row.area_type} {row.area_number}" for row in area_options.itertuples(index=False)]

# Restore the previous area selections only if they still exist in the current area options
if ("plot_areas" not in st.session_state or any(area not in area_labels for area in st.session_state.plot_areas)):
    st.session_state.plot_areas = [area_labels[0]]

selected_areas = st.multiselect("Areas", area_labels, default=st.session_state.plot_areas)

# Store the current selection so it is preserved when moving between pages
st.session_state.plot_areas = selected_areas

if not selected_areas:
    st.warning("Select at least one area.")
    # Stop execution of the rest of the page for this rerun
    st.stop()

# Add an area label used for filtering and plotting
selected_data = df.copy()
selected_data["area"] = selected_data["area_type"] + " " + selected_data["area_number"].astype(str)
selected_data = selected_data[selected_data["area"].isin(selected_areas)].sort_values(["area", "date_id"])

# Allow any individual dataset column or all columns to be selected
column_options = ["All columns"] + data_columns

# Restore the previous column only if it still exists in the current column options
if "plot_column" not in st.session_state or st.session_state.plot_column not in column_options:
    st.session_state.plot_column = "All columns"

selected_column = st.selectbox("Column", column_options, index=column_options.index(st.session_state.plot_column))
st.session_state.plot_column = selected_column

# Create the available months for the selected area series
months = sorted(selected_data["date_id"].dt.to_period("M").unique())
# Create human-readable labels for the month slider
month_labels = [month.strftime("%b %Y") for month in months]

# Restore the previous month range only if both months are available for the selected areas
if ("plot_months" not in st.session_state or st.session_state.plot_months[0] not in month_labels or st.session_state.plot_months[1] not in month_labels):
    st.session_state.plot_months = (month_labels[0], month_labels[0])

selected_months = st.select_slider("Month range", options=month_labels, value=st.session_state.plot_months)
st.session_state.plot_months = selected_months

# Convert the selected month labels back to month periods
start_month = months[month_labels.index(selected_months[0])]
end_month = months[month_labels.index(selected_months[1])]

# Keep only observations within the selected month range
filtered_data = selected_data[(selected_data["date_id"].dt.to_period("M") >= start_month) & (selected_data["date_id"].dt.to_period("M") <= end_month)]

# Use the same colour for an area throughout the plot
area_colors = {area: px.colors.qualitative.Plotly[i % len(px.colors.qualitative.Plotly)] for i, area in enumerate(area_labels)}

# Plot either the selected column or the combined reservoir variables
if selected_column != "All columns":
    fig = px.line(filtered_data, x="date_id", y=selected_column, color="area", markers=True, color_discrete_map=area_colors, title=f"{selected_column} by area")

    fig.update_layout(xaxis_title="Date", yaxis_title=selected_column, legend_title_text="Area", hovermode="x unified")

    st.plotly_chart(fig, width="stretch")

else:
    st.caption("Colours represent areas, while line styles and markers distinguish reservoir variables. Descriptive fields are excluded from the combined plot.")

    if len(selected_areas) > 3:
        st.info("Displaying all reservoir variables for several areas may make the plot difficult to read.")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # The combined view includes only quantitative reservoir variables
    ratio_columns = ["reservoir_fill_ratio", "previous_week_reservoir_fill_ratio", "reservoir_fill_ratio_change"]
    twh_columns = ["reservoir_capacity_twh", "stored_energy_twh"]

    # Shorter labels are used to keep the legend readable
    variable_labels = {"reservoir_fill_ratio": "Fill ratio",
                       "previous_week_reservoir_fill_ratio": "Previous week's fill ratio",
                       "reservoir_fill_ratio_change": "Fill ratio change",
                       "reservoir_capacity_twh": "Capacity (TWh)",
                       "stored_energy_twh": "Stored energy (TWh)"}

    # Use line styles and markers to distinguish reservoir variables
    line_styles = {"reservoir_fill_ratio": "solid",
                   "previous_week_reservoir_fill_ratio": "dash",
                   "reservoir_fill_ratio_change": "dot",
                   "reservoir_capacity_twh": "dashdot",
                   "stored_energy_twh": "solid"}

    # Plot each selected area using its own colour
    for area in selected_areas:
        area_data = filtered_data[filtered_data["area"] == area]

        for column in ratio_columns:
            fig.add_trace(go.Scatter(x=area_data["date_id"],
                                     y=area_data[column],
                                     mode="lines",
                                     name=f"{area} - {variable_labels[column]}",
                                     line=dict(color=area_colors[area], dash=line_styles[column], width=2)),
                          secondary_y=False)

        for column in twh_columns:
            if column == "stored_energy_twh":
                fig.add_trace(go.Scatter(x=area_data["date_id"],
                                         y=area_data[column],
                                         mode="lines+markers",
                                         name=f"{area} - {variable_labels[column]}",
                                         line=dict(color=area_colors[area], dash=line_styles[column], width=2),
                                         marker=dict(symbol="star", size=6)),
                              secondary_y=True)
            else:
                fig.add_trace(go.Scatter(x=area_data["date_id"],
                                         y=area_data[column],
                                         mode="lines",
                                         name=f"{area} - {variable_labels[column]}",
                                         line=dict(color=area_colors[area], dash=line_styles[column], width=2)),
                              secondary_y=True)

    # Add a reference line
    fig.add_hline(y=0, line_dash="dash")

    fig.update_layout(title="Reservoir variables by area",
                      xaxis_title="Date",
                      legend_title_text="Area and variable",
                      hovermode="x unified")

    fig.update_yaxes(title_text="Fill ratio / change in fill ratio", secondary_y=False)
    fig.update_yaxes(title_text="Energy (TWh)", secondary_y=True)

    st.plotly_chart(fig, width="stretch")