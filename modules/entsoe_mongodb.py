import certifi
import pandas as pd
import streamlit as st
from pymongo import MongoClient


# Reuse the MongoDB connection between Streamlit reruns
@st.cache_resource
def get_cross_border_collection():
    """Connect to MongoDB and return the ENTSO-E cross-border data."""
    client = MongoClient(st.secrets["MONGODB_URI"], tlsCAFile=certifi.where(), serverSelectionTimeoutMS=10000)
    return client["ind320_project"]["cross_border_flows"]


@st.cache_data
def load_weekly_cross_border(norway_area="BZN|NO3", first_sunday="2024-01-07", last_sunday="2025-12-28"):
    """Return weekly international electricity imports, exports and net imports for a Norwegian bidding zone."""
    collection = get_cross_border_collection()

    pipeline = [{"$match": {"norway_area": norway_area, "direction": {"$in": ["in", "out"]}}}, # Select all international connections for the Norwegian area
                # Group UTC observations into Norwegian Monday-Sunday weeks
                {"$group": {"_id": {"week_start": {"$dateTrunc": {"date": "$timestamp",
                                                                  "unit": "week",
                                                                  "startOfWeek": "monday",
                                                                  "timezone": "Europe/Oslo"}}},
                            "imports_mwh": {"$sum": {"$cond": [{"$eq": ["$direction", "in"]}, "$energy_mwh", 0]}},
                            "exports_mwh": {"$sum": {"$cond": [{"$eq": ["$direction", "out"]}, "$energy_mwh", 0]}}}},
                # Label each Norwegian week by Sunday
                {"$project": {"_id": 0,
                              "date_id": {"$dateToString": {"format": "%Y-%m-%d",
                                                            "date": {"$dateAdd": {"startDate": "$_id.week_start",
                                                                                  "unit": "day",
                                                                                  "amount": 6,
                                                                                  "timezone": "Europe/Oslo"}},
                                                            "timezone": "Europe/Oslo"}},
                              "imports_mwh": 1,
                              "exports_mwh": 1}},
                {"$sort": {"date_id": 1}}]

    # Aggregate in MongoDB
    records = list(collection.aggregate(pipeline))

    if not records:
        raise ValueError(f"No electricity observations found for {norway_area}.")

    weekly = pd.DataFrame(records)
    weekly["date_id"] = pd.to_datetime(weekly["date_id"])

    weekly = weekly.set_index("date_id").sort_index()
    weekly = weekly.loc[first_sunday:last_sunday]

    if weekly.empty:
        raise ValueError("No electricity observations in the selected date range.")

    weekly["net_imports_mwh"] = weekly["imports_mwh"] - weekly["exports_mwh"]
    weekly.index.name = "date_id"

    return weekly
