# main.py
import asyncio
import os
import shutil
import json
import time  # <--- ADD THIS CRUCIAL IMPORT TO FIX THE 500 CRASH
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from ingest import ingest_pdf_pipeline
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request

app = FastAPI(title="Agentic Auditor API", version="1.0.0")

# Enable CORS for frontend frameworks (Astro / Tailwind)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production Vercel frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenBucketLimiter(BaseHTTPMiddleware):
    def __init__(self, app, max_tokens: int = 5, replenish_rate: float = 30.0):
        """
        max_tokens: Maximum capacity of the user's bucket.
        replenish_rate: Time in seconds required to regenerate exactly 1 token.
        """
        super().__init__(app)
        self.max_tokens = max_tokens
        self.replenish_rate = replenish_rate
        # In-memory matrix tracking structural rate states per IP address
        self.buckets: Dict[str, Dict[str, float]] = {}

    def _get_updated_tokens(self, ip: str) -> float:
        current_time = time.time()
        
        # Initialize an explicit bucket instance if this is a newly discovered IP
        if ip not in self.buckets:
            self.buckets[ip] = {
                "tokens": float(self.max_tokens),
                "last_update": current_time
            }
            return float(self.max_tokens)
            
        bucket = self.buckets[ip]
        elapsed = current_time - bucket["last_update"]
        
        # Calculate how many tokens regenerated during the time window
        regenerated = elapsed / self.replenish_rate
        new_tokens = min(float(self.max_tokens), bucket["tokens"] + regenerated)
        
        # Update state tracking variables
        bucket["tokens"] = new_tokens
        bucket["last_update"] = current_time
        return new_tokens

    async def dispatch(self, request: Request, call_next):
        # Apply strict checking conditions solely to downstream resource-heavy mutation routes
        if request.url.path in ["/api/chat", "/api/upload"]:
            # Isolate connection string headers
            client_ip = request.client.host if request.client else "unknown_node"
            available_tokens = self._get_updated_tokens(client_ip)
            
            if available_tokens < 1.0:
                # Calculate required cool-down wait parameter to return to the client
                retry_after = int(self.replenish_rate * (1.0 - available_tokens))
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "RATE_LIMIT_EXCEEDED",
                        "message": f"Resource threshold breached. Backoff cool-down required: {retry_after}s."
                    },
                    headers={"Retry-After": str(retry_after)}
                )
                
            # Consume exactly one execution token for this request cycle
            self.buckets[client_ip]["tokens"] -= 1.0
            
        return await call_next(request)

# Register the architectural rate-limiting layer right underneath your CORS configuration
app.add_middleware(TokenBucketLimiter, max_tokens=5, replenish_rate=30.0)

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
    Orchestrates the chat experience via our LangGraph supervisor router 
    and streams tokens back to the frontend in real-time.
    """
    # 1. Formatting History
    formatted_history = [{"role": msg.role, "content": msg.content} for msg in payload.history]
    query = payload.query.lower()
    
    # 2. Extract Routing Metadata to notify UI Telemetry immediately
    is_broad_legal = any(x in query for x in ["global", "standard", "tax", "search", "web"])
    route_badge = "TRACE // WAN_FALLBACK" if is_broad_legal else "TRACE // LCL_VECTOR_ISOLATION"

    # 3. Define Async Stream Generator Channel
    
    async def event_generator():
        try:
            # Drop the tracking badge event instantly so the routing matrix lights up
            yield f"data: {json.dumps({'type': 'metadata', 'badge': route_badge})}\n\n"
            await asyncio.sleep(0.1) # Shorter snappy latency check
            
            # Iterate asynchronously through the live LangGraph emission tokens
            from app.graph import run_agent_stream
            
            async for chunk in run_agent_stream(query=payload.query, chat_history=formatted_history):
                # If it's a token block, stream it straight to the frontend canvas
                if chunk["type"] == "token":
                    yield f"data: {json.dumps({'type': 'content', 'token': chunk['content']})}\n\n"
                
                # If a tool starts up, you can optionally flash a runtime trace status message
                elif chunk["type"] == "tool_start":
                    # Updates telemetry path text dynamically if the agent requests a RAG lookup
                    if chunk["tool"] == "query_contract_segments":
                        yield f"data: {json.dumps({'type': 'metadata', 'badge': 'TRACE // EXECUTING_RAG_TOOL'})}\n\n"
                    elif chunk["tool"] == "web_legal_search":
                        yield f"data: {json.dumps({'type': 'metadata', 'badge': 'TRACE // EXECUTING_WAN_SEARCH'})}\n\n"
                
        except asyncio.CancelledError:
            print("System Event: Connection closed by client interface.")
        except Exception as err:
            yield f"data: {json.dumps({'type': 'content', 'token': f' [Runtime Error: {str(err)}]'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
    

# Health check root endpoint for easy service validation
@app.get("/")
def read_root():
    return {"status": "online", "engine": "Agentic Auditor Multi-Agent RAG v1"}