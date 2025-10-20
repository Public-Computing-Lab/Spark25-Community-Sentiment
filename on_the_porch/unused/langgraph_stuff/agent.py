#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_core.messages import HumanMessage


# from postgres_stuff.test import DB_URL

DB_URL = "postgresql://user1:BbWTihWnsBHglVpeKK8XfQgEPDOcokZZ@dpg-d3g661u3jp1c73eg9v1g-a.ohio-postgres.render.com/crime_rate_h3u5"

# Load environment variables from .env file
load_dotenv()

# LangSmith tracing (enable + credentials + optional project/run metadata)
os.environ["LANGCHAIN_TRACING_V2"] = "true"
# Replace with your actual LangSmith API key and endpoint
os.environ["LANGSMITH_API_KEY"] = "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"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
# Optional but recommended for organization
os.environ["LANGCHAIN_PROJECT"] = "spark_eda-sql-agent"
os.environ["LANGCHAIN_SESSION"] = "local-dev"


def build_agent():
    model = os.getenv("OPENAI_MODEL", "gpt-4")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in .env file")
    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
    db = SQLDatabase.from_uri(DB_URL)
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools()
    return create_react_agent(llm, tools)


def main():
    question = "what are the most common 311 call by week?"
    agent = build_agent()
    result = agent.invoke({"messages": [HumanMessage(content=question)]})
    messages = result.get("messages", [])
    answer = messages[-1].content if messages else ""
    print(answer)


if __name__ == "__main__":
    main()


