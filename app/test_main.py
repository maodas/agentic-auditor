import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import time
from app.main import app

def test_rate_limiter_boundary():
    """
    Simulates resource abuse by firing consecutive requests rapidly 
    to verify that the TokenBucketLimiter throws an HTTP 429 response.
    """
    local_client = TestClient(app)
    target_route = "/api/chat"
    payload = {"query": "Test threshold boundaries.", "history": []}
    
    with patch("app.main.run_agent") as mock_agent:
        mock_agent.return_value = "Mocked instant agent response."
        
        # Drain the token bucket completely (Max capacity = 5 tokens)
        for _ in range(5):
            response = local_client.post(target_route, json=payload)
            assert response.status_code == 200
            
        # The 6th consecutive execution happens instantly and must trigger a 429
        limit_response = local_client.post(target_route, json=payload)
        
        assert limit_response.status_code == 429
        error_data = limit_response.json()
        assert error_data["error"] == "RATE_LIMIT_EXCEEDED"
        assert "Retry-After" in limit_response.headers


def test_streaming_response_headers():
    """
    Verifies that the /api/chat system route streams data back 
    using the correct text/event-stream content types.
    """
    fresh_client = TestClient(app)
    payload = {"query": "Standard local contract query sweep.", "history": []}
    
    # Fast-forward time by 1000 seconds to instantly replenish all tokens for this client IP
    future_time = time.time() + 1000.0
    
    with patch("app.main.run_agent") as mock_agent, \
         patch("time.time", return_value=future_time):
         
        mock_agent.return_value = "Mocked instant streaming response chunk."
        
        with fresh_client.stream("POST", "/api/chat", json=payload) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            
            first_line = next(response.iter_lines())
            assert first_line.startswith("data: ")