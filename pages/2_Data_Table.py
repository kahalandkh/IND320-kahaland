import pandas as pd
import streamlit as st

from modules.data import load_data


df = load_data()

st.title("Data Table")

st.write("")

st.write("Select an area type and number to display the first month of observations for that area:")

# Select an area type from the values available in the dataset
area_types = sorted(df["area_type"].unique())

# Restore the previous area type only if it still exists in the current options
if "table_area_type" not in st.session_state or st.session_state.table_area_type not in area_types:
    st.session_state.table_area_type = area_types[0]

col1, col2 = st.columns([2, 1])

with col1:
    selected_area_type = st.selectbox("Area type", area_types, index=area_types.index(st.session_state.table_area_type))

# Store the current selection so it is preserved when moving between pages
st.session_state.table_area_type = selected_area_type

# Only show area numbers that belong to the selected area type
area_numbers = sorted(df.loc[df["area_type"] == selected_area_type, "area_number"].unique())

# Restore the previous area number if it is still valid for the selected area type
if "table_area_number" not in st.session_state or st.session_state.table_area_number not in area_numbers:
    st.session_state.table_area_number = area_numbers[0]

with col2:
    selected_area_number = st.selectbox("Area number", area_numbers, index=area_numbers.index(st.session_state.table_area_number))

st.session_state.table_area_number = selected_area_number

# Filter the data to the selected area series and sort it chronologically
selected_data = (df[(df["area_type"] == selected_area_type) & (df["area_number"] == selected_area_number)].sort_values("date_id"))

# Identify the first month available for the selected area
first_month = selected_data["date_id"].dt.to_period("M").min()

# Keep only observations from the first month
first_month_data = selected_data[selected_data["date_id"].dt.to_period("M") == first_month]

st.write("")

# Show which month is being displayed
st.caption(f"First month available for {selected_area_type} {selected_area_number}: {first_month.to_timestamp().strftime('%B %Y')}")

# Create one row for each column in the imported dataset
table_rows = []

# Only reservoir measurements are displayed as line charts
trend_columns = ["reservoir_fill_ratio",
                 "reservoir_capacity_twh",
                 "stored_energy_twh",
                 "previous_week_reservoir_fill_ratio",
                 "reservoir_fill_ratio_change"]

for column in df.columns:
    values = first_month_data[column]

    # Display all first-month values in chronological order
    if column == "date_id":
        displayed_values = ", ".join(values.dt.strftime("%d %b %Y").tolist())
    elif column == "next_publication_date":
        displayed_values = ", ".join(value.split("T")[0] for value in values.astype(str))
    elif pd.api.types.is_numeric_dtype(values):
        displayed_values = ", ".join(f"{value:.4g}" for value in values)
    else:
        displayed_values = ", ".join(values.astype(str).tolist())

    # Add a line chart only for reservoir measurement variables
    if column in trend_columns:
        chart_values = values.tolist()
    else:
        chart_values = []

    table_rows.append({"Variable": column,
                       "First-month values": displayed_values,
                       "First-month trend": chart_values})

table_df = pd.DataFrame(table_rows)

st.dataframe(table_df,
             column_config={"Variable": st.column_config.TextColumn("Variable", width="medium"),
                            "First-month values": st.column_config.TextColumn("First-month values", width="large"),
                            "First-month trend": st.column_config.LineChartColumn("First-month trend", width="large", color="auto")
                            },
             hide_index=True,
             width="stretch",
             height="content",
             row_height=50)