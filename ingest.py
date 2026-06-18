# ingest.py
import os
import json
from langchain_unstructured import UnstructuredLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from supabase.client import create_client
from dotenv import load_dotenv

load_dotenv()

def validate_and_extract_sections(full_text: str):
    """
    Uses a free lightweight model on Groq to validate the document type
    and dynamically discover its top 3 structural themes.
    """
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    
    prompt = f"""
    Analyze the following snippet of a document. 
    1. Determine if it is a legal document, agreement, contract, or corporate policy.
    2. Identify up to 3 main operational or business sections present in the document (e.g., Payment, Liability, Support Staff, Notices, Termination).
    
    Respond STRICTLY in the following raw JSON format:
    {{
        "is_legal": true,
        "reasoning": "Brief justification of document classification",
        "sections": ["SectionName1", "SectionName2", "SectionName3"]
    }}
    
    Document snippet:
    {full_text[:3000]}
    """
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        # Clean potential markdown wrapping from text
        clean_content = response.content.strip().lstrip("```json").rstrip("```")
        result = json.loads(clean_content)
        return result
    except Exception as e:
        print(f"Error during structural classification: {e}")
        return {"is_legal": True, "reasoning": "Fallback extraction", "sections": ["General", "Terms"]}

def ingest_pdf_pipeline(file_path: str):
    supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY"))
    
    print(f"Executing Serverless Partitioning via Unstructured API for: {os.path.basename(file_path)}")
    
    # By using partition_via_api=True, the heavy processing happens in the cloud.
    # The serverless dependency bundle stays extremely light (< 20MB) ensuring zero Vercel deployment issues.
    loader = UnstructuredLoader(
        file_path=file_path,
        partition_via_api=True,
        api_key=os.environ.get("UNSTRUCTURED_API_KEY"), # Get a free key from unstructured.io
        strategy="hi_res"
    )
    docs = loader.load()
    
    # Aggregate text for overall structural analysis
    full_text = " ".join([d.page_content for d in docs])
    analysis = validate_and_extract_sections(full_text)
    
    if not analysis.get("is_legal", False):
        return {
            "success": False, 
            "error": f"Document rejected. Reason: {analysis.get('reasoning')}"
        }
        
    print(f"Verification Passed. Detected Sections: {analysis['sections']}")
    
    # Dynamic metadata enrichment per chunk/page
    # We assign the sections discovered globally to help our virtual metadata filters map them later
    for doc in docs:
        doc.metadata["filename"] = os.path.basename(file_path)
        doc.metadata["discovered_sections"] = analysis["sections"]
        
        # Tag specifically if a chunk contains section terms to make the virtual routing highly accurate
        text_lower = doc.page_content.lower()
        matched_section = "general"
        for section in analysis["sections"]:
            if section.lower() in text_lower:
                matched_section = section.lower()
                break
        doc.metadata["section"] = matched_section

    # Vectorize and push to Supabase
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    SupabaseVectorStore.from_documents(docs, embeddings, client=supabase, table_name="documents")
    
    return {
        "success": True,
        "message": "Pipeline Complete",
        "sections": analysis["sections"]
    }

if __name__ == "__main__":
    # Test execution with your local demo file
    result = ingest_pdf_pipeline("sample_legal.pdf")
    print(result)