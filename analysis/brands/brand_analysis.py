import asyncio
from typing import Dict, List, Any
from datetime import datetime

from analysis.common.llm_client import get_gemini_json_response
from utils.image_utils import encode_image_to_base64

async def analyze_brand_profile_with_llm(profile_data: Dict[str, Any], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze a brand's Instagram profile using LLM to extract key identity elements
    
    Args:
        profile_data: Brand profile data from Instagram
        posts: List of posts from the brand's Instagram
        
    Returns:
        Dictionary with brand identity analysis
    """
    instagram_handle = profile_data.get("username", "")
    print(f"Analyzing brand profile for @{instagram_handle} with LLM")
    
    try:
        # Extract basic information
        bio = profile_data.get("biography", "")
        full_name = profile_data.get("fullName", "")
        followers = profile_data.get("followersCount", 0)
        following = profile_data.get("followingCount", 0)
        posts_count = profile_data.get("postsCount", 0)
        
        # Extract captions from posts
        captions = [post.get("caption", "") for post in posts if post.get("caption")]
        captions_sample = captions[:5]  # Limit to 5 captions for prompt size
        
        # Prepare sample images (optional)
        image_urls = []
        for post in posts[:3]:  # Use first 3 posts only
            if post.get("displayUrl"):
                image_urls.append(post.get("displayUrl"))
        
        # Build prompt for analysis
        prompt = f"""
        Analyze this Instagram brand profile and posts to extract key identity elements.
        
        Brand: {full_name or instagram_handle}
        Instagram handle: @{instagram_handle}
        Bio: {bio}
        Followers: {followers:,}
        Following: {following:,}
        Posts: {posts_count:,}
        
        Sample post captions:
        {chr(10).join(['- ' + caption[:300] + ('...' if len(caption) > 300 else '') for caption in captions_sample])}
        
        Please analyze and provide the following in a structured JSON format:
        1. Brand identity: What is the core identity and positioning of this brand?
        2. Messaging style: How does the brand communicate (tone, language style, etc.)?
        3. Visual identity: What visual elements characterize the brand's Instagram presence?
        4. Key topics: What topics/themes does the brand focus on?
        5. Target audience: Who is the brand's primary audience based on content?
        6. Strengths: What does the brand do well on Instagram?
        7. Opportunity areas: Where could the brand improve its Instagram presence?
        
        Return the analysis as a valid JSON object.
        """
        
        # Call Gemini API
        response = get_gemini_json_response("gemini-pro", [prompt])
        
        # Add metadata
        response["analysis_timestamp"] = datetime.now().isoformat()
        
        return response
    
    except Exception as e:
        print(f"Warning: Error in brand analysis: {str(e)}")
        # Return simple fallback analysis
        return {
            "brand_identity": f"Instagram profile for @{instagram_handle}",
            "messaging_style": "Visual-focused social media content",
            "visual_identity": "Professional photography and branded content",
            "key_topics": ["Products", "Lifestyle"],
            "target_audience": "Social media users interested in the brand's products",
            "strengths": ["Brand presence on Instagram"],
            "opportunity_areas": ["Enhanced engagement strategy"],
            "analysis_error": str(e),
            "analysis_timestamp": datetime.now().isoformat(),
            "fallback_generated": True
        }

# Rule-based alternative (for when LLM is not needed)
async def analyze_brand_profile(profile_data: Dict[str, Any], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze a brand's Instagram profile to extract key identity elements
    Using simplified rule-based approach in case of API errors
    
    Args:
        profile_data: Brand profile data from Instagram 
        posts: List of posts from the brand's Instagram
        
    Returns:
        Dictionary with brand identity analysis
    """
    instagram_handle = profile_data.get("username", "")
    print(f"Analyzing brand profile for @{instagram_handle} (rule-based)")
    
    try:
        # Extract basic information
        bio = profile_data.get("biography", "")
        full_name = profile_data.get("fullName", "")
        
        # Extract post captions
        captions = [post.get("caption", "") for post in posts if post.get("caption")]
        
        # Use simple heuristics instead of LLM
        topics = []
        if any(word in bio.lower() for word in ["sport", "athlete", "fitness", "train"]):
            topics.append("Sports/Fitness")
        if any(word in bio.lower() for word in ["style", "fashion", "design"]):
            topics.append("Fashion/Style")
        if any(word in bio.lower() for word in ["sustainable", "eco", "planet"]):
            topics.append("Sustainability")
        if any(word in bio.lower() for word in ["tech", "technology", "digital"]):
            topics.append("Technology")
        if any(word in bio.lower() for word in ["food", "recipe", "cook", "restaurant"]):
            topics.append("Food/Culinary")
        if any(word in bio.lower() for word in ["travel", "adventure", "explore"]):
            topics.append("Travel/Adventure")
        if any(word in bio.lower() for word in ["beauty", "makeup", "skin"]):
            topics.append("Beauty/Cosmetics")
        
        # Default to generic topics if none detected
        if not topics:
            if "nike" in instagram_handle.lower():
                topics = ["Sports", "Lifestyle", "Fashion"]
            elif "adidas" in instagram_handle.lower():
                topics = ["Sports", "Lifestyle", "Fashion"]
            else:
                topics = ["Lifestyle", "Products", "Brand Content"]
        
        # Create simple analysis
        analysis = {
            "brand_identity": f"Instagram profile for {full_name or instagram_handle}",
            "messaging_style": "Visual-focused social media content",
            "visual_identity": "Professional photography and branded content",
            "key_topics": topics,
            "target_audience": "Social media users interested in the brand's products and lifestyle",
            "strengths": ["Strong visual identity", "Consistent branding"],
            "opportunity_areas": ["More audience engagement", "Enhanced storytelling"],
            "analysis_timestamp": datetime.now().isoformat(),
            "analysis_method": "rule-based"
        }
        
        return analysis
        
    except Exception as e:
        print(f"Warning: Error in brand analysis: {str(e)}")
        # Return simple fallback analysis
        return {
            "brand_identity": f"Instagram profile for @{instagram_handle}",
            "key_topics": ["Products", "Lifestyle"],
            "target_audience": "Social media users",
            "strengths": ["Brand presence on Instagram"],
            "analysis_error": str(e),
            "analysis_timestamp": datetime.now().isoformat(),
            "fallback_generated": True
        } 