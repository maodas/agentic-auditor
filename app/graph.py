from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from app.tools.rag_tool import query_contract_segments, web_legal_search

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
tools = [query_contract_segments, web_legal_search]

SYSTEM_ORCHESTRATOR_PROMPT = """
You are a Senior Agentic Legal Auditor. Your primary function is to analyze uploaded corporate contracts, agreements, policies, and address broad legal jurisdictional queries.

SCOPE BOUNDARIES & GUARDRAILS:
1. ONLY answer queries related to corporate law, contract auditing, compliance, regulations, or legal concepts.
2. If a user asks for assistance with non-legal topics (e.g., career/CV writing advice, Excel formulas, data analysis tutorials, cooking recipes, or general lifestyle advice), you MUST politely refuse to answer, stating that it is outside your operational scope as a corporate legal auditor.
3. Be strictly factual. Do not apologize or state that you "cannot provide external results" when answering legal queries that fall under web search scope. Use your tools confidently.

GUIDE FOR TOOL SELECTION:
1. For document-specific lookups (payment terms, liabilities, termination), invoke `query_contract_segments`.
2. For general legal questions, definitions, or regional laws (such as starting a company in Guatemala), invoke `web_legal_search`. Summarize the tool's findings accurately.
"""

agent_executor = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_ORCHESTRATOR_PROMPT
)

async def run_agent_stream(query: str, chat_history: list = None):
    if chat_history is None:
        chat_history = []
        
    messages = chat_history + [{"role": "user", "content": query}]
    
    graph_config = {
        "configurable": {"thread_id": "auditor_session"},
        "recursion_limit": 50
    }
    
    async for event in agent_executor.astream_events({"messages": messages}, config=graph_config, version="v2"):
        event_type = event.get("event")
        
        if event_type == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                yield {"type": "token", "content": chunk.content}
                
        elif event_type == "on_tool_start":
            yield {"type": "tool_start", "tool": event.get("name")}