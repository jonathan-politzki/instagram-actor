import asyncio
from typing import Dict, Any, Optional

from utils.rate_limit import rate_limit
from utils.cache import cached
from apify.client import run_actor, get_actor_results

@cached(max_age_days=1)
async def collect_instagram_profile(instagram_handle: str) -> Dict[str, Any]:
    """
    Collect Instagram profile data
    
    Args:
        instagram_handle: Instagram handle to collect profile for
        
    Returns:
        Profile data dictionary
    """
    print(f"Collecting Instagram profile for @{instagram_handle}")
    
    # Apply rate limiting
    await rate_limit("instagram_profile")
    
    # Run the Instagram profile scraper actor
    run_input = {
        "usernames": [instagram_handle],
        "resultsType": "details",
        "extendOutputFunction": """
            ($) => {
                return {
                    username: $.username,
                    fullName: $.full_name,
                    biography: $.biography,
                    followersCount: $.edge_followed_by.count,
                    followingCount: $.edge_follow.count,
                    postsCount: $.edge_owner_to_timeline_media.count,
                    profilePicUrl: $.profile_pic_url_hd,
                    isBusinessAccount: $.is_business_account,
                    businessCategory: $.business_category_name,
                    is_private: $.is_private,
                    has_public_story: $.has_public_story
                }
            }
        """
    }
    
    try:
        run = run_actor("apify/instagram-profile-scraper", run_input)
        items = get_actor_results(run["defaultDatasetId"])
        
        if not items:
            raise Exception(f"No profile data found for @{instagram_handle}")
        
        return items[0]
    
    except Exception as e:
        print(f"Error collecting Instagram profile: {str(e)}")
        raise

@cached(max_age_days=1)
async def check_profile_visibility(username: str) -> Dict[str, Any]:
    """
    Check if an Instagram profile is public or private and retrieve basic profile data
    
    Args:
        username: Instagram username to check
        
    Returns:
        Dictionary with profile visibility information
    """
    print(f"Checking visibility for @{username}")
    
    try:
        # Apply rate limiting
        await rate_limit("profile_check")
        
        # Use the profile scraper with extended output function to properly get the is_private field
        profile_run_input = {
            "usernames": [username],
            "resultsType": "details",
            "extendOutputFunction": """
                ($) => {
                    return {
                        username: $.username,
                        fullName: $.full_name,
                        biography: $.biography,
                        followersCount: $.edge_followed_by?.count,
                        followingCount: $.edge_follow?.count,
                        postsCount: $.edge_owner_to_timeline_media?.count,
                        profilePicUrl: $.profile_pic_url_hd,
                        is_private: $.is_private,
                        isBusinessAccount: $.is_business_account,
                        businessCategory: $.business_category_name,
                        has_public_story: $.has_public_story
                    }
                }
            """
        }
        
        # First API call - get basic profile data
        profile_run = run_actor("apify/instagram-profile-scraper", profile_run_input, timeout_secs=60)
        profile_items = get_actor_results(profile_run["defaultDatasetId"])
        
        if not profile_items:
            # Try one more time with a basic call
            await rate_limit("profile_check")
            simple_run_input = {"usernames": [username]}
            profile_run = run_actor("apify/instagram-profile-scraper", simple_run_input, timeout_secs=60)
            profile_items = get_actor_results(profile_run["defaultDatasetId"])
            
            if not profile_items:
                return {
                    "username": username,
                    "exists": False,
                    "is_private": True,
                    "is_public": False,
                    "profile_data": None
                }
        
        profile_data = profile_items[0]
        
        # Instagram marks business profiles differently, so we consider both
        is_private = profile_data.get("is_private", True)
        is_business = profile_data.get("isBusinessAccount", False)
        posts_count = profile_data.get("postsCount", 0)
        
        # Additional verification for public vs private status
        is_public = False
        
        # Business accounts should be considered public even if private flag is set
        if is_business:
            is_public = True
        
        # If is_private is explicitly False, it's public
        elif is_private is False:
            is_public = True
            
        # Also check posts count - if there are posts and it's not explicitly marked private, 
        # it might be public (we'll do an additional check)
        elif posts_count > 0 and is_private is not True:
            is_public = True
            
        # If still unsure, try to get posts as a final verification
        if not is_public and not is_business and is_private is not False:
            try:
                # Apply rate limiting
                await rate_limit("profile_posts_check")
                
                # Try to get posts - if we can, it's public
                posts_input = {
                    "usernames": [username],
                    "resultsType": "posts",
                    "resultsLimit": 1
                }
                
                posts_run = run_actor("apify/instagram-profile-scraper", posts_input, timeout_secs=30)
                posts = get_actor_results(posts_run["defaultDatasetId"])
                
                # If we get posts, it's definitely public
                if posts and len(posts) > 0:
                    is_public = True
                    is_private = False
            except:
                # Error getting posts - assume it's private
                is_public = False
                is_private = True
        
        return {
            "username": username,
            "exists": True,
            "is_private": is_private,
            "is_public": is_public,
            "is_business": is_business,
            "profile_data": profile_data
        }
    
    except Exception as e:
        print(f"Error checking profile visibility for @{username}: {str(e)}")
        # Default to assume it exists but is private in case of error
        return {
            "username": username,
            "exists": True,
            "is_private": True,
            "is_public": False,
            "error": str(e)
        } 