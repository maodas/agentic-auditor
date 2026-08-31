import os
import json
from typing import Any, Dict
from langchain_unstructured import UnstructuredLoader
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from supabase.client import create_client
from dotenv import load_dotenv

load_dotenv()

def validate_and_extract_sections(full_text: str) -> Dict[str, Any]:
    """
    Evaluates document structural liability bounds using a foundational model LLM 
    to extract isolated sections and run a compliance validation filter.
    """
    llm = ChatGroq(
        model="qwen/qwen3.6-27b", 
        temperature=0,
        model_kwargs={"response_format": {"type": "json_object"}}
    )
    
    prompt = f"""
    Analyze the following snippet of an uploaded document.
    
    CRITICAL CLASSIFICATION BOUNDARIES:
    1. The document MUST be a legally binding, fully executed legal contract, agreement, corporate policy, corporate charter, or formal statutory regulation to pass (is_legal_contract = true).
    2. You MUST fail/reject the document (is_legal_contract = false) if it is a commercial proposal, technical proposal, marketing/sales pitch, commercial quotation, resume/CV, project report, or a Statement of Work (SOW) that focuses primarily on engineering/business deliverables rather than binding legal liability.
    3. Even if a technical proposal contains minor boilerplate legal rows (like confidentiality or a short copyright notice), it is still classified as a PROPOSAL, and you MUST reject it.

    Identify up to 3 main operational or business themes if it passes validation (e.g., Payment, Liability, Support Staff, Notices, Termination).
    
    Respond STRICTLY in JSON format with no extra conversational text or markdown code block wrapping:
    {{
        "is_legal_contract": false,
        "reason": "Specify exactly why the document was accepted or rejected.",
        "detected_sections": []
    }}
    
    Document snippet text:
    {full_text[:3000]}
    """
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        parsed = json.loads(content)
        
        is_legal = parsed.get("is_legal_contract", parsed.get("is_legal", False))
        reason = parsed.get("reason", parsed.get("reasoning", "Document rejected: Not an auditable legal agreement."))
        sections = parsed.get("detected_sections", parsed.get("sections", []))
        
        return {
            "is_legal_contract": bool(is_legal),
            "reason": str(reason),
            "detected_sections": sections if isinstance(sections, list) else []
        }
    except Exception as e:
        print(f"Error during structural classification pipeline parsing: {str(e)}")
        return {
            "is_legal_contract": False,
            "reason": f"Classification parsing failure: {str(e)}",
            "detected_sections": []
        }

def ingest_pdf_pipeline(file_path: str) -> Dict[str, Any]:
    """
    Orchestrates the serverless partitioning pipeline, generating vector embeddings 
    and loading chunk contents directly to remote Supabase tables.
    """
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
    
    if not analysis.get("is_legal_contract", False):
        return {
            "success": False, 
            "error": f"Document rejected. Reason: {analysis.get('reason', 'Not an auditable legal agreement.')}"
        }
        
    sections = analysis.get("detected_sections", ["General"])
    if not sections:
        sections = ["General"]
        
    print(f"Verification Passed. Detected Sections: {sections}")
    
    for doc in docs:
        doc.metadata["filename"] = os.path.basename(file_path)
        doc.metadata["discovered_sections"] = sections
        
        text_lower = doc.page_content.lower()
        matched_section = "general"
        for section in sections:
            if section.lower() in text_lower:
                matched_section = section.lower()
                break
        doc.metadata["section"] = matched_section

    embedding_model = HuggingFaceEndpointEmbeddings(
        model="sentence-transformers/all-MiniLM-L6-v2",
        provider="hf-inference",
        huggingfacehub_api_token=os.environ.get("HF_TOKEN")
    )
    SupabaseVectorStore.from_documents(docs, embedding_model, client=supabase, table_name="documents")
    
    return {
        "success": True,
        "message": "Pipeline Complete",
        "sections": sections
    }