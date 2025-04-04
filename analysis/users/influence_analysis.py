import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import re

from analysis.common.llm_client import get_gemini_json_response

async def analyze_user_influence_with_llm(user_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a user's Instagram profile to determine their influence characteristics
    
    Args:
        user_profile: User profile data dictionary
        
    Returns:
        Dictionary with user influence analysis
    """
    username = user_profile.get("username", "")
    print(f"Analyzing influence for @{username} with LLM")
    
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
        is_business = profile_data.get("isBusinessAccount", False)
        business_category = profile_data.get("businessCategory", "")
        
        # Extract captions from posts
        captions = [post.get("caption", "") for post in posts if post.get("caption")]
        captions_sample = captions[:3]  # Limit sample size
        
        # Build prompt for analysis
        prompt = f"""
        Analyze this Instagram user profile to determine their influence characteristics and audience:
        
        User: {full_name or username}
        Instagram handle: @{username}
        Bio: {bio}
        Followers: {followers if followers else "Unknown"}
        Following: {following if following else "Unknown"}
        Posts: {posts_count if posts_count else "Unknown"}
        Business account: {"Yes" if is_business else "No"}
        {f"Business category: {business_category}" if business_category else ""}
        
        Sample post captions:
        {chr(10).join(['- ' + caption[:200] + ('...' if len(caption) > 200 else '') for caption in captions_sample]) if captions_sample else "No captions available"}
        
        Provide a comprehensive analysis with the following information in a structured JSON format:
        
        1. Influence category (micro-influencer, content creator, brand ambassador, casual user, etc.)
        2. Estimated authenticity score (0-100)
        3. Content themes and topics
        4. Engagement potential (estimated engagement rate)
        5. Audience demographics (estimated)
        6. Brand alignment potential (what types of brands would be a good fit)
        7. Strengths as a potential influencer
        8. Areas for development
        
        Return the analysis as a valid JSON object.
        """
        
        # Call Gemini API
        response = get_gemini_json_response("gemini-pro", [prompt])
        
        # Add metadata
        response["username"] = username
        response["analysis_timestamp"] = datetime.now().isoformat()
        
        return response
    
    except Exception as e:
        print(f"Error analyzing user influence with LLM: {str(e)}")
        # Return fallback analysis
        return {
            "username": username,
            "influence_category": "casual user",
            "authenticity_score": 50,
            "content_themes": ["Unable to determine due to API error"],
            "engagement_potential": "medium",
            "audience_demographics": {
                "age_range": "Unknown",
                "primary_locations": ["Unknown"],
                "interests": ["Unknown"]
            },
            "brand_alignment_potential": ["General consumer brands"],
            "strengths": ["Instagram presence"],
            "areas_for_development": ["More consistent content", "Enhanced engagement"],
            "error": str(e),
            "fallback_generated": True,
            "analysis_timestamp": datetime.now().isoformat()
        }

# Rule-based alternative for when LLM is not available
async def analyze_user_influence(user_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a user's influence using rule-based approach
    
    Args:
        user_profile: User profile data
        
    Returns:
        Dictionary with user influence analysis
    """
    username = user_profile.get("username", "")
    print(f"Analyzing influence for @{username} (rule-based)")
    
    # Extract profile data
    profile_data = user_profile.get("profile_data", {})
    posts = user_profile.get("posts", [])
    
    # Default values
    influence = {
        "username": username,
        "influence_category": "casual user",
        "authenticity_score": 50,
        "content_themes": [],
        "engagement_potential": "medium",
        "analysis_timestamp": datetime.now().isoformat(),
        "analysis_method": "rule-based"
    }
    
    try:
        # Extract basics
        followers = profile_data.get("followersCount", 0)
        following = profile_data.get("followingCount", 0)
        posts_count = profile_data.get("postsCount", 0)
        is_business = profile_data.get("isBusinessAccount", False)
        bio = profile_data.get("biography", "")
        
        # Determine influence category based on followers
        if followers > 1000000:
            influence["influence_category"] = "mega-influencer"
        elif followers > 100000:
            influence["influence_category"] = "macro-influencer"
        elif followers > 10000:
            influence["influence_category"] = "mid-tier influencer"
        elif followers > 1000:
            influence["influence_category"] = "micro-influencer"
        elif is_business:
            influence["influence_category"] = "business account"
        else:
            influence["influence_category"] = "casual user"
        
        # Estimate authenticity based on followers/following ratio
        if followers > 0 and following > 0:
            ratio = followers / following
            if ratio > 20:
                # Very skewed ratio suggests potential fake followers
                influence["authenticity_score"] = 30
            elif ratio > 10:
                influence["authenticity_score"] = 60
            elif ratio > 2:
                influence["authenticity_score"] = 80
            else:
                influence["authenticity_score"] = 70
            
        # Look for content themes in bio and posts
        themes = []
        
        theme_keywords = {
            "fashion": ["fashion", "style", "outfit", "clothing", "model"],
            "fitness": ["fitness", "gym", "workout", "exercise", "training", "health"],
            "travel": ["travel", "adventure", "explore", "wanderlust", "destination"],
            "food": ["food", "recipe", "cooking", "chef", "restaurant", "meal"],
            "beauty": ["beauty", "makeup", "skincare", "cosmetics", "hair"],
            "lifestyle": ["lifestyle", "life", "everyday", "daily"],
            "technology": ["tech", "technology", "gadget", "digital", "app"],
            "business": ["entrepreneur", "business", "startup", "success", "career"],
            "art": ["art", "artist", "creative", "design", "illustration"],
            "photography": ["photo", "photography", "photographer", "camera", "picture"]
        }
        
        # Check bio for themes
        bio_lower = bio.lower()
        for theme, keywords in theme_keywords.items():
            if any(keyword in bio_lower for keyword in keywords):
                themes.append(theme)
        
        # Check captions for themes
        captions_text = " ".join([post.get("caption", "").lower() for post in posts if post.get("caption")])
        for theme, keywords in theme_keywords.items():
            if theme not in themes:  # Don't duplicate themes already found
                if any(keyword in captions_text for keyword in keywords):
                    themes.append(theme)
        
        # Add themes
        influence["content_themes"] = themes or ["general content"]
        
        # Estimate engagement potential
        likes = [post.get("likesCount", 0) for post in posts]
        comments = [post.get("commentsCount", 0) for post in posts]
        
        if likes and comments:
            avg_likes = sum(likes) / len(likes)
            avg_comments = sum(comments) / len(comments)
            
            if followers > 0:
                engagement_rate = (avg_likes + avg_comments) / followers * 100
                
                if engagement_rate > 5:
                    influence["engagement_potential"] = "high"
                elif engagement_rate > 2:
                    influence["engagement_potential"] = "medium"
                else:
                    influence["engagement_potential"] = "low"
        
        return influence
        
    except Exception as e:
        print(f"Error in rule-based influence analysis: {str(e)}")
        influence["error"] = str(e)
        return influence

async def analyze_comments_for_influence(comments: List[Dict[str, Any]], username: str) -> Dict[str, Any]:
    """
    Analyze a user's comments to determine their influence and engagement style
    
    Args:
        comments: List of comments
        username: Username of the commenter
        
    Returns:
        Analysis results
    """
    if not comments:
        return {
            "username": username,
            "comment_count": 0,
            "engagement_quality": "unknown",
            "sentiment": "neutral",
            "analysis_timestamp": datetime.now().isoformat()
        }
    
    try:
        # Analyze sentiment and engagement of each comment
        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        engagement_scores = []
        
        for comment in comments:
            text = comment.get("text", "")
            
            if not text:
                continue
                
            # Use analyze_comment_quality from audience_analysis.py (import for actual use)
            # For now, simple implementation:
            
            # Simple sentiment analysis
            positive_terms = ["love", "great", "amazing", "awesome", "beautiful", "perfect", "excellent"]
            negative_terms = ["bad", "worst", "terrible", "ugly", "hate", "disappointing", "poor"]
            
            positive_count = sum(1 for term in positive_terms if term in text.lower())
            negative_count = sum(1 for term in negative_terms if term in text.lower())
            
            if positive_count > negative_count:
                sentiment_counts["positive"] += 1
            elif negative_count > positive_count:
                sentiment_counts["negative"] += 1
            else:
                sentiment_counts["neutral"] += 1
                
            # Simple engagement score
            engagement_score = min(100, len(text) / 2)  # Length-based score
            engagement_scores.append(engagement_score)
        
        # Calculate overall sentiment
        if sentiment_counts["positive"] > sentiment_counts["negative"] + sentiment_counts["neutral"]:
            overall_sentiment = "positive"
        elif sentiment_counts["negative"] > sentiment_counts["positive"] + sentiment_counts["neutral"]:
            overall_sentiment = "negative"
        else:
            overall_sentiment = "neutral"
            
        # Calculate overall engagement quality
        avg_engagement = sum(engagement_scores) / len(engagement_scores) if engagement_scores else 0
        
        if avg_engagement > 70:
            engagement_quality = "high"
        elif avg_engagement > 30:
            engagement_quality = "medium"
        else:
            engagement_quality = "low"
            
        return {
            "username": username,
            "comment_count": len(comments),
            "engagement_quality": engagement_quality,
            "sentiment": overall_sentiment,
            "avg_engagement_score": avg_engagement,
            "sentiment_distribution": sentiment_counts,
            "analysis_timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error analyzing comments for influence: {str(e)}")
        return {
            "username": username,
            "comment_count": len(comments),
            "engagement_quality": "medium",
            "sentiment": "neutral",
            "error": str(e),
            "analysis_timestamp": datetime.now().isoformat()
        } 