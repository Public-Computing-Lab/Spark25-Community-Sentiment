System Design: Natural Language to Data Visualization
This document provides a comprehensive architectural blueprint for a system designed to translate natural language user queries into multifaceted data responses, including raw data tables, textual summaries, and interactive map visualizations.

1. High-Level System Workflow
The system operates on a sequential pipeline that processes a user's query through several specialized modules. Each module performs a distinct task, transforming the data and passing it to the next stage until a final, user-friendly output is generated.

The core workflow is as follows:

Query Ingestion & Analysis: The user's query is received and deconstructed to understand intent and required data.

Contextual Metadata Retrieval: The system fetches the relevant database schema information needed to accurately query the data.

Automated SQL Generation: An LLM constructs a precise SQL query based on the user's intent and the available data schema.

Data Execution & Retrieval: The SQL query is executed against the primary datastore to fetch the raw data.

Data Processing & Presentation: The raw data is processed, optionally summarized by an LLM, and visualized as a map if location data is present. The final package is then presented to the user.

2. Core Design Components
2.1. The Orchestration Engine (OE)
The OE represents the central logic of the architecture. It is not a single component but the overarching control flow that directs data between all other modules. It is responsible for initiating each step in the correct sequence, managing the inputs and outputs, and handling any potential errors.

2.2. Module 1: Query Analysis
This initial module is designed to understand the user's request at a semantic level.

Purpose: To parse the user's raw text query to determine the underlying intent, extract key entities (like locations, dates, or specific metrics), and identify if the user has requested a special output format, such as a summary.

Logical Flow: The OE receives the user's text query and passes it to a small, efficient language model optimized for quick analysis. This model returns a structured interpretation of the query, which includes the core intent, a list of recognized entities, and flags for any special processing requests.

2.3. Module 2: Metadata Retrieval
This module acts as a bridge between the user's query and the database's structure, ensuring that the generated database query is valid and accurate.

Purpose: To fetch the relevant database schemas (table names, column names, data types) based on the intent and entities identified in the previous step. This provides the necessary context for building a correct query.

Logical Flow: Using the structured intent from the analysis module, the OE queries a metadata store. This store maps concepts like "sales" or "products" to specific database tables and columns. The output is the structural information for only the tables needed to answer the user's question.

2.4. Module 3: SQL Generation
This is the core translation module where the user's natural language request becomes machine-executable code.

Purpose: To generate a valid, accurate, and efficient SQL query that reflects the user's intent and is compatible with the database schema.

Logical Flow: The OE provides a powerful language model with a carefully structured prompt. This prompt contains two key pieces of information: the user's original, unaltered query and the relevant table schemas retrieved in the previous step. The model's sole task is to return a single, executable SQL query string.

2.5. Module 4: Data Fetching
This module is responsible for interacting with the database.

Purpose: To connect to the datastore, execute the generated SQL query, and retrieve the results.

Logical Flow: The OE takes the SQL string from the generation module and executes it against the database. This process includes error handling to manage issues like invalid SQL or connection problems. The result is the raw data, which the OE formats into a standard structure, such as a list of records.

2.6. Module 5: Data Processing & Presentation
The final module transforms the raw data into a user-friendly and insightful presentation.

Purpose: To create summaries, build visualizations, and assemble the final response package for the user.

Logical Flow: This is a conditional pipeline managed by the OE.

Summarization: If the query analysis flagged a request for a summary, the OE sends the raw data and the original query to a language model. This model is prompted to generate a brief, human-readable summary of the data in the context of the user's question.

Visualization: The OE inspects the headers of the data results for location-related information. If found, it triggers a map generation function, which uses a visualization library to create an interactive map from the data points.

Final Assembly: The OE gathers all the generated artifacts (the raw data table, the text summary, and any visualizations) into a final package to be displayed to the user.