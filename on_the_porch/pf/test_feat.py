from simple_sql_qa_pocketflow import generate_sql, get_schema
import json

# Test dual SQL query generation
print("="*60)
print("Testing Dual SQL Query Generation")
print("="*60)

# Get schema for the table
table_name = "Dorchester_311"
schema = get_schema(table_name)
print(f"\nSchema:\n{schema}\n")

# Test question
question = "what are the top 5 request types by count?"

print(f"Question: {question}\n")

# Generate SQL queries
queries, tokens = generate_sql(question, schema)

print("Generated Queries:")
print("="*60)
print("\n1. Answer Query:")
print(queries["answer_query"])
print("\n2. Map Query:")
print(queries["map_query"])
print("\n" + "="*60)
print(f"Tokens used: {tokens}")

# Verify structure
print("\n" + "="*60)
print("Verification:")
print("="*60)

# Check answer_query
assert "answer_query" in queries, "Missing 'answer_query' key"
assert isinstance(queries["answer_query"], str), "answer_query is not a string"
assert len(queries["answer_query"]) > 0, "answer_query is empty"
print("✓ Answer query is valid")

# Check map_query
assert "map_query" in queries, "Missing 'map_query' key"
map_query = queries["map_query"]

if map_query is None or (isinstance(map_query, str) and map_query.strip() == ""):
    print("✓ Map query is null/empty (LLM decided mapping not relevant)")
    print("  This is expected for statistical/aggregate questions")
elif isinstance(map_query, str):
    print("✓ Map query is a valid string")
    if "LIMIT" in map_query.upper():
        print("✓ Map query has LIMIT clause")
    else:
        print("⚠ Warning: Map query missing LIMIT clause")
    if "latitude" in map_query.lower() or "longitude" in map_query.lower():
        print("✓ Map query includes lat/lon columns")
else:
    raise AssertionError(f"map_query has unexpected type: {type(map_query)}")

print("\n✓ Test passed!")

