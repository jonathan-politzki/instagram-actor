import os
import json
from typing import Dict, Any, Optional, Union, Callable
from datetime import datetime, timedelta
from functools import wraps

# Cache directory
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(cache_key: str) -> str:
    """
    Get the file path for a cache key
    
    Args:
        cache_key: The cache key to get the path for
        
    Returns:
        The file path for the cache key
    """
    return os.path.join(CACHE_DIR, f"{cache_key}.json")

def save_to_cache(cache_key: str, data: Dict[str, Any]) -> None:
    """
    Save data to the cache
    
    Args:
        cache_key: The key to store the data under
        data: The data to store
    """
    try:
        # Add timestamp to cache data
        cache_data = {
            "data": data,
            "cache_timestamp": datetime.now().isoformat()
        }
        
        # Save to cache file
        with open(get_cache_path(cache_key), 'w') as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"Error saving to cache: {str(e)}")

def load_from_cache(cache_key: str, max_age_days: int = 1) -> Optional[Dict[str, Any]]:
    """
    Load data from the cache if it exists and is not expired
    
    Args:
        cache_key: The key to load data for
        max_age_days: Maximum age of the cache in days
        
    Returns:
        The cached data, or None if no valid cache exists
    """
    cache_path = get_cache_path(cache_key)
    
    # Check if cache file exists
    if not os.path.exists(cache_path):
        return None
        
    try:
        # Load cache data
        with open(cache_path, 'r') as f:
            cached = json.load(f)
            
        # Check if cache has timestamp
        if "cache_timestamp" not in cached:
            return None
            
        # Check if cache is expired
        cache_time = datetime.fromisoformat(cached["cache_timestamp"])
        if (datetime.now() - cache_time) > timedelta(days=max_age_days):
            return None
            
        # Return cached data
        return cached.get("data")
    except Exception as e:
        print(f"Error loading from cache: {str(e)}")
        return None

def clear_cache(cache_key: Optional[str] = None) -> None:
    """
    Clear the cache
    
    Args:
        cache_key: Specific key to clear, or None to clear all
    """
    if cache_key:
        # Clear specific cache file
        cache_path = get_cache_path(cache_key)
        if os.path.exists(cache_path):
            os.remove(cache_path)
    else:
        # Clear all cache files
        for filename in os.listdir(CACHE_DIR):
            if filename.endswith(".json"):
                os.remove(os.path.join(CACHE_DIR, filename))

def cached(max_age_days: int = 1):
    """
    Decorator for caching function results
    
    Args:
        max_age_days: Maximum age of the cache in days
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and args
            cache_key = f"{func.__name__}_{hash(str(args) + str(kwargs))}"
            
            # Try to load from cache
            cached_data = load_from_cache(cache_key, max_age_days)
            if cached_data is not None:
                print(f"Using cached data for {func.__name__}")
                return cached_data
                
            # Call function
            result = await func(*args, **kwargs)
            
            # Save to cache
            save_to_cache(cache_key, result)
            
            return result
        return wrapper
    return decorator 