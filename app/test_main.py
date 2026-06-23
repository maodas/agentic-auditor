# app/test_main.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import time
from app.main import app


def test_streaming_response_headers():
    """
    Verifies that the /api/chat system route streams data back 
    using the correct text/event-stream content types.
    """
    fresh_client = TestClient(app)
    payload = {"query": "Standard local contract query sweep.", "history": []}
    
    # Fast-forward time by 1000 seconds to instantly replenish all tokens for this client IP
    future_time = time.time() + 1000.0
    
    with patch("app.graph.run_agent_stream") as mock_agent_stream, \
         patch("time.time", return_value=future_time):
         
        async def mock_stream(*args, **kwargs):
            yield {"type": "token", "content": "Mocked stream chunk."}
            
        mock_agent_stream.return_value = mock_stream()
        
        with fresh_client.stream("POST", "/api/chat", json=payload) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            
            first_line = next(response.iter_lines())
            assert first_line.startswith("data: ")

def test_rate_limiter_boundary():
    """
    Verifies that the TokenBucketLimiter safely catches high traffic volumes.
    """
    # Force the middleware to use our in-memory fallback map to bypass active Redis calls
    for middleware in app.user_middleware:
        if "TokenBucketLimiter" in str(middleware.cls):
            middleware.kwargs.get("app")
            
    local_client = TestClient(app)
    target_route = "/api/chat"
    payload = {"query": "Test threshold boundaries.", "history": []}
    
    with patch("app.graph.run_agent_stream") as mock_agent_stream, \
         patch("redis.asyncio.Redis.from_url") as mock_redis:
         
        # Disable Redis connection for local unit testing boundaries
        if hasattr(app.state, "redis"):
            delattr(app.state, "redis")
            
        async def mock_stream(*args, **kwargs):
            yield {"type": "token", "content": "Mocked instant token response."}
            
        mock_agent_stream.return_value = mock_stream()
        
        # Drain the token bucket completely (Max capacity = 5 tokens)
        for _ in range(5):
            response = local_client.post(target_route, json=payload)
            assert response.status_code == 200
            
        limit_response = local_client.post(target_route, json=payload)
        assert limit_response.status_code == 429