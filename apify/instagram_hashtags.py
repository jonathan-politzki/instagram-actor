from typing import Dict, List, Any

from utils.rate_limit import rate_limit
from utils.cache import cached
from apify.client import run_actor, get_actor_results

@cached(max_age_days=1)
async def collect_hashtag_posts(hashtag: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Collect posts for a specific hashtag
    
    Args:
        hashtag: Hashtag to collect posts for (without the # symbol)
        limit: Maximum number of posts to collect
        
    Returns:
        List of posts associated with the hashtag
    """
    print(f"Collecting posts for hashtag #{hashtag}")
    
    try:
        # Apply rate limiting - longer delay for hashtag searches
        await rate_limit("instagram_hashtags")
        
        # Call the hashtag scraper
        run_input = {
            "hashtags": [hashtag],
            "resultsLimit": limit
        }
        
        run = run_actor("apify/instagram-hashtag-scraper", run_input, timeout_secs=60)
        hashtag_data = get_actor_results(run["defaultDatasetId"])
        
        return hashtag_data
    
    except Exception as e:
        print(f"Error collecting hashtag posts for #{hashtag}: {str(e)}")
        return [] 