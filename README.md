Global Flight Snapshot via OpenSky Network:

This project is a Streamlit dashboard that visualizes live aircraft data from the OpenSky Network API. 
It fetches a real-time snapshot of active flights (~1,800 aircraft globally) and displays:

Number of active flights
Top 30 countries by active flights (bar chart)
Scatter map of global flight positions.

The work was split up by 5 people: Shreya Mendi, Omkar Sreekanth, Arnav Mahale, Hanfu Zhao, and Ethan Dominic. Each person's contributions are listed below:

Omkar's Portion:

The following graphs were created by **Omkar Sreekanth (`oarkse7486`)** in the file `streamlit_app.py`:

- Flights by altitude bands (bar chart, feet)  
- Top airlines by callsign prefix (bar chart of top 15 airlines)  
- Flights by broad region (pie chart: Americas, Europe/Africa, Asia-Pacific)  

Note: Some earlier commits may appear under his old GitHub username **`sromee98403`**
but all commits under both usernames were authored by **Omkar Sreekanth**.

=======
Top 10 Airlines departed from RDU in the last 6 hours
>>>>>>> 754ce3af99ee183159a79d664cbb5a6814d977a0

Prerequisites

Before running the app, make sure you have:
Python 3.8+ installed
Access to the internet (to fetch live OpenSky API data)
pip package manager

Installation

Clone this repository or copy the source files:

<<<<<<< HEAD
git clone https://github.com/yourusername/opensky-flight-dashboard.git
cd opensky-flight-dashboard
=======
git clone https://github.com/Shreya-Mendi/Bootcamp_project.git
cd Bootcamp_project/
>>>>>>> 754ce3af99ee183159a79d664cbb5a6814d977a0

(Optional but recommended) Create a virtual environment:

python -m venv venv
source venv/bin/activate   # On Mac/Linux
venv\Scripts\activate      # On Windows

Install the required dependencies:

pip install -r requirements.txt


Project Structure

.

├── fetchapi.py           # Fetches flight snapshot from OpenSky API

├── streamlit_app.py      # Streamlit dashboard

├── requirements.txt      # Python dependencies

└── README.md             # Project documentation


Usage

Run locally

Start the Streamlit app:
streamlit run streamlit_app.py
This will open a browser window at http://localhost:8501.

Example Workflow
Click "Fetch Live Flights"
View:
Total number of flights in the snapshot
Top 30 countries by active flights (bar chart)
Global scatter map of flight positions
<<<<<<< HEAD

=======
Click "Fetch RDU Data"
View:
Bar Graph of Top 10 Airlines from RDU
>>>>>>> 754ce3af99ee183159a79d664cbb5a6814d977a0

Requirements

Here’s a sample requirements.txt you can use:
requests
pandas
streamlit
matplotlib

Notes & Limitations

The OpenSky free API is rate-limited (about 1 request every 10 seconds, max ~1,800 aircraft per snapshot).
If no flights are shown, try again after a few seconds.
Only live data is shown—no historical flight data is stored.

Data Source

All data comes from the public OpenSky API
Snapshot is limited to ~1800 flights by the free tier

Live Demo

View it on Hugging Face Spaces:
https://huggingface.co/spaces/ShreyaMendi/Skyline 

Example Output

Top 30 Countries by Active Flights
A horizontal bar chart ranking countries with the most flights in the snapshot.
Global Flight Positions (Scatter Map)
A scatter plot of aircraft positions by latitude/longitude.

=======
