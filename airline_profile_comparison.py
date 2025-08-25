"""
airline_profile_comparison.py

A Streamlit application that provides profile comparisons of various airlines based on data fetched from the AviationStack API.
"""
import requests
from dotenv import load_dotenv
import streamlit as st
import os
import pandas as pd
from test_json import return_json
import matplotlib.pyplot as plt
from fetchapi import fetch_aviation_API_airlines_endpoint

airline_data = fetch_aviation_API_airlines_endpoint()

def get_airline_feature_dict(feature_type, cast_type):
    """
    Return a dictionary of airline names along with their values for the specified feature type.
    
    Parameters:
    - feature_type (str): The specified feature type to extract (e.g., "fleet_size", "fleet_average_age", "date_founded").
    - cast_type (str): The type to cast the feature value to ("int", "float", or "str")
    
    Returns:
    - dict: A dictionary whose keys are airline names and values are the corresponding feature values.
    """
    airline_feature_dict = {}
    for i in range(len(airline_data["data"])):
        airline_name = airline_data["data"][i]["airline_name"]
        if airline_data["data"][i][feature_type] is not None and airline_data["data"][i][feature_type] != "":
            if cast_type == "int":
                airline_feature_value = int(airline_data["data"][i][feature_type])
            elif cast_type == "str":
                airline_feature_value = str(airline_data["data"][i][feature_type])
            else:
                airline_feature_value = float(airline_data["data"][i][feature_type])
        airline_feature_dict[airline_name] = airline_feature_value
    return airline_feature_dict

def plot_bar_graph(feature_series, title, ylabel, bottom_ylim=0):
    """
    Plot a bar graph for the given feature Series.
    
    Parameters:
    - feature_series (pd.Series): A pandas Series where the index is airline names and the values are the feature values.
    - title (str): The desired title of the graph.
    - ylabel (str): The desired label for the y-axis.
    - bottom_ylim (int, optional): The minimum limit for the y-axis. Defaults to 0.

    Returns:
    - None: Displays the bar graph using Streamlit.
    """
    fig, ax = plt.subplots()
    bars = ax.bar(feature_series.index.astype(str), feature_series.values)
    ax.set_title(title)
    ax.set_xlabel("Airline")
    ax.set_ylabel(ylabel)
    ax.bar(feature_series.index, feature_series.values)
    ax.bar_label(bars, padding=3)
    plt.xticks(rotation=90)
    plt.ylim(bottom=bottom_ylim)
    st.pyplot(fig)

# Main Program Execution
st.title("Airline Profile Comparison")

comparison_option = st.radio(
    "Pick the type of comparison you would like to see: ",
    ("Fleet Size", "Fleet Average Age", "Founding Year")
)

countries_of_origin = pd.Series(get_airline_feature_dict("country_name", "str"))
country_filters = countries_of_origin.unique().tolist()
country_filters.append("All Countries") # Add option for user to see all countries
country_filter_option = st.radio(
    "Pick a country of origin to filter by: ",
    (country_filters)
)

if country_filter_option == "All Countries":
    if comparison_option == "Fleet Size":
        fleet_sizes = (pd.Series(get_airline_feature_dict("fleet_size", "int"))).dropna() # Remove airlines with no fleet size data
        sorted_fleet_sizes = fleet_sizes.sort_values(ascending=True)
        top10_sorted_fleet_sizes = sorted_fleet_sizes.tail(10) # Get the top 10 largest airlines by fleet size
        plot_bar_graph(top10_sorted_fleet_sizes, "Airline Fleet Sizes", "Fleet Size")
    elif comparison_option == "Fleet Average Age":
        fleet_avg_ages = (pd.Series(get_airline_feature_dict("fleet_average_age", "float"))).dropna() # Remove airlines with no fleet average age data
        sorted_fleet_avg_ages = fleet_avg_ages.sort_values(ascending=True)
        top10_sorted_fleet_avg_ages = sorted_fleet_avg_ages.head(10) # Get the top 10 youngest airlines by fleet average age
        plot_bar_graph(top10_sorted_fleet_avg_ages, "Airline Fleet Average Ages", "Fleet Average Age")
    elif comparison_option == "Founding Year":
        founding_years = (pd.Series(get_airline_feature_dict("date_founded", "int"))).dropna() # Remove airlines with no founding year data
        sorted_founding_years = founding_years.sort_values(ascending=True)
        top10_sorted_founding_years = sorted_founding_years.head(10) # Get the top 10 oldest airlines by founding year
        plot_bar_graph(top10_sorted_founding_years, "Airline Founding Years", "Founding Year", bottom_ylim=1900) # Set y-axis minimum so years before 1900 since no airlines were founded before then
else:
    if comparison_option == "Fleet Size":
        fleet_sizes = (pd.Series(get_airline_feature_dict("fleet_size", "int"))).dropna() # Remove airlines with no fleet size data
        filtered_fleet_sizes = fleet_sizes[countries_of_origin == country_filter_option] # Ensure only airlines from the selected country are included
        sorted_fleet_sizes = filtered_fleet_sizes.sort_values(ascending=True)
        plot_bar_graph(sorted_fleet_sizes, "Airline Fleet Sizes", "Fleet Size")
    elif comparison_option == "Fleet Average Age":
        fleet_avg_ages = (pd.Series(get_airline_feature_dict("fleet_average_age", "float"))).dropna() # Remove airlines with no fleet average age data
        filtered_fleet_avg_ages = fleet_avg_ages[countries_of_origin == country_filter_option] # Ensure only airlines from the selected country are included
        sorted_fleet_avg_ages = filtered_fleet_avg_ages.sort_values(ascending=True)
        plot_bar_graph(sorted_fleet_avg_ages, "Airline Fleet Average Ages", "Fleet Average Age")
    elif comparison_option == "Founding Year":
        founding_years = (pd.Series(get_airline_feature_dict("date_founded", "int"))).dropna() # Remove airlines with no founding year data
        filtered_founding_years = founding_years[countries_of_origin == country_filter_option] # Ensure only airlines from the selected country are included
        sorted_founding_years = filtered_founding_years.sort_values(ascending=True)
        plot_bar_graph(sorted_founding_years, "Airline Founding Years", "Founding Year", bottom_ylim=1900) # Set y-axis minimum so years before 1900 since no airlines were founded before then