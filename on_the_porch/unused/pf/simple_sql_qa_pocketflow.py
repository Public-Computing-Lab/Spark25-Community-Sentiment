import os
import pandas as pd
import time
from sqlalchemy import create_engine, text
from openai import OpenAI
from langsmith import Client
from pocketflow import Flow, Node
import folium
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuration
# PostgreSQL Configuration (commented out)
# DB_URL = os.getenv('DB_URL')

# SQLite Configuration (local database)
DB_URL = 'sqlite:///data/dorchester_311.db'
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')


# Set environment variables for LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = os.getenv('LANGCHAIN_API_KEY')
os.environ["LANGCHAIN_PROJECT"] = 'pocketflow-testing'

client = Client(api_key=os.environ.get('LANGCHAIN_API_KEY'))

def get_schema(table_name):
    """Get table schema"""
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        # PostgreSQL schema query (commented out)
        # result = conn.execute(text(f"""
        #     SELECT column_name, data_type 
        #     FROM information_schema.columns 
        #     WHERE table_name = '{table_name}'
        #     ORDER BY ordinal_position
        # """))
        # columns = result.fetchall()
        # return f"Table '{table_name}' columns:\n" + "\n".join([f"- {col[0]} ({col[1]})" for col in columns])
        
        # SQLite schema query
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = result.fetchall()
        # SQLite PRAGMA returns: cid, name, type, notnull, dflt_value, pk
        return f"Table '{table_name}' columns:\n" + "\n".join([f"- {col[1]} ({col[2]})" for col in columns])

def generate_sql(question, schema):
    """Generate SQL using LLM - returns both aggregate and detail queries"""
    from langsmith import traceable
    import json
    
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    
    # PostgreSQL prompt (commented out)
    # prompt = f"""Question: {question}
    # Database: PostgreSQL
    # Schema:
    # {schema}
    # Generate TWO PostgreSQL queries and return them as a JSON object:
    
    # SQLite prompt
    prompt = f"""Question: {question}

Database: SQLite

Schema:
{schema}

Generate TWO SQLite queries and return them as a JSON object:

1. "answer_query": Query to answer the question (may use COUNT, SUM, AVG, GROUP BY, etc.)

2. "map_query": Query to fetch individual rows with latitude and longitude for mapping.
   - If the question involves geographic/spatial insights (locations, areas, where something is), include a query with latitude/longitude columns and relevant WHERE filters. Add LIMIT 1000.
   - If the question is purely statistical/aggregated with no spatial component (counts, averages, top categories), set this to null or an empty string.
   
   Decide based on whether seeing locations on a map would be useful for the question.

Return ONLY valid JSON in this exact format:
{{
    "answer_query": "SELECT ...",
    "map_query": "SELECT ... LIMIT 1000" OR null
}}"""
    
    @traceable(name="sql_generation", metadata={"model": "gpt-4o-mini", "provider": "openai"})
    def _generate_sql_inner(question, schema):
        start_time = time.time()
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        inference_time = time.time() - start_time
        
        result = response.choices[0].message.content.strip()
        
        # Extract JSON from markdown if present
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()
        
        # Parse JSON
        queries = json.loads(result)
        
        # Log token usage and inference time
        tokens_used = 0
        if hasattr(response, 'usage') and response.usage:
            tokens_used = response.usage.total_tokens
            metrics = {
                "total_tokens": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "inference_time_seconds": round(inference_time, 3),
                "tokens_per_second": round(response.usage.total_tokens / inference_time, 2) if inference_time > 0 else 0,
                "cost_estimate": response.usage.total_tokens * 0.00015
            }
            print(f"SQL Generation - Metrics: {metrics}")
        
        return queries, tokens_used
    
    result = _generate_sql_inner(question, schema)
    return result

def run_sql(sql):
    """Execute SQL and return DataFrame"""
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        return df

def generate_answer(question, df):
    """Generate answer using LLM"""
    from langsmith import traceable
    
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    
    data_sample = df.head(10).to_json(orient="records")
    
    prompt = f"""Question: {question}

Data:
{data_sample}

Answer:"""
    
    @traceable(name="answer_generation", metadata={"model": "gpt-4o-mini", "provider": "openai"})
    def _generate_answer_inner(question, data_sample):
        start_time = time.time()
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        inference_time = time.time() - start_time
        
        answer = response.choices[0].message.content.strip()
        
        # Log token usage and inference time
        tokens_used = 0
        if hasattr(response, 'usage'):
            tokens_used = response.usage.total_tokens
            metrics = {
                "total_tokens": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "inference_time_seconds": round(inference_time, 3),
                "tokens_per_second": round(response.usage.total_tokens / inference_time, 2) if inference_time > 0 else 0,
                "cost_estimate": response.usage.total_tokens * 0.00015
            }
            print(f"Answer Generation - Metrics: {metrics}")
        
        return answer, tokens_used
    
    result = _generate_answer_inner(question, data_sample)
    return result

# PocketFlow Nodes
class GetSchemaNode(Node):
    def prep(self, shared):
        print("Getting schema...")
        return shared.get("table_name")
    
    def exec(self, prep_res):
        schema = get_schema(prep_res)
        print(schema)
        return schema
    
    def post(self, shared, prep_res, exec_res):
        shared["schema"] = exec_res
        return "default"  # Return action to trigger next node

class GenerateSQLNode(Node):
    def prep(self, shared):
        print("\nGenerating SQL...")
        return {
            "question": shared.get("question"),
            "schema": shared.get("schema")
        }
    
    def exec(self, prep_res):
        start_time = time.time()
        queries, tokens = generate_sql(prep_res["question"], prep_res["schema"])
        sql_time = time.time() - start_time
        return {"queries": queries, "tokens": tokens, "time": sql_time}
    
    def post(self, shared, prep_res, exec_res):
        shared["answer_query"] = exec_res["queries"]["answer_query"]
        shared["map_query"] = exec_res["queries"]["map_query"]
        shared["sql_tokens"] = exec_res["tokens"]
        shared["sql_time"] = exec_res["time"]
        print(f"Answer Query: {exec_res['queries']['answer_query']}")
        print(f"Map Query: {exec_res['queries']['map_query']}")
        return "default"  # Return action to trigger next node

class RunQueryNode(Node):
    def prep(self, shared):
        print("\nExecuting SQL queries...")
        return {
            "answer_query": shared.get("answer_query"),
            "map_query": shared.get("map_query")
        }
    
    def exec(self, prep_res):
        start_time = time.time()
        
        # Execute answer query
        answer_df = run_sql(prep_res["answer_query"])
        
        # Execute map query only if it exists and is not empty/null
        map_query = prep_res["map_query"]
        if map_query and isinstance(map_query, str) and map_query.strip():
            map_df = run_sql(map_query)
        else:
            map_df = None
        
        query_time = time.time() - start_time
        return {"answer_df": answer_df, "map_df": map_df, "time": query_time}
    
    def post(self, shared, prep_res, exec_res):
        shared["answer_df"] = exec_res["answer_df"]
        shared["map_df"] = exec_res["map_df"]
        shared["query_time"] = exec_res["time"]
        print(f"Answer query returned {len(exec_res['answer_df'])} rows")
        if exec_res["map_df"] is not None:
            print(f"Map query returned {len(exec_res['map_df'])} rows")
        else:
            print("No map query generated (not relevant for this question)")
        return "default"  # Return action to trigger next node

class PlotMapNode(Node):
    def prep(self, shared):
        return shared.get("map_df")
    
    def exec(self, prep_res):
        df = prep_res
        
        # Check if df exists and is not empty
        if df is None or len(df) == 0:
            print("  → No data to plot, skipping map generation")
            return None
        
        # Check if df has latitude and longitude columns
        lat_col = None
        lon_col = None
        
        for col in df.columns:
            col_lower = col.lower()
            if 'lat' in col_lower and not lon_col:
                lat_col = col
            if 'lon' in col_lower or 'lng' in col_lower:
                lon_col = col
        
        if not lat_col or not lon_col:
            print("  → No latitude/longitude columns found, skipping map generation")
            return None
        
        # Filter out rows with null/invalid coordinates
        df_valid = df[[lat_col, lon_col]].dropna()
        if len(df_valid) == 0:
            print("  → No valid coordinates found, skipping map generation")
            return None
        
        # Create map centered on mean coordinates (use valid data only)
        center_lat = df_valid[lat_col].mean()
        center_lon = df_valid[lon_col].mean()
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
        
        # Add markers (use original df to preserve all data)
        for _, row in df.iterrows():
            if pd.notna(row[lat_col]) and pd.notna(row[lon_col]):
                # TODO: Customize tooltip text based on your data columns
                tooltip_text = "Location"
                folium.Marker(
                    location=[row[lat_col], row[lon_col]],
                    tooltip=tooltip_text
                ).add_to(m)
        
        # Create maps folder if it doesn't exist
        os.makedirs("maps", exist_ok=True)
        
        # Save map
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"maps/map_{timestamp}.html"
        m.save(filename)
        
        return filename
    
    def post(self, shared, prep_res, exec_res):
        if exec_res:
            shared["map_file"] = exec_res
            print(f"\n✓ Map saved to: {exec_res}")
        else:
            shared["map_file"] = None
            print("\n→ No map generated for this query")
        return "default"

class GenerateAnswerNode(Node):
    def prep(self, shared):
        print("\nGenerating answer...")
        return {
            "question": shared.get("question"),
            "df": shared.get("answer_df")
        }
    
    def exec(self, prep_res):
        start_time = time.time()
        answer, tokens = generate_answer(prep_res["question"], prep_res["df"])
        answer_time = time.time() - start_time
        return {"answer": answer, "tokens": tokens, "time": answer_time}
    
    def post(self, shared, prep_res, exec_res):
        shared["answer"] = exec_res["answer"]
        shared["answer_tokens"] = exec_res["tokens"]
        shared["answer_time"] = exec_res["time"]
        print(f"Answer: {exec_res['answer']}")
        return "default"  # Return action to trigger next node

class SummaryNode(Node):
    def prep(self, shared):
        return shared
    
    def exec(self, prep_res):
        total_time = prep_res.get("sql_time", 0) + prep_res.get("query_time", 0) + prep_res.get("answer_time", 0)
        total_tokens = prep_res.get("sql_tokens", 0) + prep_res.get("answer_tokens", 0)
        total_cost = total_tokens * 0.00015
        
        print("\n" + "="*60)
        print("POCKETFLOW PIPELINE SUMMARY")
        print("="*60)
        print(f"Total Pipeline Time: {round(total_time, 3)}s")
        print(f"  - SQL Generation: {round(prep_res.get('sql_time', 0), 3)}s")
        print(f"  - Query Execution: {round(prep_res.get('query_time', 0), 3)}s")
        print(f"  - Answer Generation: {round(prep_res.get('answer_time', 0), 3)}s")
        print(f"\nTotal Tokens Used: {total_tokens}")
        print(f"  - SQL Generation: {prep_res.get('sql_tokens', 0)}")
        print(f"  - Answer Generation: {prep_res.get('answer_tokens', 0)}")
        print(f"\nEstimated Cost: ${round(total_cost, 6)}")
        print("="*60)
        
        return {
            "total_time": round(total_time, 3),
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6)
        }
    
    def post(self, shared, prep_res, exec_res):
        shared["summary"] = exec_res
        return None

def main():
    # Build PocketFlow pipeline
    get_schema_node = GetSchemaNode()
    generate_sql_node = GenerateSQLNode()
    run_query_node = RunQueryNode()
    plot_map_node = PlotMapNode()
    generate_answer_node = GenerateAnswerNode()
    summary_node = SummaryNode()
    
    # Wire nodes together
    flow = Flow().start(get_schema_node)
    get_schema_node >> generate_sql_node >> run_query_node >> plot_map_node >> generate_answer_node >> summary_node
    
    # Run pipeline
    question = "hwo many parking enforcement requests were made in May 2025?"
    # table_name = "Dorchester_311"  # PostgreSQL table name
    table_name = "service_requests"  # SQLite table name
    
    print("="*60)
    print("Starting PocketFlow SQL QA Pipeline")
    print("="*60)
    
    shared = {"question": question, "table_name": table_name}
    flow._run(shared)
    
    print(f"\nFinal Answer: {shared.get('answer')}")

if __name__ == "__main__":
    main()
