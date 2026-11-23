
def combine_weekly_data(reservoir, sources=None):
    """Join selected weekly data to the reservoir history."""
    return reservoir.join(list((sources or {}).values()), how="left")
