import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime

from analysis.common.llm_client import get_gemini_json_response
from utils.image_utils import encode_image_to_base64

async def analyze_user_profile_with_llm(user_profile: Dict[str, Any], brand_handle: str = "", brand_name: str = "") -> Dict[str, Any]:
    """
    Analyze a user's profile to determine if they fit the ideal customer profile (ICP) for a given brand
    
    Args:
        user_profile: User profile data dictionary
        brand_handle: Instagram handle of the brand to analyze against
        brand_name: Name of the brand
        
    Returns:
        Dictionary with user profile and ICP analysis
    """
    username = user_profile.get("username", "")
    print(f"Analyzing user profile for @{username} with LLM")
    
    # Extract profile data
    profile_data = user_profile.get("profile_data", {})
    posts = user_profile.get("posts", [])
    
    try:
        # Extract basic information
        bio = profile_data.get("biography", "")
        full_name = profile_data.get("fullName", "")
        followers = profile_data.get("followersCount", 0)
        following = profile_data.get("followingCount", 0)
        posts_count = profile_data.get("postsCount", 0)
        
        # Extract captions from posts
        captions = [post.get("caption", "") for post in posts if post.get("caption")]
        captions_sample = captions[:3]  # Limit sample size
        
        # Build prompt for analysis
        prompt = f"""
        Analyze this Instagram user profile to determine if they fit the ideal customer profile (ICP) for {brand_name or brand_handle}.
        
        User: {full_name or username}
        Instagram handle: @{username}
        Bio: {bio}
        Followers: {followers if followers else "Unknown"}
        Following: {following if following else "Unknown"}
        Posts: {posts_count if posts_count else "Unknown"}
        
        Sample post captions:
        {chr(10).join(['- ' + caption[:200] + ('...' if len(caption) > 200 else '') for caption in captions_sample]) if captions_sample else "No captions available"}
        
        Brand context:
        Brand: {brand_name or brand_handle}
        Instagram: @{brand_handle}
        
        Analyze if this user is a good potential customer or follower for {brand_name or brand_handle}. Provide the following in a structured JSON format:
        1. User profile summary
        2. Demographics (estimated age range, gender if identifiable, location if mentioned)
        3. Interests and affinities based on their content
        4. Relevance to {brand_name or brand_handle} (high, medium, low)
        5. Reasoning for the relevance score
        6. Is this user a suitable ICP (ideal customer profile)? (true/false)
        7. Recommended engagement approach
        
        Return analysis as a valid JSON object.
        """
        
        # Call Gemini API
        response = get_gemini_json_response("gemini-pro", [prompt])
        
        # Add metadata
        response["username"] = username
        response["brand_handle"] = brand_handle
        response["analysis_timestamp"] = datetime.now().isoformat()
        
        # Extract key fields for easier access
        response["is_suitable_icp"] = response.get("is_suitable_icp", False)
        
        return response
    
    except Exception as e:
        print(f"Error analyzing user profile with LLM: {str(e)}")
        # Return fallback analysis
        return {
            "username": username,
            "profile_summary": f"Instagram user @{username}",
            "demographics": {
                "age_range": "Unknown",
                "gender": "Unknown",
                "location": "Unknown"
            },
            "interests": ["Unable to determine due to API error"],
            "relevance_to_brand": "medium",
            "reasoning": f"Error during analysis: {str(e)}",
            "is_suitable_icp": True,  # Default to True to be inclusive
            "recommended_engagement": "Standard engagement approach",
            "error": str(e),
            "fallback_generated": True,
            "analysis_timestamp": datetime.now().isoformat()
        }

# Rule-based alternative for when LLM is not available
async def analyze_follower_content(follower_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a follower's content to determine if they're a suitable ideal customer profile using rule-based approach
    
    Args:
        follower_data: Follower data dictionary
        
    Returns:
        Dictionary with follower data and analysis
    """
    username = follower_data.get("username")
    print(f"Analyzing content for follower @{username} (rule-based)")
    
    # Get profile data and posts
    profile_data = follower_data.get("profile_data", {})
    posts = follower_data.get("posts", [])
    
    # Simple rule-based approach without LLM
    # Create a basic analysis based on available data
    analysis = {
        "is_suitable_icp": True,  # Default to True to be inclusive
        "reasoning": "Simple rule-based analysis",
        "profile_summary": f"Instagram user @{username}",
        "interests": ["Not analyzed - using rule-based approach"],
        "demographic_indicators": ["Unknown"],
        "brand_affinities": [],
        "analysis_method": "rule-based",
        "analysis_timestamp": datetime.now().isoformat()
    }
    
    # Update follower data with our analysis
    follower_data["icp_analysis"] = analysis
    follower_data["is_suitable_icp"] = True
    
    return follower_data

async def analyze_follower_profile(username: str) -> Dict[str, Any]:
    """
    Analyze a follower's profile to determine if they are a good ICP candidate
    
    Args:
        username: Instagram username to analyze
        
    Returns:
        Dictionary with analysis results
    """
    print(f"Analyzing follower profile for @{username}")
    
    try:
        # Import here to avoid circular imports
        from apify.instagram_profile import check_profile_visibility
        from apify.instagram_posts import collect_instagram_posts
        
        # Check profile visibility first
        visibility = await check_profile_visibility(username)
        
        # If profile doesn't exist or is private, return quickly
        if not visibility.get("exists") or visibility.get("is_private"):
            return {
                "username": username,
                "is_suitable_icp": False,
                "reasoning": f"Profile is {'private' if visibility.get('exists') else 'not found'}",
                "analysis_timestamp": datetime.now().isoformat()
            }
        
        # For public profiles, get post data
        posts = await collect_instagram_posts(username, limit=3)
        
        # Simple rules to determine quality
        post_count = len(posts)
        has_captions = any(post.get("caption") for post in posts)
        
        is_suitable = post_count > 0 and has_captions
        
        return {
            "username": username,
            "is_suitable_icp": is_suitable,
            "reasoning": f"Profile has {post_count} accessible posts",
            "profile_data": visibility.get("profile_data"),
            "posts_sample": posts,
            "analysis_timestamp": datetime.now().isoformat(),
            "analysis_method": "rule-based"
        }
        
    except Exception as e:
        print(f"Error analyzing follower profile: {str(e)}")
        return {
            "username": username,
            "is_suitable_icp": False,
            "reasoning": f"Error: {str(e)}",
            "analysis_timestamp": datetime.now().isoformat(),
            "error": str(e)
        } 