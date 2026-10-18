import streamlit as st

def main():
    """Render the home page."""
    st.title("IND320 Energy Project")

    st.write("This application was developed as part of the IND320 project work and provides an interactive view of reservoir and cross-border electricity data.")

# Configure the application layout and browser tab
st.set_page_config(page_title="IND320 Energy Project", layout="wide")

# Register the application pages and define their sidebar labels
pages = [st.Page(main, title="Home", icon="🏠", default=True),
         st.Page("pages/2_Data_Table.py", title="Data Table", icon="📋"),
         st.Page("pages/3_Data_Plot.py", title="Data Plot", icon="📈"),
         st.Page("pages/4_Reservoir_Fill_Ratio.py", title="Reservoir Fill Ratio", icon="💧"),
         st.Page("pages/5_Cross_Border_Transfers.py", title="Cross-border Transfers", icon="⚡")]
page = st.navigation(pages)
page.run()