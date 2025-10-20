#!/usr/bin/env python3
"""
Simple Vanna Flask App for PostgreSQL using OpenAI from .env
"""

import os
from dotenv import load_dotenv
from vanna.chromadb import ChromaDB_VectorStore
from vanna.flask import VannaFlaskApp
from vanna.openai import OpenAI_Chat


class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)


def main():
    print("🚀 Starting Vanna Flask App...")
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get OpenAI credentials from .env
    openai_api_key = os.getenv('OPENAI_API_KEY')
    openai_model = os.getenv('OPENAI_MODEL', 'gpt-4')
    
    print(f"Using OpenAI model: {openai_model}")
    
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not found in .env file")
    
    # Initialize with OpenAI API key from .env
    vn = MyVanna(config={
        'api_key': openai_api_key,
        'model': openai_model,
        'allow_llm_to_see_data': True
    })

    # Connect to PostgreSQL database directly
    vn.connect_to_postgres(
        host='dpg-d3g661u3jp1c73eg9v1g-a.ohio-postgres.render.com',
        dbname='crime_rate_h3u5',
        user='user1',
        password='BbWTihWnsBHglVpeKK8XfQgEPDOcokZZ',
        port=5432
    )
    print("✅ Connected to PostgreSQL database")

    # Launch the default Vanna Flask app
    app = VannaFlaskApp(vn)

    print("🌐 Open your browser and go to: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)


if __name__ == "__main__":
    main()
