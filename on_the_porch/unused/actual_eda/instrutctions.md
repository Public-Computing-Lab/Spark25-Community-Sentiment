Prompt for Cursor:

I have a CSV file with incident/crime data. The file has columns like:

_id, INCIDENT_NUMBER, OFFENSE_CODE, OFFENSE_CODE_GROUP, OFFENSE_DESCRIPTION, DISTRICT, REPORTING_AREA, SHOOTING, OCCURRED_ON_DATE, YEAR, MONTH, DAY_OF_WEEK, HOUR, UCR_PART, STREET, Lat, Long, Location


Please create a well-documented Jupyter Notebook (.ipynb) for Exploratory Data Analysis (EDA). The notebook should include Markdown explanations and Python code cells.

The notebook should cover the following steps in detail:

Introduction (Markdown)

Explain what the dataset represents and what EDA is.

Outline the goals of this analysis.

Data Loading & Setup

Import necessary libraries (pandas, numpy, matplotlib, seaborn).

Load the CSV file (crime_data.csv).

Display the shape, column names, and first few rows.

Data Cleaning & Preprocessing

Check for missing values and handle them appropriately (e.g., fill OFFENSE_CODE_GROUP with "Unknown").

Convert OCCURRED_ON_DATE to datetime.

Strip whitespace from column names.

Basic Data Overview

Show summary statistics (df.describe(include="all")).

Count unique values for categorical columns like DISTRICT, DAY_OF_WEEK, OFFENSE_DESCRIPTION.

Univariate Analysis

Distribution of incidents by district (bar chart).

Distribution of incidents by day of week (bar chart, ordered from Monday to Sunday).

Distribution of incidents by hour of day (bar chart).

Top 10 offense descriptions (horizontal bar chart).

Bivariate & Temporal Analysis

Plot number of incidents over time (daily/monthly trend).

Compare incidents by district and offense type (heatmap or grouped bar chart).

Analyze shooting incidents vs. non-shooting incidents.

Geospatial Exploration

Simple scatter plot of incidents by latitude and longitude.

(Optional) Add an interactive map using folium if possible.

Correlations

Compute correlations between numerical columns (e.g., YEAR, MONTH, HOUR).

Show a heatmap.

Insights & Observations (Markdown)

Summarize key patterns found in the data.

Highlight which districts or times have higher incident counts.

Mention limitations of the dataset.

Conclusion (Markdown)

Wrap up with what was learned and what could be further explored.

Formatting requirements:

Each section should start with a Markdown heading.

Code should be well-commented so it is clear what each step does.

Plots should have titles, labels, and readable formatting.