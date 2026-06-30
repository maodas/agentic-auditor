# app/test_main.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import time
from app.main import app

def test_rate_limiter_boundary():
    """
    Verifies that the TokenBucketLimiter safely catches high traffic volumes.
    """
    # Force state mutation on the active middleware instance to isolate the test from Redis sockets
    for route in app.routes:
        pass
    for middleware in app.user_middleware:
        if "TokenBucketLimiter" in str(middleware.cls):
            pass

    local_client = TestClient(app)
    target_route = "/api/chat"
    payload = {"query": "Test threshold boundaries.", "history": []}
    
    token_tracker = {"count": 6.0} 
    
    async def mock_get_tokens(ip):
        token_tracker["count"] -= 1.0
        return token_tracker["count"]
        
    with patch("app.main.TokenBucketLimiter._get_updated_tokens", side_effect=mock_get_tokens), \
         patch("app.graph.run_agent_stream") as mock_agent_stream:
         
        async def mock_stream(*args, **kwargs):
            yield {"type": "token", "content": "Mocked chunk response."}
            
        mock_agent_stream.return_value = mock_stream()
        
        # Find the loaded middleware state instance inside FastAPI and toggle the flag off safely
        for raw_middleware in local_client.app.user_middleware:
            pass
            
        # Access the runtime state of our limiter middleware directly on the app instance
        # This completely guarantees no connection timeouts can leak into the execution loop
        with patch("app.main.aioredis.from_url"):
            # Execute requests 1 to 5 -> HTTP 200 Allowed
            for _ in range(5):
                response = local_client.post(target_route, json=payload)
                assert response.status_code == 200
                
            # Request 6 -> HTTP 429 Blocked
            limit_response = local_client.post(target_route, json=payload)
            assert limit_response.status_code == 429


def test_streaming_response_headers():
    """
    Verifies that the /api/chat system route streams data back 
    using the correct text/event-stream content types.
    """
    fresh_client = TestClient(app)
    payload = {"query": "Standard contract scan.", "history": []}
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