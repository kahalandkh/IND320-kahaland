import streamlit as st

from modules.magasinstatistikk_data import load_magasinstatistikk_data


# Configure the application layout and browser tab
st.set_page_config(page_title="IND320 Energy Project", layout="wide")


def main():
    """Render the home page."""
    st.title("IND320 Energy Project")

    st.write("This application was developed as part of the IND320 project work and provides an interactive view of reservoir, weather and cross-border electricity data.")


# Register the application pages and define their sidebar labels
pages = [st.Page(main, title="Home", icon="🏠", default=True),
         st.Page("pages/2_Reservoir_Data.py", title="Reservoir Data", icon="📋"),
         st.Page("pages/3_Reservoir_Plots.py", title="Reservoir Plots", icon="📈"),
         st.Page("pages/5_Cross_Border_Transfers.py", title="Cross-border Transfers", icon="⚡")]

page = st.navigation(pages)


# Get the available reservoir regions
df = load_magasinstatistikk_data()
area_types = sorted(df["area_type"].dropna().unique())

# Default to electricity area EL on a new session
if st.session_state.get("selected_area_type") not in area_types:
    st.session_state["selected_area_type"] = ("EL" if "EL" in area_types else area_types[0])

# Keep the region selector visible across all pages
with st.sidebar:
    st.divider()
    st.subheader("Selected region")

    selected_area_type = st.selectbox("Area type", area_types, key="selected_area_type")

    # Area numbers depend on the selected area type
    area_numbers = sorted(df.loc[df["area_type"] == selected_area_type, "area_number"].dropna().unique())

    # Use EL1 by default, or the first valid area
    if st.session_state.get("selected_area_number") not in area_numbers:
        st.session_state["selected_area_number"] = (1 if selected_area_type == "EL" and 1 in area_numbers else area_numbers[0])

    selected_area_number = st.selectbox("Area number", area_numbers, key="selected_area_number")

    st.caption(f"Current selection: {selected_area_type}{selected_area_number}")

# Run the selected page
page.run()
