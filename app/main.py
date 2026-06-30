import asyncio
import os
import shutil
import json
import time  
import redis.asyncio as aioredis  
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from ingest import ingest_pdf_pipeline
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request
from app.graph import run_agent_stream

app = FastAPI(title="Agentic Auditor API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenBucketLimiter(BaseHTTPMiddleware):
    def __init__(self, app, max_tokens: int = 5, replenish_rate: float = 30.0):
        super().__init__(app)
        self.max_tokens = max_tokens
        self.replenish_rate = replenish_rate
        self.fallback_buckets: Dict[str, Dict[str, float]] = {}
        self.use_redis = True
        
        try:
            redis_host = os.environ.get("REDIS_HOST", "redis")
            self.redis = aioredis.from_url(
                f"redis://{redis_host}:6379", 
                decode_responses=True,
                socket_connect_timeout=2.0 
            )
        except Exception:
            self.use_redis = False

    async def _get_updated_tokens(self, ip: str) -> float:
        current_time = time.time()
        
        if self.use_redis:
            try:
                key = f"ratelimit:{ip}"
                data = await self.redis.hgetall(key)
                if not data:
                    await self.redis.hset(key, mapping={"tokens": float(self.max_tokens), "last_update": current_time})
                    await self.redis.expire(key, 86400)
                    return float(self.max_tokens)
                
                old_tokens = float(data["tokens"])
                last_update = float(data["last_update"])
                elapsed = current_time - last_update
                new_tokens = min(float(self.max_tokens), old_tokens + (elapsed / self.replenish_rate))
                
                await self.redis.hset(key, mapping={"tokens": new_tokens, "last_update": current_time})
                return new_tokens
            except Exception:
                self.use_redis = False

        if ip not in self.fallback_buckets:
            self.fallback_buckets[ip] = {"tokens": float(self.max_tokens), "last_update": current_time}
            return float(self.max_tokens)
            
        bucket = self.fallback_buckets[ip]
        elapsed = current_time - bucket["last_update"]
        new_tokens = min(float(self.max_tokens), bucket["tokens"] + (elapsed / self.replenish_rate))
        bucket["tokens"] = new_tokens
        bucket["last_update"] = current_time
        return new_tokens

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/api/chat", "/api/upload"]:
            client_ip = request.client.host if request.client else "unknown_node"
            available_tokens = await self._get_updated_tokens(client_ip)
            
            if available_tokens < 1.0:
                retry_after = int(self.replenish_rate * (1.0 - available_tokens))
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "RATE_LIMIT_EXCEEDED",
                        "message": f"Resource threshold breached. Backoff cool-down required: {retry_after}s."
                    },
                    headers={"Retry-After": str(retry_after)}
                )
                
            if self.use_redis:
                try:
                    await self.redis.hincrbyfloat(f"ratelimit:{client_ip}", "tokens", -1.0)
                except Exception:
                    self.use_redis = False
                    if client_ip not in self.fallback_buckets:
                        self.fallback_buckets[client_ip] = {"tokens": available_tokens, "last_update": time.time()}
                    self.fallback_buckets[client_ip]["tokens"] -= 1.0
            else:
                if client_ip not in self.fallback_buckets:
                    self.fallback_buckets[client_ip] = {"tokens": available_tokens, "last_update": time.time()}
                self.fallback_buckets[client_ip]["tokens"] -= 1.0
            
        return await call_next(request)
    
app.add_middleware(TokenBucketLimiter, max_tokens=5, replenish_rate=30.0)

class ChatMessage(BaseModel):
    role: str  
    content: str

class ChatRequest(BaseModel):
    query: str
    history: Optional[List[ChatMessage]] = []

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF legal documents are supported.")
    
    temp_dir = "/tmp"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        pipeline_result = ingest_pdf_pipeline(temp_file_path)
        
        if not pipeline_result.get("success"):
            raise HTTPException(status_code=422, detail=pipeline_result.get("error"))
            
        return {
            "status": "success",
            "filename": file.filename,
            "detected_sections": pipeline_result.get("sections")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Ingestion Failure: {str(e)}")
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    formatted_history = [{"role": msg.role, "content": msg.content} for msg in payload.history]
    query = payload.query.lower()
    
    is_broad_legal = any(x in query for x in ["global", "standard", "tax", "search", "web"])
    route_badge = "TRACE // WAN_FALLBACK" if is_broad_legal else "TRACE // LCL_VECTOR_ISOLATION"

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'metadata', 'badge': route_badge})}\n\n"
            await asyncio.sleep(0.05) 
            
            async for chunk in run_agent_stream(query=payload.query, chat_history=formatted_history):
                if chunk["type"] == "token":
                    yield f"data: {json.dumps({'type': 'content', 'token': chunk['content']})}\n\n"
                elif chunk["type"] == "tool_start":
                    if chunk["tool"] == "query_contract_segments":
                        yield f"data: {json.dumps({'type': 'metadata', 'badge': 'TRACE // EXECUTING_RAG_TOOL'})}\n\n"
                    elif chunk["tool"] == "web_legal_search":
                        yield f"data: {json.dumps({'type': 'metadata', 'badge': 'TRACE // EXECUTING_WAN_SEARCH'})}\n\n"
                
        except asyncio.CancelledError:
            pass
        except Exception as err:
            yield f"data: {json.dumps({'type': 'content', 'token': f' [Runtime Error: {str(err)}]'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/")
def read_root():
    return {"status": "online", "engine": "Agentic Auditor Multi-Agent RAG v1"}