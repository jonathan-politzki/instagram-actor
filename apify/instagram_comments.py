from typing import Dict, List, Any

from utils.rate_limit import rate_limit
from utils.cache import cached
from apify.client import run_actor, get_actor_results

@cached(max_age_days=1)
async def collect_post_comments(post_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Collect comments for a specific Instagram post
    
    Args:
        post_id: The post ID or shortcode to collect comments for
        limit: Maximum number of comments to collect
        
    Returns:
        List of comments
    """
    print(f"Collecting comments for post {post_id}")
    
    try:
        # Apply rate limiting
        await rate_limit("instagram_comments")
        
        # Get comments for this post using the Instagram Comment Scraper
        run_input = {
            "directUrls": [f"https://www.instagram.com/p/{post_id}/"],
            "resultsLimit": limit
        }
        
        run = run_actor("apify/instagram-comment-scraper", run_input, timeout_secs=60)
        comments = get_actor_results(run["defaultDatasetId"])
        
        return comments
    
    except Exception as e:
        print(f"Error collecting comments for post {post_id}: {str(e)}")
        return [] 