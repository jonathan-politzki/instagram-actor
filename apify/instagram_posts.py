from typing import Dict, List, Any

from utils.rate_limit import rate_limit
from utils.cache import cached
from apify.client import run_actor, get_actor_results

@cached(max_age_days=1)
async def collect_instagram_posts(instagram_handle: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Collect Instagram posts for a brand's Instagram account
    
    Args:
        instagram_handle: Instagram handle to collect posts for
        limit: Maximum number of posts to collect
        
    Returns:
        List of posts
    """
    print(f"Collecting Instagram posts for @{instagram_handle}")
    
    try:
        # Apply rate limiting
        await rate_limit("instagram_posts")
        
        # Try the main Instagram scraper actor first with correct parameters
        print(f"Collecting posts with apify/instagram-scraper...")
        run_input = {
            "profiles": [instagram_handle],  # Using 'profiles' rather than 'usernames'
            "resultsType": "posts",
            "resultsLimit": limit * 2,  # Request more posts to ensure we get at least 'limit'
            "addParentData": False,
            "searchType": "user",
            "searchLimit": limit * 2
        }
        
        # First try the main Instagram scraper
        try:
            run = run_actor("apify/instagram-scraper", run_input, timeout_secs=120)
            posts = get_actor_results(run["defaultDatasetId"])
            
            if not posts:
                raise Exception("No posts returned by instagram-scraper")
                
        except Exception as e:
            print(f"First scraper failed: {str(e)}, trying profile scraper...")
            # Fallback to the profile scraper
            profile_run_input = {
                "usernames": [instagram_handle],
                "resultsType": "posts",
                "resultsLimit": limit,
                "extendOutputFunction": """
                    ($) => {
                        return {
                            id: $.id,
                            shortCode: $.shortcode,
                            caption: $.edge_media_to_caption?.edges[0]?.node?.text,
                            commentsCount: $.edge_media_to_comment?.count,
                            dimensionsHeight: $.dimensions?.height,
                            dimensionsWidth: $.dimensions?.width,
                            displayUrl: $.display_url,
                            likesCount: $.edge_media_preview_like?.count,
                            timestamp: $.taken_at_timestamp,
                            url: `https://www.instagram.com/p/${$.shortcode}/`
                        }
                    }
                """
            }
            
            # Apply rate limiting before fallback
            await rate_limit("instagram_posts")
            run = run_actor("apify/instagram-profile-scraper", profile_run_input, timeout_secs=120)
            posts = get_actor_results(run["defaultDatasetId"])
        
        print(f"Successfully collected {len(posts)} posts for @{instagram_handle}")
        
        # Limit the number of posts returned
        return posts[:limit]
    
    except Exception as e:
        print(f"Error collecting Instagram posts: {str(e)}")
        # Return empty list instead of raising to prevent analysis from failing
        return []

async def collect_user_profile_posts(username: str, limit: int = 3) -> Dict[str, Any]:
    """
    Simple helper function to collect a user's profile and a few posts
    
    Args:
        username: Instagram username to collect data for
        limit: Maximum number of posts to collect
        
    Returns:
        Dictionary with user profile and posts data
    """
    try:
        print(f"Collecting profile data for @{username}")
        
        # Import here to avoid circular imports
        from apify.instagram_profile import collect_instagram_profile
        
        # Get profile data
        profile_data = await collect_instagram_profile(username)
        if not profile_data:
            print(f"Could not retrieve profile data for @{username}")
            return {}
            
        # Get posts (just a few)
        posts = await collect_instagram_posts(username, limit=limit)
        
        # Combine into a user profile object
        user_data = {
            "username": username,
            "profile_data": profile_data,
            "posts": posts
        }
        
        return user_data
    
    except Exception as e:
        print(f"Error collecting user data for @{username}: {str(e)}")
        return {
            "username": username,
            "error": str(e)
        } 