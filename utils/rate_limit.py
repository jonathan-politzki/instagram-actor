import time
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

# Store timestamps of last API calls
LAST_API_CALL: Dict[str, float] = {}

# Default minimum delays for different API endpoints
DEFAULT_DELAYS = {
    "instagram_profile": 2.0,    # Profile data
    "instagram_posts": 2.0,      # Posts data
    "instagram_comments": 3.0,   # Comments data
    "instagram_hashtags": 5.0,   # Hashtag search (higher delay)
    "profile_check": 1.0,        # Profile visibility check
    "profile_posts_check": 2.0,  # Additional profile posts check
    "default": 1.0               # Default for any other API endpoint
}

async def rate_limit(api_name: str, min_delay_seconds: Optional[float] = None):
    """
    Implement rate limiting for API calls to prevent hitting rate limits
    
    Args:
        api_name: Name of the API endpoint being called
        min_delay_seconds: Minimum delay in seconds between calls (overrides default)
    """
    now = time.time()
    last_call = LAST_API_CALL.get(api_name, 0)
    elapsed = now - last_call
    
    # Use provided delay or get from defaults
    if min_delay_seconds is None:
        min_delay_seconds = DEFAULT_DELAYS.get(api_name, DEFAULT_DELAYS["default"])
    
    if elapsed < min_delay_seconds:
        delay = min_delay_seconds - elapsed
        print(f"Rate limiting: waiting {delay:.2f}s for {api_name} API")
        await asyncio.sleep(delay)
    
    # Update last call time
    LAST_API_CALL[api_name] = time.time()

def log_api_call(api_name: str, success: bool = True, details: Dict[str, Any] = None) -> None:
    """
    Log API call for monitoring and debugging (optional)
    
    Args:
        api_name: Name of the API endpoint called
        success: Whether the call was successful
        details: Additional details about the call
    """
    # This function can be expanded to log to a file or monitoring service
    timestamp = datetime.now().isoformat()
    status = "SUCCESS" if success else "FAILURE"
    details_str = str(details) if details else ""
    
    print(f"[{timestamp}] {api_name} - {status} {details_str}")

# Context manager for rate-limited code blocks (synchronous version)
class RateLimited:
    def __init__(self, api_name: str, min_delay_seconds: Optional[float] = None):
        self.api_name = api_name
        self.min_delay_seconds = min_delay_seconds
        
    def __enter__(self):
        now = time.time()
        last_call = LAST_API_CALL.get(self.api_name, 0)
        elapsed = now - last_call
        
        # Use provided delay or get from defaults
        if self.min_delay_seconds is None:
            min_delay_seconds = DEFAULT_DELAYS.get(self.api_name, DEFAULT_DELAYS["default"])
        else:
            min_delay_seconds = self.min_delay_seconds
        
        if elapsed < min_delay_seconds:
            delay = min_delay_seconds - elapsed
            print(f"Rate limiting: waiting {delay:.2f}s for {self.api_name} API")
            time.sleep(delay)
        
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Update last call time
        LAST_API_CALL[self.api_name] = time.time()
        
        # Log error if there was one
        if exc_type:
            log_api_call(self.api_name, success=False, details={"error": str(exc_val)}) 