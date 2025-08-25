import requests
from dotenv import load_dotenv
import streamlit as st
import os
import pandas as pd
from test_json import return_json
import matplotlib.pyplot as plt

"""
load_dotenv()
api_key = os.getenv("AVIATION_KEY")
url = f"https://api.aviationstack.com/v1/airlines?access_key={api_key}"
response = requests.get(url)
airline_data = response.json()
"""
airline_data = return_json() # For testing

def get_airline_feature_dict(feature_type, cast_type):
    airline_feature_dict = {}
    for i in range(len(airline_data["data"])):
        airline_name = airline_data["data"][i]["airline_name"]
        if cast_type == "int":
            airline_feature_value = int(airline_data["data"][i][feature_type])
        elif cast_type == "str":
            airline_feature_value = str(airline_data["data"][i][feature_type])
        else:
            airline_feature_value = float(airline_data["data"][i][feature_type])
        airline_feature_dict[airline_name] = airline_feature_value
    return airline_feature_dict

def plot_bar_graph(feature_df, title, ylabel, bottom_ylim=0):
    fig, ax = plt.subplots()
    bars = ax.bar(feature_df.index.astype(str), feature_df.values)
    ax.set_title(title)
    ax.set_xlabel("Airline")
    ax.set_ylabel(ylabel)
    ax.bar(feature_df.index, feature_df.values)
    ax.bar_label(bars, padding=3)
    plt.xticks(rotation=45)
    plt.ylim(bottom=bottom_ylim)
    st.pyplot(fig)

st.title("Airline Profile Comparison")
comparison_option = st.radio(
    "Pick the type of comparison you would like to see: ",
    ("Fleet Size", "Fleet Average Age", "Founding Year")
)

countries_of_origin = pd.Series(get_airline_feature_dict("country_name", "str"))

country_filters = countries_of_origin.unique().tolist()
country_filters.append("All Countries")

country_option = st.radio(
    "Pick a country of origin to filter by: ",
    (country_filters)
)

if country_option == "All Countries":
    if comparison_option == "Fleet Size":
        fleet_sizes = pd.Series(get_airline_feature_dict("fleet_size", "int"))
        sorted_fleet_sizes = fleet_sizes.sort_values(ascending=True)
        plot_bar_graph(sorted_fleet_sizes, "Airline Fleet Sizes", "Fleet Size")
    elif comparison_option == "Fleet Average Age":
        fleet_avg_ages = pd.Series(get_airline_feature_dict("fleet_average_age", "float"))
        sorted_fleet_avg_ages = fleet_avg_ages.sort_values(ascending=True)
        plot_bar_graph(sorted_fleet_avg_ages, "Airline Fleet Average Ages", "Fleet Average Age")
    elif comparison_option == "Founding Year":
        founding_years = pd.Series(get_airline_feature_dict("date_founded", "int"))
        sorted_founding_years = founding_years.sort_values(ascending=True)
        plot_bar_graph(sorted_founding_years, "Airline Founding Years", "Founding Year", bottom_ylim=1900)
else:
    if comparison_option == "Fleet Size":
        fleet_sizes = pd.Series(get_airline_feature_dict("fleet_size", "int"))
        filtered_fleet_sizes = fleet_sizes[countries_of_origin == country_option]
        sorted_fleet_sizes = filtered_fleet_sizes.sort_values(ascending=True)
        plot_bar_graph(sorted_fleet_sizes, "Airline Fleet Sizes", "Fleet Size")
    elif comparison_option == "Fleet Average Age":
        fleet_avg_ages = pd.Series(get_airline_feature_dict("fleet_average_age", "float"))
        filtered_fleet_avg_ages = fleet_avg_ages[countries_of_origin == country_option]
        sorted_fleet_avg_ages = filtered_fleet_avg_ages.sort_values(ascending=True)
        plot_bar_graph(sorted_fleet_avg_ages, "Airline Fleet Average Ages", "Fleet Average Age")
    elif comparison_option == "Founding Year":
        founding_years = pd.Series(get_airline_feature_dict("date_founded", "int"))
        filtered_founding_years = founding_years[countries_of_origin == country_option]
        sorted_founding_years = filtered_founding_years.sort_values(ascending=True)
        plot_bar_graph(sorted_founding_years, "Airline Founding Years", "Founding Year", bottom_ylim=1900)