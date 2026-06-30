import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import create_client
from dotenv import load_dotenv
from duckduckgo_search import DDGS

load_dotenv()

supabase_client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY"))

embedding_model = HuggingFaceInferenceAPIEmbeddings(
    api_key=os.environ.get("HF_TOKEN"),
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

class DynamicLegalQuerySchema(BaseModel):
    query: str = Field(description="The specific question or clause to search for.")
    section: str = Field(
        default="general", 
        description="The targeted section name identified during ingestion (e.g., 'payment', 'termination', 'exportation', or 'general')."
    )

def get_rag_retriever(section_filter=None):
    vector_store = SupabaseVectorStore(
        client=supabase_client,
        embedding=embedding_model,
        table_name="documents",
        query_name="match_documents"
    )
    
    search_kwargs = {"k": 5}
    if section_filter and section_filter.lower() != "general":
        search_kwargs["filter"] = {"section": section_filter.lower()}
        
    return vector_store.as_retriever(search_kwargs=search_kwargs)

@tool("query_contract_segments", args_schema=DynamicLegalQuerySchema)
def query_contract_segments(query: str, section: str = "general") -> str:
    """
    Queries the vector database for a specific section of the document using metadata filters.
    Use this tool whenever the question is about the uploaded document.
    """
    retriever = get_rag_retriever(section_filter=section)
    docs = retriever.invoke(query)
    
    if not docs:
        retriever_fallback = get_rag_retriever(section_filter="general")
        docs = retriever_fallback.invoke(query)
        
    return f"--- Context isolated from section [{section}] ---\n\n" + "\n\n".join([d.page_content for d in docs])

@tool("web_legal_search")
def web_legal_search(query: str) -> str:
    """
    Searches the internet for general legal concepts, definitions, regulations, or jurisdictions 
    that are outside the scope of the uploaded document. Use this only when the question cannot 
    be answered by the document itself.
    """
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
            
        if not results:
            return "No external legal search results found."
            
        formatted_results = []
        for i, r in enumerate(results, 1):
            formatted_results.append(f"Result {i}:\nTitle: {r.get('title')}\nSnippet: {r.get('body')}\n")
            
        return "\n".join(formatted_results)
        
    except Exception as e:
        return f"External web search failed due to a network or structural timeout: {str(e)}"