# execution.md

# Natural Language to Data Visualization — Execution Guide (Pocket Flow)

**Purpose**
This document describes the execution plan and Pocket Flow definition for the Natural Language to Data Visualization system. It is an operations and developer-facing guide that describes how the orchestration engine runs, the responsibilities of each node, input/output contracts, failure modes, observability needs, and testing steps.

---

## Table of contents

1. Overview
2. High-level flow (Pocket Flow)
3. Node definitions and contracts
4. Prompt templates and examples
5. Error handling, retries, and timeouts
6. Caching and metadata strategies
7. Security and access control
8. Instrumentation and observability
9. Testing and validation
10. Deployment and runbook
11. Appendix: sample payloads and flow YAML

---

## 1. Overview

This system converts user natural language queries into three possible artifacts: a raw data table, a short human-readable summary, and an interactive map if geospatial data exists. The orchestration engine executes a deterministic sequence of modules. Pocket Flow represents each module as a node with explicit input and output contracts. The engine manages control flow, parallelism where safe, and end-to-end error handling.

Design goals

* Deterministic execution and clear contracts between modules.
* Minimal trust surface for LLMs: do not allow LLMs to perform unchecked external actions.
* Fast responses for analysis tasks while retaining accuracy for SQL generation.
* Observability for each step: timings, inputs, outputs, and failures.

## 2. High-level flow (Pocket Flow)

Below is a compact representation of the flow. Each line is a node: `node-name: type -> next-node`.

```
receive_query: http -> query_analysis
query_analysis: llm_small -> metadata_retrieval
metadata_retrieval: metadata_store -> sql_generation
sql_generation: llm_strong -> data_fetch
data_fetch: db_exec -> data_enrichment
data_enrichment: processing -> conditional_summary
conditional_summary: when(summary_flag)->summary_llm | when(not summary_flag)->conditional_visualization
conditional_visualization: when(has_geo)->map_generation | when(not has_geo)->final_assembly
map_generation: viz -> final_assembly
summary_llm: llm_strong -> final_assembly
final_assembly: packager -> respond
respond: http_response
```

Notes

* `llm_small` denotes a lightweight model tuned for intent parsing.
* `llm_strong` denotes a larger model reserved for SQL construction and natural language summarization.
* `db_exec` interacts with the canonical datastore and returns a normalized JSON records array.

## 3. Node definitions and contracts

For each node, this section defines: purpose, inputs, outputs, validation rules, and examples.

### receive_query

* Purpose: Accept incoming requests (REST or gRPC) and basic validation.
* Input: HTTP body `{ user_id, query_text, locale?, session_id? }`.
* Output: `{ request_id, user_id, query_text, received_at }`.
* Validation: `query_text` non-empty; `user_id` present or null for anonymous requests.

### query_analysis

* Purpose: Parse intent, entities, time windows, and output flags.
* Inputs: `{ request_id, query_text }`.
* Outputs: `{ request_id, intent, entities:[], date_ranges:[], summary_flag:bool, limit:int|null, raw_query_text }`.
* Validation: `intent` from allowed set e.g., ["aggregate", "timeseries", "slice", "count", "top_k"]
* Implementation notes: Use a small LLM or deterministic parser for performance. Return canonical entity types: `location`, `datetime`, `metric`, `dimension`.

### metadata_retrieval

* Purpose: Map intent and entities to concrete tables and columns.
* Inputs: `{ intent, entities }`.
* Outputs: `{ tables:[{name, columns:[{name,type}], sample_rows_url?}], schema_hash }`.
* Validation: Ensure every referenced concept maps to at least one column. If no match, return a `no_schema_match` error.
* Caching: Cache schema responses by `schema_hash` for 1 hour or until schema change.

### sql_generation

* Purpose: Produce a single, executable SQL query string.
* Inputs: `{ request_id, raw_query_text, tables, columns, schema_hash, entities, constraints }`.
* Outputs: `{ sql_text, deterministic_hash }`.
* Validation: SQL must parse with the DB's explain/prepare endpoint. If the DB returns a parse error, fail fast and record the error.
* Safety: The LLM is strictly limited by prompt to produce a single `SELECT` statement. Do not allow DDL, DML or multiple statements.

### data_fetch

* Purpose: Execute SQL and return normalized results.
* Inputs: `{ sql_text, request_id, db_timeout_ms }`.
* Outputs: `{ rows:[{...}], row_count:int, columns:[{name,type}], execution_time_ms }`.
* Validation: Enforce `row_count` limit (e.g., 10k rows). If above the limit, return a `result_truncated` flag and include a `sample` subset.
* Implementation notes: Use prepared statement support and parameterized queries where available. Use read-only credentials.

### data_enrichment

* Purpose: Normalize types, detect geospatial columns, and convert to canonical formats.
* Inputs: `{ rows, columns }`.
* Outputs: `{ rows, columns, has_geo:bool, geo_columns:[names], numeric_summary:{ column: {min,max,mean,median} } }`.
* Validation: Geo detection by matching column names (lat, lon, latitude, longitude, geom) and by heuristics (value ranges, common coordinate formats).

### summary_llm

* Purpose: Produce a human-readable summary of the result in the context of the original query.
* Inputs: `{ rows_sample, columns, raw_query_text, request_id }`.
* Outputs: `{ summary_text, explainability_notes }`.
* Constraints: Limit summary to 150-300 words. Include an explicit "method" sentence stating whether summary was from sample or full results.

### map_generation

* Purpose: Create an interactive map artifact from geospatial data.
* Inputs: `{ rows, geo_columns, columns, style_hints? }`.
* Outputs: `{ map_url_or_object, static_preview_png?, map_metrics }`.
* Implementation notes: Prefer vector tiles and lightweight client-side rendering. Provide a static preview fallback for systems that cannot render interactive maps.

### final_assembly

* Purpose: Package the artifacts into a final response.
* Inputs: `{ rows_or_sample, columns, summary_text?, map_object? }`.
* Outputs: `{ response_payload, render_hints }`.
* Validation: Check for payload size. If payload large, return a paginated access pattern with a download link.

## 4. Prompt templates and examples

These templates are stable strings the Pocket Flow uses when invoking LLM nodes. Keep prompts short and explicit. Always append safety and format constraints.

### Query analysis prompt (llm_small)

```
SYSTEM: You are a lightweight parser. Extract intent and entities from the user query.
USER: {{raw_query_text}}
INSTRUCTIONS: Return JSON with fields: intent, entities, date_ranges, summary_flag, limit. Ensure valid JSON only.
```

### SQL generation prompt (llm_strong)

```
SYSTEM: You are a strict SQL generator. Produce a single executable SELECT statement that answers the user's question using the provided schema. Do not produce comments or extra text. If the schema cannot answer the query, return {"error":"schema_mismatch"}.
CONTEXT: Schema: {{tables_and_columns_json}}
USER_QUERY: {{raw_query_text}}
REQUIREMENTS: Use parameters for any user-provided values. Limit results to {{limit}} if provided
```
