import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from plotly.subplots import make_subplots
from modules.magasinstatistikk_data import load_magasinstatistikk_data


df = load_magasinstatistikk_data()

st.title("Reservoir Plots")
st.write("Explore reservoir measurements over time and optionally compare regions.")

# Use the primary region selected in the global sidebar
selected_area_type = st.session_state["selected_area_type"]
selected_area_number = st.session_state["selected_area_number"]
primary_area = f"{selected_area_type}{selected_area_number}"

st.caption(f"Selected region: **{primary_area}** · Change in the sidebar")

# Offer only other regions of the same type for comparison
area_numbers = sorted(df.loc[df["area_type"] == selected_area_type, "area_number"].dropna().unique())
area_labels = [f"{selected_area_type}{number}" for number in area_numbers]
comparison_options = [area for area in area_labels if area != primary_area]

# Clear checkboxes that no longer represent valid comparisons.
# This also prevents an area from comparing with itself if it becomes primary.
for key in list(st.session_state):
    if key.startswith("plot_compare_checkbox_"):
        area = key.removeprefix("plot_compare_checkbox_")
        if area not in comparison_options:
            st.session_state[key] = False

comparison_areas = []
if comparison_options:
    st.write("**Compare with (optional)**")

    # Keep the comparison checkboxes together on the left
    columns = st.columns([1] * len(comparison_options) + [6], gap="xxsmall")
    for column, area in zip(columns, comparison_options):
        with column:
            if st.checkbox(area, key=f"plot_compare_checkbox_{area}", persist_state="session",):
                comparison_areas.append(area)
else:
    # NO0 has no other nationwide areas of the same type.
    st.caption("No other areas of this type are available for comparison.")

# The primary region is always plotted
selected_areas = [primary_area] + comparison_areas

# Only numerical reservoir measurements are meaningful to plot
measurements = {"All columns": None,
                "Reservoir fill ratio": "reservoir_fill_ratio",
                "Previous week's fill ratio": "previous_week_reservoir_fill_ratio",
                "Weekly fill ratio change": "reservoir_fill_ratio_change",
                "Stored energy (TWh)": "stored_energy_twh",
                "Reservoir capacity (TWh)": "reservoir_capacity_twh",}

# Remember the measurement when navigating between pages
if st.session_state.get("plot_measurement") not in measurements:
    st.session_state["plot_measurement"] = "All columns"

selected_measurement = st.selectbox("Measurement", list(measurements), key="plot_measurement", persist_state="session")
selected_column = measurements[selected_measurement]

# Use the primary region's observations to define the available months
primary_data = df.loc[(df["area_type"] == selected_area_type) & (df["area_number"] == selected_area_number)]
months = sorted(primary_data["date_id"].dropna().dt.to_period("M").unique())

if not months:
    st.info("No weekly observations are available for the selected region.")
    st.stop()

min_date = months[0].start_time.date()
max_date = months[-1].end_time.date()

# Default to the two most recent months with observations
default_range = (months[max(0, len(months) - 2)].start_time.date(), max_date)

# Keep the saved range as long as it is valid for the primary region
saved_range = st.session_state.get("plot_date_range")
if (not isinstance(saved_range, (tuple, list)) or len(saved_range) != 2 or not (min_date <= saved_range[0] <= saved_range[1] <= max_date)):
    st.session_state["plot_date_range"] = default_range

# Display month/year labels while the slider still moves by day
selected_dates = st.slider("Month range", min_value=min_date, max_value=max_date, format="MMM YYYY", key="plot_date_range", persist_state="session")

start_month = pd.Period(selected_dates[0], freq="M")
end_month = pd.Period(selected_dates[1], freq="M")

# Filter to the selected regions and include complete calendar months
selected_data = df.loc[df["area_type"] == selected_area_type].copy()
selected_data["area"] = (selected_data["area_type"] + selected_data["area_number"].astype(str))
period_data = selected_data.loc[selected_data["area"].isin(selected_areas) & selected_data["date_id"].dt.to_period("M").between(start_month, end_month)].sort_values(["area", "date_id"])

st.caption(f"Plotting {', '.join(selected_areas)} ({start_month.strftime('%b %Y')} – {end_month.strftime('%b %Y')})")

# Keep colours consistent when comparison regions are added or removed
area_colors = {area: px.colors.qualitative.Plotly[i % len(px.colors.qualitative.Plotly)] for i, area in enumerate(area_labels)}

if period_data.empty:
    st.info("No weekly observations are available for the selected months.")
else:
    missing_areas = [area for area in selected_areas if area not in period_data["area"].unique()]
    if missing_areas:
        st.caption(f"No observations in this period for: {', '.join(missing_areas)}")

    if selected_column is not None:
        # Single measurement: compare all selected regions on one axis
        plot_data = period_data.dropna(subset=[selected_column]).copy()

        if plot_data.empty:
            st.info("No measurements are available for the selected months.")
        else:
            y_column = selected_column
            y_title = selected_measurement

            if selected_column == "reservoir_fill_ratio_change":
                # Display changes as percentage points instead of fractions
                plot_data["change_pp"] = plot_data[selected_column] * 100
                y_column = "change_pp"
                y_title = "Weekly change (percentage points)"

            fig = px.line(plot_data, x="date_id", y=y_column, color="area", markers=plot_data["date_id"].nunique() <= 52,
                          color_discrete_map=area_colors, category_orders={"area": selected_areas}, title=f"{selected_measurement} by area")

            fig.update_layout(xaxis_title="Date", yaxis_title=y_title, legend_title_text="Area", hovermode="x unified")
            fig.update_xaxes(hoverformat="%d %b %Y")

            if selected_column in ["reservoir_fill_ratio", "previous_week_reservoir_fill_ratio"]:
                fig.update_yaxes(tickformat=".0%")
                fig.update_traces(hovertemplate="%{y:.1%}<extra>%{fullData.name}</extra>")
            elif selected_column == "reservoir_fill_ratio_change":
                fig.add_hline(y=0, line_dash="dash")
                fig.update_traces(hovertemplate="%{y:+.2f} pp<extra>%{fullData.name}</extra>")
            else:
                fig.update_traces(hovertemplate="%{y:.2f} TWh<extra>%{fullData.name}</extra>")

            st.plotly_chart(fig, width="stretch")

    else:
        # All columns: show reservoir measurements on ratio and energy axes
        ratio_columns = ["reservoir_fill_ratio", "previous_week_reservoir_fill_ratio", "reservoir_fill_ratio_change"]
        twh_columns = ["reservoir_capacity_twh", "stored_energy_twh"]
        plot_columns = ratio_columns + twh_columns

        if period_data[plot_columns].notna().sum().sum() == 0:
            st.info("No reservoir measurements are available for the selected months.")
        else:
            st.caption("Colours represent regions; line styles and markers distinguish measurements. Ratio and energy values use separate y-axes.")
            if len(selected_areas) > 2:
                st.info("The combined plot can be difficult to read for several regions. Choose an individual measurement for a clearer comparison.")

            variable_labels = {"reservoir_fill_ratio": "Fill ratio", "previous_week_reservoir_fill_ratio": "Previous week's fill ratio", "reservoir_fill_ratio_change": "Weekly fill ratio change", "reservoir_capacity_twh": "Capacity", "stored_energy_twh": "Stored energy"}
            line_styles = {"reservoir_fill_ratio": "solid", "previous_week_reservoir_fill_ratio": "dash", "reservoir_fill_ratio_change": "dot", "reservoir_capacity_twh": "dashdot", "stored_energy_twh": "solid",}

            fig = make_subplots(specs=[[{"secondary_y": True}]])

            show_markers = period_data["date_id"].nunique() <= 52

            for area in selected_areas:
                area_data = period_data.loc[period_data["area"] == area]

                for column in ratio_columns:
                    if not area_data[column].notna().any():
                        continue

                    scatter_options = {"x": area_data["date_id"], "y": area_data[column], "mode": "lines", "name": f"{area} - {variable_labels[column]}", "line": dict(color=area_colors[area], dash=line_styles[column], width=2)}
                    if column == "reservoir_fill_ratio_change":
                        # Keep fractions on the axis, but show changes in percentage points
                        scatter_options["customdata"] = area_data[column] * 100
                        scatter_options["hovertemplate"] = ("%{customdata:+.2f} pp<extra>%{fullData.name}</extra>")
                    else:
                        scatter_options["hovertemplate"] = ("%{y:.1%}<extra>%{fullData.name}</extra>")

                    fig.add_trace(go.Scatter(**scatter_options), secondary_y=False)

                for column in twh_columns:
                    if not area_data[column].notna().any():
                        continue

                    fig.add_trace(go.Scatter(x=area_data["date_id"], y=area_data[column], mode="lines+markers" if column == "stored_energy_twh" and show_markers else "lines", 
                                             name=f"{area} - {variable_labels[column]}", line=dict(color=area_colors[area], dash=line_styles[column], width=2), marker=dict(symbol="star", size=6),
                                             hovertemplate="%{y:.2f} TWh<extra>%{fullData.name}</extra>"), secondary_y=True)

            fig.add_hline(y=0, line_dash="dash")
            fig.update_layout(title="Reservoir measurements by area", xaxis_title="Date", legend_title_text="Region and measurement", hovermode="x unified")
            fig.update_xaxes(hoverformat="%d %b %Y")
            fig.update_yaxes(title_text="Fill ratio / weekly change", tickformat=".0%", secondary_y=False)
            fig.update_yaxes(title_text="Energy (TWh)", secondary_y=True)

            st.plotly_chart(fig, width="stretch")


with st.expander("Data source"):
    st.markdown("The data shown on this page come from [**NVE Magasinstatistikk**](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/).")
