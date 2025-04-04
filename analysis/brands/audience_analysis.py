import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import re

from analysis.common.llm_client import get_gemini_json_response

async def generate_audience_insights_with_llm(icp_data: List[Dict[str, Any]], brand_name: str, brand_handle: str) -> Dict[str, Any]:
    """
    Generate audience insights from a list of ICP data
    
    Args:
        icp_data: List of user profiles with ICP analysis
        brand_name: Brand name
        brand_handle: Brand Instagram handle
        
    Returns:
        Dictionary with audience insights
    """
    print(f"Generating audience insights for @{brand_handle}")
    
    try:
        # Check if we have ICP data
        if not icp_data:
            print("No ICP data available, generating general insights")
            return {
                "audience_alignment": "Insufficient data to determine specific ICP alignment",
                "audience_segments": [
                    {
                        "name": "General Instagram Users",
                        "description": "Instagram users who engage with brand content",
                        "estimated_percentage": 100
                    }
                ],
                "content_recommendations": [
                    "Post engaging visual content regularly",
                    "Encourage user-generated content",
                    "Use Instagram Stories for behind-the-scenes content"
                ],
                "engagement_strategies": [
                    "Respond to comments consistently",
                    "Run Instagram contests or giveaways",
                    "Collaborate with micro-influencers in your niche"
                ],
                "general_insight": "More audience data needed for detailed analysis",
                "analysis_timestamp": datetime.now().isoformat(),
                "analysis_method": "general_recommendations"
            }
        
        # Extract suitable ICPs only
        suitable_icps = [profile for profile in icp_data if profile.get("is_suitable_icp", False)]
        
        # Extract key information from suitable ICPs
        interests = []
        demographics = []
        affinities = []
        
        for profile in suitable_icps:
            # Interests
            profile_interests = profile.get("interests", [])
            if isinstance(profile_interests, list):
                interests.extend(profile_interests)
            
            # Demographics
            profile_demographics = profile.get("demographics", {})
            if isinstance(profile_demographics, dict):
                if "age_range" in profile_demographics and profile_demographics["age_range"] != "Unknown":
                    demographics.append(f"Age: {profile_demographics['age_range']}")
                if "gender" in profile_demographics and profile_demographics["gender"] != "Unknown":
                    demographics.append(f"Gender: {profile_demographics['gender']}")
                if "location" in profile_demographics and profile_demographics["location"] != "Unknown":
                    demographics.append(f"Location: {profile_demographics['location']}")
        
        # Build prompt for analysis
        prompt = f"""
        Generate detailed audience insights for {brand_name or brand_handle} based on analysis of {len(suitable_icps)} identified ideal customer profiles.
        
        Brand: {brand_name or brand_handle}
        Instagram handle: @{brand_handle}
        
        Key interests identified across profiles:
        {chr(10).join(['- ' + interest for interest in interests[:20]])}
        
        Demographics identified:
        {chr(10).join(['- ' + demo for demo in demographics[:20]])}
        
        Please provide a comprehensive audience analysis with the following in a structured JSON format:
        
        1. Audience alignment: Overall assessment of how well the brand's content aligns with the identified audience
        2. Audience segments: Key segments within the audience, their descriptions, and estimated percentage
        3. Content recommendations: 3-5 specific content strategies to better engage this audience
        4. Engagement strategies: 3-5 engagement tactics to build stronger connections
        5. Key insights: 2-3 valuable insights about this audience that could inform marketing strategy
        
        Return the analysis in a valid JSON format.
        """
        
        # Call Gemini API
        response = get_gemini_json_response("gemini-pro", [prompt])
        
        # Add metadata
        response["analysis_timestamp"] = datetime.now().isoformat()
        response["analysis_method"] = "llm_insights"
        response["analyzed_profiles_count"] = len(suitable_icps)
        
        return response
    
    except Exception as e:
        print(f"Error generating audience insights: {str(e)}")
        # Return simple fallback insights
        return {
            "audience_alignment": "Error occurred during audience analysis",
            "content_recommendations": [
                "Continue posting high-quality visual content", 
                "Increase engagement through questions and calls to action"
            ],
            "engagement_strategies": [
                "Respond to comments consistently",
                "Use Instagram Stories for behind-the-scenes content"
            ],
            "error": str(e),
            "fallback_generated": True,
            "analysis_timestamp": datetime.now().isoformat()
        }

async def analyze_comment_quality(comment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes a comment to determine its sentiment, authenticity, and relevance.
    Helps filter out bot comments, spam, and negative sentiment.
    
    Args:
        comment: Comment data dictionary
        
    Returns:
        The original comment with added quality metrics
    """
    # Extract comment data
    username = comment.get("ownerUsername", "")
    text = comment.get("text", "")
    
    # Skip empty comments
    if not text or not username:
        comment["quality_score"] = 0
        comment["is_likely_bot"] = True
        comment["sentiment"] = "neutral"
        return comment
    
    # Initialize quality metrics
    quality_metrics = {
        "is_likely_bot": False,
        "sentiment": "neutral",
        "quality_score": 50  # Default middle score
    }
    
    # Bot detection signals
    bot_signals = [
        # Generic/spam phrases
        any(phrase in text.lower() for phrase in [
            "check my profile", "check out my", "follow me", "dm me", "click my bio", 
            "click the link", "earn money", "make money", "join now", "discount code",
            "promo code", "free followers", "visit my page", "visit my profile",
            "follow back", "follow for follow", "f4f", "l4l", "like for like"
        ]),
        
        # Excessive emoji usage (more than 50% of content)
        sum(1 for char in text if ord(char) > 127) > len(text) * 0.5,
        
        # Very short generic comments
        len(text) < 5 and text.lower() in ["nice", "cool", "wow", "omg", "love", "lol", "🔥", "👍", "❤️", "🙌"],
        
        # Username patterns common in bot accounts
        bool(re.search(r'[0-9]{4,}$', username)),  # Ends with 4+ digits
        bool(re.search(r'^[a-z]+[0-9]{4,}', username))  # Letters followed by digits
    ]
    
    # Calculate bot probability
    bot_likelihood = sum(bot_signals) / len(bot_signals)
    quality_metrics["is_likely_bot"] = bot_likelihood > 0.4  # If more than 40% of signals are present
    
    # Sentiment analysis - simple approach
    positive_terms = ["love", "great", "amazing", "awesome", "beautiful", "perfect", "excellent", "stunning", "favorite", "best", "incredible"]
    negative_terms = ["bad", "worst", "terrible", "ugly", "hate", "disappointing", "poor", "awful", "horrible", "waste", "useless"]
    
    positive_count = sum(1 for term in positive_terms if term in text.lower())
    negative_count = sum(1 for term in negative_terms if term in text.lower())
    
    if positive_count > negative_count:
        quality_metrics["sentiment"] = "positive"
    elif negative_count > positive_count:
        quality_metrics["sentiment"] = "negative"
    else:
        quality_metrics["sentiment"] = "neutral"
    
    # Calculate overall quality score (0-100)
    base_score = 50
    
    # Deduct for bot likelihood
    bot_penalty = bot_likelihood * 50  # Up to -50 points
    
    # Adjust for sentiment
    sentiment_modifier = 0
    if quality_metrics["sentiment"] == "positive":
        sentiment_modifier = 20
    elif quality_metrics["sentiment"] == "negative":
        sentiment_modifier = -10
    
    # Adjust for length and substance
    length_modifier = min(20, len(text) / 10)  # Up to +20 for length
    
    # Calculate final score
    final_score = base_score - bot_penalty + sentiment_modifier + length_modifier
    
    # Ensure score is in 0-100 range
    quality_metrics["quality_score"] = max(0, min(100, int(final_score)))
    
    # Add quality metrics to comment
    comment.update(quality_metrics)
    
    return comment

async def filter_hashtag_relevance(brand_handle: str, hashtag: str) -> float:
    """
    Evaluates the relevance of a hashtag to the brand.
    
    Args:
        brand_handle: Brand's Instagram handle
        hashtag: Hashtag to evaluate (without # symbol)
        
    Returns:
        Relevance score between 0-1
    """
    brand_name = brand_handle.lower()
    hashtag = hashtag.lower()
    
    # Direct brand match
    if brand_name in hashtag or hashtag in brand_name:
        return 0.9  # Very high relevance
    
    # Check for common variations
    brand_variations = [
        brand_name,
        f"{brand_name}s",
        ''.join(word for word in brand_name if word.isalnum()),  # Remove special chars
        ''.join(c for c in brand_name if c.isalpha())  # Letters only
    ]
    
    for variation in brand_variations:
        if variation in hashtag or hashtag in variation:
            return 0.7  # High relevance
    
    # Check for partial matches (at least 4 chars)
    if len(brand_name) >= 4 and len(hashtag) >= 4:
        if brand_name[:4] in hashtag or hashtag[:4] in brand_name:
            return 0.4  # Medium relevance
    
    # For short brand names, be more careful
    if len(brand_name) < 4:
        # Only exact matches should be considered relevant
        return 0.2  # Low relevance by default
            
    # Default low relevance
    return 0.3

async def identify_real_people_from_usernames(usernames: List[str], brand_handle: str) -> List[Dict[str, Any]]:
    """
    Uses simple rules to identify usernames likely belonging to real people
    versus businesses or bots.
    
    Args:
        usernames: List of Instagram usernames to analyze
        brand_handle: The brand's Instagram handle for context
    
    Returns:
        List of dictionaries with username classification
    """
    if not usernames:
        return []
        
    print(f"Analyzing {len(usernames)} usernames to identify real people...")
    
    # Using simple rules instead of LLM
    real_people = []
    business_count = 0
    bot_count = 0
    
    for username in usernames:
        if not username:
            continue
            
        # Only filter obvious business indicators
        business_indicators = 0
        bot_indicators = 0
        
        # Basic business indicators - REDUCED list to only catch obvious ones
        business_words = ["shop", "store", "official", "boutique", "brand"]
        
        # Check for business patterns
        if any(word in username.lower() for word in business_words):
            business_indicators += 1
        
        # Look for LLC, INC, CO patterns
        if any(marker in username.lower() for marker in ["llc", "inc", ".co", "_co"]):
            business_indicators += 1
            
        # Basic bot indicators - REDUCED list
        bot_words = ["follow4follow", "f4f", "l4l", "followme", "getfollowers"]
        
        # Check for bot patterns
        if any(word in username.lower() for word in bot_words):
            bot_indicators += 1
            
        # Check for extremely long usernames with random characters
        if len(username) > 30 or username.count('_') > 3:
            bot_indicators += 1
            
        # Classify based on indicators
        if business_indicators >= 2:
            business_count += 1
            continue
        elif bot_indicators >= 2:
            bot_count += 1
            continue
        else:
            # Determine quality based on username characteristics
            quality = "medium"  # Default is medium now to be more inclusive
            
            # High quality indicators
            if len(username) < 20 and username.count("_") <= 1 and not username.endswith(tuple(['1','2','3','4','5','6','7','8','9','0'])):
                quality = "high"
                
            # Add to real people list
            real_people.append({
                "username": username,
                "category": "likely_person",
                "engagement_quality": quality,
                "reasoning": "Simple pattern matching (more inclusive approach)"
            })
    
    # Get counts for summary
    print(f"Analysis complete: {len(real_people)} likely real people identified")
    print(f"  - {business_count} business accounts filtered out")
    print(f"  - {bot_count} potential bot accounts filtered out")
    print(f"  - High-value connections: {len([r for r in real_people if r.get('engagement_quality') == 'high'])}")
    print(f"  - Medium-value connections: {len([r for r in real_people if r.get('engagement_quality') == 'medium'])}")
    
    return real_people 