import os
import json
from langchain_unstructured import UnstructuredLoader
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from supabase.client import create_client
from dotenv import load_dotenv

load_dotenv()

def validate_and_extract_sections(full_text: str):
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    
    prompt = f"""
    Analyze the following snippet of an uploaded document.
    
    CRITICAL CLASSIFICATION BOUNDARIES:
    1. The document MUST be a legally binding, fully executed legal contract, agreement, corporate policy, corporate charter, or formal statutory regulation to pass.
    2. You MUST fail/reject the document (is_legal = false) if it is a commercial proposal, technical proposal, marketing/sales pitch, commercial quotation, resume/CV, project report, or a Statement of Work (SOW) that focuses primarily on engineering/business deliverables rather than binding legal liability.
    3. Even if a technical proposal contains minor boilerplate legal rows (like confidentiality or a short copyright notice), it is still classified as a PROPOSAL, and you MUST reject it.

    Identify up to 3 main operational or business themes if it passes validation (e.g., Payment, Liability, Support Staff, Notices, Termination).
    
    Respond STRICTLY in the following raw JSON format, with no extra conversational text or markdown code block wrapping:
    {{
        "is_legal": false,
        "reasoning": "Specify exactly why the document was rejected.",
        "sections": []
    }}
    
    Document snippet text:
    {full_text[:3000]}
    """
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        clean_content = response.content.strip().lstrip("```json").rstrip("```")
        result = json.loads(clean_content)
        return result
    except Exception as e:
        print(f"Error during structural classification: {e}")
        return {"is_legal": True, "reasoning": "Fallback extraction", "sections": ["General", "Terms"]}

def ingest_pdf_pipeline(file_path: str):
    supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY"))
    
    print(f"Executing Serverless Partitioning via Unstructured API for: {os.path.basename(file_path)}")
    
    loader = UnstructuredLoader(
        file_path=file_path,
        partition_via_api=True,
        api_key=os.environ.get("UNSTRUCTURED_API_KEY"),
        strategy="hi_res"
    )
    docs = loader.load()
    
    full_text = " ".join([d.page_content for d in docs])
    analysis = validate_and_extract_sections(full_text)
    
    if not analysis.get("is_legal", False):
        return {
            "success": False, 
            "error": f"Document rejected. Reason: {analysis.get('reasoning')}"
        }
        
    print(f"Verification Passed. Detected Sections: {analysis['sections']}")
    
    for doc in docs:
        doc.metadata["filename"] = os.path.basename(file_path)
        doc.metadata["discovered_sections"] = analysis["sections"]
        
        text_lower = doc.page_content.lower()
        matched_section = "general"
        for section in analysis["sections"]:
            if section.lower() in text_lower:
                matched_section = section.lower()
                break
        doc.metadata["section"] = matched_section

    embedding_model = HuggingFaceInferenceAPIEmbeddings(
        api_key=os.environ.get("HF_TOKEN"),
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    SupabaseVectorStore.from_documents(docs, embedding_model, client=supabase, table_name="documents")
    
    return {
        "success": True,
        "message": "Pipeline Complete",
        "sections": analysis["sections"]
    }