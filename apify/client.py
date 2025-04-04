import os
from typing import Dict, Any
from dotenv import load_dotenv
from apify_client import ApifyClient

# Load environment variables
load_dotenv()

# Configure API keys
APIFY_API_KEY = os.getenv("APIFY_API_KEY")

# Initialize Apify client
apify_client = ApifyClient(APIFY_API_KEY)

# Create directories for cache and results
os.makedirs("cache", exist_ok=True)
os.makedirs("results", exist_ok=True)

def get_client() -> ApifyClient:
    """
    Returns the configured Apify client
    """
    if not APIFY_API_KEY:
        raise ValueError("APIFY_API_KEY environment variable is not set")
    return apify_client

def run_actor(actor_id: str, run_input: Dict[str, Any], timeout_secs: int = 120) -> Dict[str, Any]:
    """
    Helper function to run an Apify actor with error handling
    
    Args:
        actor_id: The ID of the Apify actor to run
        run_input: The input for the actor
        timeout_secs: Maximum runtime in seconds
        
    Returns:
        Dictionary with the actor run results
    """
    try:
        client = get_client()
        run = client.actor(actor_id).call(run_input=run_input, timeout_secs=timeout_secs)
        return run
    except Exception as e:
        raise Exception(f"Error running Apify actor {actor_id}: {str(e)}")

def get_actor_results(dataset_id: str) -> list:
    """
    Helper function to get results from an actor run
    
    Args:
        dataset_id: The ID of the dataset to get results from
        
    Returns:
        List of results from the actor run
    """
    try:
        client = get_client()
        items = list(client.dataset(dataset_id).iterate_items())
        return items
    except Exception as e:
        raise Exception(f"Error getting results from dataset {dataset_id}: {str(e)}") 