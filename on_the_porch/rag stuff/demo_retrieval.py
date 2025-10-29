"""
Demo: Two-Step Agentic RAG System

Step 1: LLM decides what to retrieve (doc types, tags, sources)
Step 2: Execute retrieval based on LLM's decision
Step 3: LLM generates final answer from context
"""

from retrieval import retrieve, retrieve_transcripts, retrieve_policies, format_results
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import json

load_dotenv()


def plan_retrieval(query):
    """
    Step 1: LLM analyzes query and decides what to retrieve.
    
    Returns a retrieval plan with doc_type, tags, sources, etc.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    planning_prompt = f"""You are a retrieval planner for a RAG system about Boston community sentiment and policy.

Available data sources:
1. TRANSCRIPTS: Community member interviews with tags like:
   - media, community, safety, violence, policy, youth
   - displacement, government, structural racism, neighborhood events

2. POLICY DOCS: Boston city policy documents including:
   - Boston Anti-Displacement Plan Analysis.txt
   - Boston Slow Streets Plan Analysis.txt
   - Imagine Boston 2030 Analysis.txt

Your task: Analyze the user's question and decide what data to retrieve.

USER QUESTION: {query}

Respond in JSON format:
{{
  "doc_types": ["transcript", "policy", or "both"],
  "transcript_tags": ["tag1", "tag2"] or null,
  "policy_sources": ["filename.txt"] or null,
  "k_results": 5
}}

Be strategic:
- Use 1-2 most relevant tags maximum (not all possible tags)
- Only specify policy sources if question is about a specific plan
"""
    
    response = llm.invoke(planning_prompt)
    
    # Parse JSON response
    try:
        # Extract JSON from response (might be wrapped in markdown)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        plan = json.loads(content)
        return plan
    except Exception as e:
        print(f"Error parsing plan: {e}")
        print(f"Raw response: {response.content}")
        # Fallback plan
        return {
            "doc_types": ["both"],
            "transcript_tags": None,
            "policy_sources": None,
            "k_results": 5
        }


def execute_retrieval(query, plan):
    """
    Step 2: Execute retrieval based on the LLM's plan.
    """
    results = []
    doc_types = plan.get("doc_types", ["both"])
    k = plan.get("k_results", 5)
    
    # Handle different doc_type strategies
    if "transcript" in doc_types or "both" in doc_types:
        # Retrieve transcripts
        tags = plan.get("transcript_tags")
        transcript_results = retrieve_transcripts(query, tags=tags, k=k)
        results.append(transcript_results)
    
    if "policy" in doc_types or "both" in doc_types:
        # Retrieve policies
        sources = plan.get("policy_sources")
        
        if sources:
            # Retrieve from specific sources
            for source in sources:
                policy_results = retrieve_policies(query, k=k, source=source)
                results.append(policy_results)
        else:
            # Retrieve from all policies
            policy_results = retrieve_policies(query, k=k)
            results.append(policy_results)
    
    # Combine all results
    combined = {
        'query': query,
        'chunks': [],
        'metadata': [],
        'scores': None
    }
    
    for result in results:
        combined['chunks'].extend(result['chunks'])
        combined['metadata'].extend(result['metadata'])
    
    return combined


def generate_answer(query, retrieval_result, plan):
    """
    Step 3: Generate final answer using retrieved context.
    """
    if not retrieval_result['chunks']:
        return "No relevant information found.", None
    
    # Build context from retrieved chunks
    context_parts = []
    for i, (chunk, meta) in enumerate(zip(retrieval_result['chunks'], retrieval_result['metadata']), 1):
        source = meta.get('source', 'Unknown')
        doc_type = meta.get('doc_type', 'unknown')
        tags = meta.get('tags', [])
        
        context_parts.append(f"[Source {i}: {source} ({doc_type}){' - Tags: ' + ', '.join(tags) if tags else ''}]")
        context_parts.append(chunk)
        context_parts.append("")
    
    context = "\n".join(context_parts)
    
    # Create answer prompt
    answer_prompt = f"""You are a helpful assistant analyzing Boston community data.

Answer the question in 2-3 concise paragraphs. Be conversational and direct.
- Cite key sources [Source X]
- Focus on the most important points
- Keep it brief and clear

SOURCES:
{context}

QUESTION: {query}

ANSWER (2-3 paragraphs max):"""
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    response = llm.invoke(answer_prompt)
    
    return response.content, context_parts


def two_step_rag(query, verbose=True):
    """
    Complete two-step RAG pipeline.
    
    Args:
        query: User's question
        verbose: Whether to show intermediate steps
    """
    print(f"\n{'='*80}")
    print(f"QUESTION: {query}")
    print(f"{'='*80}\n")
    
    # Step 1: Plan retrieval
    if verbose:
        print("🧠 STEP 1: Planning retrieval strategy...")
    
    plan = plan_retrieval(query)
    
    if verbose:
        print(f"\nRetrieval Plan:")
        print(f"  Doc Types: {plan.get('doc_types')}")
        print(f"  Transcript Tags: {plan.get('transcript_tags')}")
        print(f"  Policy Sources: {plan.get('policy_sources')}")
        print(f"  Results to retrieve: {plan.get('k_results')}")
    
    # Step 2: Execute retrieval
    if verbose:
        print(f"\n🔍 STEP 2: Retrieving relevant documents...")
    
    results = execute_retrieval(query, plan)
    
    if verbose:
        print(f"\nRetrieved {len(results['chunks'])} chunks:")
        for i, meta in enumerate(results['metadata'], 1):
            doc_type = meta.get('doc_type', 'unknown')
            source = meta.get('source', 'Unknown')
            tags = meta.get('tags', '')  # Tags are stored as string
            print(f"  {i}. [{doc_type}] {source}{' (' + tags + ')' if tags else ''}")
    
    # Step 3: Generate answer
    if verbose:
        print(f"\n✨ STEP 3: Generating answer...")
    
    answer, context = generate_answer(query, results, plan)
    
    if verbose:
        print(f"\n{'='*80}")
    print(f"\nANSWER:\n{answer}")
    print(f"\n{'='*80}\n")
    
    return {
        'query': query,
        'plan': plan,
        'retrieval': results,
        'answer': answer
    }


def demo_1():
    """Demo: Media representation question"""
    print("\n🎯 DEMO 1: Community Perspectives on Media")
    print("-" * 80)
    
    query = "How do community members describe media representation of their neighborhoods?"
    two_step_rag(query, verbose=True)


def demo_2():
    """Demo: Policy question"""
    print("\n🎯 DEMO 2: Housing Policy Strategies")
    print("-" * 80)
    
    query = "What strategies does Boston have for preventing displacement and ensuring affordable housing?"
    two_step_rag(query, verbose=True)


def demo_3():
    """Demo: Compare policy vs sentiment"""
    print("\n🎯 DEMO 3: Safety - Policy vs Community Concerns")
    print("-" * 80)
    
    query = "What do community members say about safety, and how do city policies address these concerns?"
    two_step_rag(query, verbose=True)


def demo_4():
    """Demo: Complex multi-faceted question"""
    print("\n🎯 DEMO 4: Complex Query - Youth and Violence")
    print("-" * 80)
    
    query = "What are the perspectives on youth involvement in violence, and what solutions do people suggest?"
    two_step_rag(query, verbose=True)


def demo_interactive():
    """Interactive demo"""
    print("\n🎯 INTERACTIVE DEMO")
    print("-" * 80)
    
    query = input("\nEnter your question: ").strip()
    if not query:
        query = "What do people say about gentrification in Boston?"
        print(f"Using default: {query}")
    
    verbose = input("\nShow detailed steps? (y/n, default=y): ").strip().lower() != 'n'
    
    two_step_rag(query, verbose=verbose)


def main():
    """Run demos"""
    print("\n" + "="*80)
    print(" TWO-STEP AGENTIC RAG DEMO")
    print(" Step 1: LLM plans retrieval → Step 2: Execute → Step 3: Generate answer")
    print("="*80)
    
    print("\nDemo scenarios:")
    print("  1. Media representation (transcripts)")
    print("  2. Housing policy (policy docs)")
    print("  3. Safety (mixed)")
    print("  4. Complex multi-faceted query")
    print("  5. Interactive - your own question")
    print("  6. Run all demos")
    
    choice = input("\nSelect demo (1-6, default=1): ").strip() or "1"
    
    if choice == "1":
        demo_1()
    elif choice == "2":
        demo_2()
    elif choice == "3":
        demo_3()
    elif choice == "4":
        demo_4()
    elif choice == "5":
        demo_interactive()
    elif choice == "6":
        demo_1()
        demo_2()
        demo_3()
        
        more = input("\nContinue with demo 4? (y/n): ").strip().lower()
        if more == 'y':
            demo_4()
        
        interactive = input("\nTry interactive demo? (y/n): ").strip().lower()
        if interactive == 'y':
            demo_interactive()
    
    print("\n" + "="*80)
    print("Demo complete! ✨")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
