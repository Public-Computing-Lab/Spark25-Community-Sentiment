# System Design Document

## Overview

RethinkAI is a Dorchester-focused community assistant that answers user questions by combining:

- **SQL queries** over structured data such as Boston 311 records, 911/public safety data, and community events
- **RAG retrieval** over unstructured documents such as policy reports, transcripts, newsletters, and community notes
- **LLM orchestration** to decide which data path to use and to generate a user-friendly answer

The system is designed to support both factual questions like “What events are happening this weekend?” and interpretive questions like “What do residents say about safety?”

## High-Level Architecture

```mermaid
flowchart TD
    subgraph Runtime["Runtime Question-Answering Path"]
        A[User / Browser] --> B[Static Frontend]
        B --> C[Flask API]
        C --> D[Chat Orchestrator]
        D --> E[SQL Pipeline]
        D --> F[RAG Pipeline]
        E --> G[(MySQL)]
        F --> H[(Chroma Vector DB)]
        D --> I[Gemini Models]
        E --> I
        F --> I
    end

    subgraph Ingestion["Offline Ingestion / Data Update Path"]
        K[Drive / Gmail / Boston Open Data] --> J[Ingestion Jobs]
        J --> G
        J --> H
    end
```

## Main Components

### 1. Frontend

The frontend is a static web interface in `public/` that sends user messages to the Flask backend and displays responses, sources, and events. It is lightweight and easy to deploy because it does not require a build-heavy framework for core usage.

### 2. API Layer

The backend API in [`api/api_v2.py`](/Users/atharvgulati/Desktop/BU%20Spring%2026%20Assignments/CS%20549/ml-misi-community-sentiment/api/api_v2.py) is responsible for:

- authentication and session handling
- conversation and message storage
- chat request handling
- event retrieval
- admin and moderation endpoints

It supports both authenticated user sessions and a legacy API-key flow for compatibility.

### 3. Chat Orchestrator

The orchestrator in [`on_the_porch/unified_chatbot.py`](/Users/atharvgulati/Desktop/BU%20Spring%2026%20Assignments/CS%20549/ml-misi-community-sentiment/on_the_porch/unified_chatbot.py) is the core logic layer. It:

- checks whether a follow-up question can be answered from recent cached context
- routes the question to `sql`, `rag`, or `hybrid`
- executes the chosen data path
- merges results into one final answer

This layer is what makes the system a real hybrid assistant rather than a single retrieval tool.

### 4. SQL Pipeline

The SQL path in [`on_the_porch/sql_chat/app4.py`](/Users/atharvgulati/Desktop/BU%20Spring%2026%20Assignments/CS%20549/ml-misi-community-sentiment/on_the_porch/sql_chat/app4.py) handles structured questions, especially:

- event and schedule queries
- counts, trends, and comparisons
- public-safety and 311 analytics

It works by:

1. reading the live MySQL schema
2. generating SQL with Gemini
3. executing and retrying if needed
4. summarizing the results in plain language

### 5. RAG Pipeline

The RAG path in [`on_the_porch/rag stuff/retrieval.py`](/Users/atharvgulati/Desktop/BU%20Spring%2026%20Assignments/CS%20549/ml-misi-community-sentiment/on_the_porch/rag%20stuff/retrieval.py) handles document-based questions, especially:

- policy interpretation
- meeting transcript questions
- neighborhood news and newsletter content
- community/admin knowledge

It uses:

- Gemini embeddings
- Chroma as the vector database
- metadata filters for source, document type, and tags

If semantic retrieval fails, it falls back to keyword-based retrieval.

## Request Flow

When a user submits a question, the system follows this process:

1. The frontend sends the message to the Flask API.
2. The API validates the session or API key.
3. The orchestrator checks whether recent cached context is enough.
4. If new retrieval is needed, the router selects `sql`, `rag`, or `hybrid`.
5. The selected pipeline runs and returns evidence.
6. The orchestrator generates the final answer.
7. The API stores the interaction and returns the response to the frontend.

### Chat Flowchart

```mermaid
flowchart TD
    A[User submits question] --> B[Flask API receives request]
    B --> C[Validate session or API key]
    C --> D[Load conversation history and cache]
    D --> E{Need new data?}
    E -- No --> F[Answer from cached context]
    E -- Yes --> G[Route question]
    G --> H{Mode selected}
    H -- SQL --> I[Run SQL pipeline]
    H -- RAG --> J[Run RAG pipeline]
    H -- Hybrid --> K[Run SQL and RAG]
    I --> L[Generate final answer]
    J --> L
    K --> L
    F --> M[Store interaction]
    L --> M
    M --> N[Return response to frontend]
```

### Runtime Workflow (Detailed)

This rendering shows the full runtime pipeline from input to output, including the
conversation-cache shortcut and the different execution paths (`sql`, `rag`, `hybrid`).

![Runtime workflow diagram](docs/diagrams/runtime_workflow.svg)

```mermaid
flowchart TD
  A[User types message in UI] --> B[Frontend POST message to API]
  B --> C[Flask API: api/api_v2.py<br/>/conversations/:id/messages or /chat]
  C --> D[Load context from MySQL<br/>- thread/messages<br/>- thread_state_json cache]

  D --> E{Needs new data?<br/>_check_if_needs_new_data}
  E -- No --> F[Answer from history/cache<br/>_answer_from_history]
  F --> H[Persist + return response<br/>save thread_state_json + messages]

  E -- Yes --> I[Route question<br/>_route_question]
  I --> J{Route mode}

  %% SQL path
  J -- sql --> K[SQL agent: _run_sql]
  K --> K1[Fetch schema snapshot<br/>information_schema.columns]
  K1 --> K2[LLM generates MySQL SELECT<br/>sql_chat/app4.py]
  K2 --> K3[Enforce Dorchester-only filter<br/>_ensure_dorchester_filter]
  K3 --> K4[Execute SQL with retries<br/>MySQL]
  K4 --> K5[LLM summarizes rows to answer<br/>_llm_generate_answer]
  K5 --> K6[Update retrieval cache<br/>sql rows + sql query]
  K6 --> H

  %% RAG path
  J -- rag --> L[RAG: _run_rag]
  L --> L1[Chroma retrieval<br/>similarity_search + filters]
  L1 --> L2[Optional sources queried<br/>RSS + policies + transcripts + cached Boston.gov]
  L2 --> L3[LLM composes answer from chunks<br/>_compose_rag_answer]
  L3 --> L4[Optional fallback on low-confidence phrasing<br/>Boston.gov augmentation]
  L4 --> L5[Update retrieval cache<br/>chunks + metadata]
  L5 --> H

  %% Hybrid path
  J -- hybrid --> M[Hybrid: _run_hybrid]
  M --> M1[Run SQL path]
  M --> M2[Run RAG path]
  M2 --> M3[LLM merges SQL + RAG into one answer]
  M3 --> M4[Optional fallback]
  M4 --> M5[Update retrieval cache<br/>sql + rag payloads]
  M5 --> H
```

## Data Architecture

The system uses two main storage layers because the data has two very different shapes.

### MySQL

MySQL stores structured and operational data such as:

- 311 data
- 911/public safety data
- extracted community events
- users, sessions, threads, and messages
- interaction logs and moderation data

MySQL is a good fit here because these datasets need exact filtering, time-based queries, and aggregation.

### Chroma Vector DB

Chroma stores unstructured text such as:

- policy documents
- community transcripts
- newsletters
- uploaded documents
- admin/community notes

Chroma is a good fit because these sources are better searched semantically than with exact SQL filtering.

## Data Ingestion Pipeline

The ingestion system in `on_the_porch/data_ingestion/` keeps the data sources up to date.

Its main inputs are:

- Google Drive documents
- Gmail/newsletter content
- Boston open data and community sources

Its outputs are:

- **MySQL** for structured event and city data
- **Chroma** for searchable document content

This hybrid ingestion design matches the runtime architecture: structured data goes to SQL, and narrative text goes to vector search.

### Ingestion Pipeline Workflow (Detailed)

This rendering shows the major offline ingestion steps that populate:
- **MySQL** (structured tables like `weekly_events`, 311/911 tables, etc.)
- **Chroma** (embedded documents and other unstructured sources)

![Ingestion workflow diagram](docs/diagrams/ingestion_workflow.svg)

```mermaid
flowchart TD
  A[Scheduled job or manual run] --> B[main_daily_ingestion.py]
  B --> P0[Phase 0: Dotnews PDF]
  P0 --> P0a[Download latest newsletter PDF]
  P0a --> P0b[Extract events from pages]
  P0b --> MYSQL1[(MySQL: weekly_events)]
  B --> P1[Phase 1: Google Drive sync]
  P1 --> P1a[List files and diff sync state]
  P1a --> P1b[Download new or updated docs]
  P1b --> P1c[Chunk and embed docs]
  P1c --> CH1[(Chroma vector DB)]
  B --> P2[Phase 2: Gmail newsletters]
  P2 --> P2a[Fetch emails and parse newsletters]
  P2a --> P2b[Extract events]
  P2b --> MYSQL1
  B --> P3[Phase 3: Boston Open Data sync]
  P3 --> P3a[Fetch datasets per config]
  P3a --> MYSQL2[(MySQL: 311 and 911 tables)]
  B --> P35[Phase 3.5: 311 and Crime to RAG]
  P35 --> P35a[Generate summary docs for last N days]
  P35a --> CH1
  B --> P4[Phase 4: Build or update vector DB]
  P4 --> P4a[build_vectordb.py]
  P4a --> CH1
  CH1 --> Z[Runtime retrieval uses Chroma]
  MYSQL1 --> Z2[Runtime events and SQL agent use MySQL]
  MYSQL2 --> Z2
```

## Deployment and Infrastructure

The current system is designed to run with a simple deployment stack:

- static frontend
- Flask API
- MySQL database
- Chroma vector store on disk
- Gemini API for generation and embeddings

The repo also includes demo and DreamHost deployment scripts, which makes the system easy to run in a class, evaluation, or lightweight hosted environment.

## Strengths

- Supports both analytical and document-based questions
- Uses the right storage layer for each data type
- Keeps conversation context through cached retrieval state
- Includes moderation, admin knowledge, and community note workflows
- Has a practical ingestion pipeline instead of relying on static demo data only

## Limitations

- Legacy cache is in-memory, so it does not scale cleanly across multiple API instances
- The system depends heavily on Gemini for routing, SQL generation, and answer synthesis
- Chroma is currently file-based, which is fine for small deployments but weaker for larger production scaling
- Data freshness depends on scheduled ingestion running reliably

## Recommended Future Improvements

- move cache storage to Redis
- use a centralized or managed vector database for scale
- add stronger monitoring and data-freshness alerts
- harden production security with stricter CORS, HTTPS-only cookies, and rate limiting

## Conclusion

RethinkAI uses a hybrid architecture because no single retrieval method is enough for this problem. SQL is best for exact event and city-data questions, while RAG is best for documents and community narratives. The orchestrator ties these together into one conversational system that is practical, extensible, and well aligned with the project’s Dorchester community focus.
