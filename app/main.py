# main.py
import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from ingest import ingest_pdf_pipeline
from app.graph import run_agent

app = FastAPI(title="Agentic Auditor API", version="1.0.0")

# Enable CORS for frontend frameworks (Astro / Tailwind)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production Vercel frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    query: str
    history: Optional[List[ChatMessage]] = []

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Handles PDF uploading, checks file extensions, routes to the high-res cloud loader,
    and returns dynamically discovered contract sections.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF legal documents are supported.")
    
    # Secure serverless local temp path
    temp_dir = "/tmp"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    try:
        # Stream raw file bytes to disk temporarily
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Execute the validation and dynamic metadata enrichment pipeline
        pipeline_result = ingest_pdf_pipeline(temp_file_path)
        
        if not pipeline_result.get("success"):
            raise HTTPException(status_code=422, detail=pipeline_result.get("error"))
            
        return {
            "status": "success",
            "filename": file.filename,
            "detected_sections": pipeline_result.get("sections")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal ingestion failure: {str(e)}")
        
    finally:
        # Ensure stateless cleanup to respect serverless memory ceilings
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    """
    Orchestrates the chat experience via our LangGraph supervisor router.
    """
    try:
        # Convert Pydantic history into the dictionary structure expected by the backend agent
        formatted_history = [{"role": msg.role, "content": msg.content} for msg in payload.history]
        
        response_content = run_agent(query=payload.query, chat_history=formatted_history)
        return {"response": response_content}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent orchestration error: {str(e)}")

# Health check root endpoint for easy service validation
@app.get("/")
def read_root():
    return {"status": "online", "engine": "Agentic Auditor Multi-Agent RAG v1"}