# app/graph.py
from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from app.tools.rag_tool import query_contract_segments, web_legal_search

# Using the powerful llama-3.3-70b-versatile model hosted on Groq (Serverless-optimized, ultra-low latency)
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
tools = [query_contract_segments, web_legal_search]

SYSTEM_ORCHESTRATOR_PROMPT = """
You are a Senior Agentic Legal Auditor. Your job is to answer the user's queries using the appropriate tools available to you.

GUIDE FOR TOOL SELECTION:
1. If the user's question relates directly to the uploaded contract or document (e.g., payment timelines, liabilities, breach terms), invoke `query_contract_segments`. Pass the specific segment name to the 'section' argument if the intent aligns with common sections like 'payment' or 'termination'.
2. If the user asks a broad legal question, jurisdictional regulation query, or external fact check not present in the document, invoke `web_legal_search`.

GUARDRAILS:
- Be strictly factual. Base contract responses solely on the returned snippets.
- If the document context does not contain the answer after a query, explicitly state that the specific terms are missing from the uploaded file.
- Do not make up legal terms. If searching the web, summarize public legal consensus accurately.
"""

agent_executor = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_ORCHESTRATOR_PROMPT
)

def run_agent(query: str, chat_history: list = None):
    if chat_history is None:
        chat_history = []
        
    messages = chat_history + [{"role": "user", "content": query}]
    result = agent_executor.invoke({"messages": messages})
    
    # Extract the last assistant response message
    return result["messages"][-1].content