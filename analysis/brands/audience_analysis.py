import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import re

from analysis.common.llm_client import get_gemini_json_response

# Import data collection functions - add these at the top
from apify.instagram_posts import collect_instagram_posts
from apify.instagram_profile import collect_instagram_profile
from apify.instagram_comments import collect_post_comments
from apify.instagram_hashtags import collect_hashtag_posts

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
    Analyze a comment's quality using rule-based approach
    
    Args:
        comment: Comment data dictionary
        
    Returns:
        Dictionary with quality score and analysis
    """
    text = comment.get("text", "")
    username = comment.get("ownerUsername", "unknown")
    
    # Skip empty comments
    if not text:
        return {
            "username": username,
            "text": text,
            "quality_score": 0,
            "quality_category": "poor",
            "reasoning": "Empty comment"
        }
    
    # Initialize base score
    quality_score = 0
    
    # Length factor (0-40 points)
    # Short comments receive fewer points
    length = len(text)
    if length > 100:
        quality_score += 40
    elif length > 50:
        quality_score += 30
    elif length > 20:
        quality_score += 20
    elif length > 10:
        quality_score += 10
    else:
        quality_score += 5
    
    # Complexity factor (0-30 points)
    # Simple comments with just emojis or basic phrases receive fewer points
    # Count word diversity
    words = text.split()
    unique_words = set(words)
    
    # More diverse vocabulary = higher score
    word_diversity = len(unique_words) / max(1, len(words))
    quality_score += min(30, int(word_diversity * 30))
    
    # Engagement factor (0-30 points)
    # Comments that ask questions or show deeper engagement
    engagement_indicators = [
        "?", "what", "how", "when", "why", "where", "who",
        "love", "amazing", "great", "awesome", "thank", "thanks",
        "beautiful", "perfect", "agree", "disagree", "opinion",
        "think", "believe", "feel", "experience", "recommend"
    ]
    
    # Count engagement indicators
    engagement_count = sum(1 for indicator in engagement_indicators if indicator in text.lower())
    quality_score += min(30, engagement_count * 5)
    
    # Categorize quality
    if quality_score >= 70:
        quality_category = "excellent"
        reasoning = "High-quality, thoughtful comment with substance"
    elif quality_score >= 50:
        quality_category = "good"
        reasoning = "Good comment showing engagement"
    elif quality_score >= 30:
        quality_category = "average"
        reasoning = "Average comment with some substance"
    else:
        quality_category = "poor"
        reasoning = "Brief or low-effort comment"
    
    return {
        "username": username,
        "text": text,
        "quality_score": quality_score,
        "quality_category": quality_category,
        "reasoning": reasoning
    }

async def filter_hashtag_relevance(brand_handle: str, hashtag: str) -> float:
    """
    Determine if a hashtag is relevant to a brand
    
    Args:
        brand_handle: Instagram handle of the brand
        hashtag: Hashtag to check (without # symbol)
        
    Returns:
        Relevance score (0.0-1.0)
    """
    # Simple relevance check - can be enhanced with more sophisticated logic
    
    # Convert to lowercase for comparison
    brand_handle = brand_handle.lower()
    hashtag = hashtag.lower()
    
    # Exact match with brand handle
    if brand_handle in hashtag or hashtag in brand_handle:
        return 1.0
    
    # Check common brand hashtag patterns
    common_variations = [
        f"{brand_handle}style",
        f"{brand_handle}life",
        f"{brand_handle}community",
        f"{brand_handle}fam",
        f"{brand_handle}lover",
        f"{brand_handle}fan",
        f"love{brand_handle}",
        f"team{brand_handle}"
    ]
    
    for variation in common_variations:
        if variation in hashtag or hashtag in variation:
            return 0.9
    
    # Similarity check - use fuzzy matching or edit distance for more sophisticated check
    # For now, use simple character overlap
    if len(brand_handle) > 3 and len(hashtag) > 3:
        overlap = sum(1 for char in brand_handle if char in hashtag) / len(brand_handle)
        if overlap > 0.7:
            return 0.7
    
    # Default - lower relevance
    return 0.1

async def collect_users_from_hashtags(brand_handle: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Collect users from hashtag posts
    
    Args:
        brand_handle: Instagram handle of the brand
        limit: Maximum number of users to return
        
    Returns:
        List of users from hashtag posts
    """
    print(f"Collecting users from hashtags for @{brand_handle}")
    
    try:
        # Get brand-related hashtags
        hashtags = [
            brand_handle,
            f"{brand_handle}style",
            f"{brand_handle}community"
        ]
        
        all_users = []
        seen_usernames = set()
        
        for hashtag in hashtags:
            print(f"Checking hashtag #{hashtag}")
            
            # Check relevance
            relevance = await filter_hashtag_relevance(brand_handle, hashtag)
            if relevance < 0.5:
                print(f"Skipping hashtag #{hashtag} - low relevance")
                continue
            
            # Collect hashtag posts
            hashtag_posts = await collect_hashtag_posts(hashtag, limit=10)
            
            if not hashtag_posts:
                print(f"No posts found for hashtag #{hashtag}")
                continue
            
            # Extract users from posts
            for post in hashtag_posts:
                username = post.get("ownerUsername")
                if username and username != brand_handle and username not in seen_usernames:
                    all_users.append({
                        "username": username,
                        "source": f"hashtag_{hashtag}",
                        "relevance": relevance
                    })
                    seen_usernames.add(username)
                    
                    if len(all_users) >= limit:
                        break
            
            if len(all_users) >= limit:
                break
        
        print(f"Collected {len(all_users)} users from hashtag posts")
        return all_users
        
    except Exception as e:
        print(f"Error collecting users from hashtags: {str(e)}")
        return []

async def collect_instagram_followers(instagram_handle: str, limit: int = 50, quality_threshold: int = 30) -> List[Dict[str, Any]]:
    """
    Collect Instagram followers with comment quality analysis
    
    Args:
        instagram_handle: Instagram handle to collect followers for
        limit: Maximum number of followers to return
        quality_threshold: Minimum quality score (0-100) for comments
        
    Returns:
        List of followers with quality scores
    """
    print(f"Collecting engaged users for @{instagram_handle}")
    print(f"Using quality threshold: {quality_threshold}")
    
    # Get posts to analyze comments
    posts = await collect_instagram_posts(instagram_handle, limit=5)
    
    if not posts:
        print("No posts found to analyze")
        return []
    
    # Store quality users with their scores
    quality_users = {}
    analyzed_count = 0
    
    # Analyze comments on each post
    for post in posts:
        post_id = post.get("shortCode", "")
        if not post_id:
            continue
        
        print(f"Analyzing comments for post {post_id}")
        
        # Get comments for this post
        comments = await collect_post_comments(post_id, limit=30)
        
        for comment in comments:
            username = comment.get("ownerUsername", "")
            
            # Skip comments from the brand itself
            if not username or username.lower() == instagram_handle.lower():
                continue
            
            # Analyze comment quality
            quality = await analyze_comment_quality(comment)
            quality_score = quality.get("quality_score", 0)
            analyzed_count += 1
            
            # Only keep users above threshold
            if quality_score >= quality_threshold:
                if username not in quality_users or quality_score > quality_users[username]["quality_score"]:
                    quality_users[username] = {
                        "username": username,
                        "quality_score": quality_score,
                        "comment_text": comment.get("text", ""),
                        "comment_quality": quality.get("quality_category", "unknown"),
                        "source": "comment"
                    }
    
    # Convert to list and sort by quality score
    users_list = list(quality_users.values())
    users_list.sort(key=lambda u: u.get("quality_score", 0), reverse=True)
    
    print(f"Comment analysis complete:")
    print(f"  - Analyzed {analyzed_count} comments")
    print(f"  - Found {len(users_list)} users above quality threshold of {quality_threshold}")
    
    # Return limited list
    return users_list[:limit]

async def enhanced_audience_collection(instagram_handle: str, limit: int = 50, quality_threshold: int = 30) -> List[Dict[str, Any]]:
    """
    A simplified approach to collect an audience that uses rule-based username analysis
    to identify real people.
    
    Args:
        instagram_handle: Instagram handle to collect audience for
        limit: Maximum number of users to return
        quality_threshold: Minimum quality score (for initial filtering)
    
    Returns:
        List of users identified as likely real people
    """
    print(f"🔍 Enhanced audience collection for @{instagram_handle}")
    print(f"  Using comment quality threshold: {quality_threshold}")
    
    # First collect users with a MUCH LOWER threshold than specified
    # to get more candidates (we'll still filter later)
    actual_threshold = max(5, quality_threshold - 25)  # Use an extremely low bar to get more candidates
    standard_users = await collect_instagram_followers(instagram_handle, limit=limit*3, quality_threshold=actual_threshold)
    
    if not standard_users or len(standard_users) < limit:
        print("Not enough users found. Trying alternate collection methods...")
        # Try hashtag-based collection as additional source with very low quality requirements
        hashtag_users = await collect_users_from_hashtags(instagram_handle, limit=limit*2)
        
        # Combine users from both sources, avoiding duplicates
        if hashtag_users:
            existing_usernames = {user.get("username") for user in standard_users}
            for user in hashtag_users:
                if user.get("username") not in existing_usernames:
                    standard_users.append(user)
                    existing_usernames.add(user.get("username"))
    
    if not standard_users:
        print("⚠️ Could not collect any users for analysis")
        return []
    
    # Extract usernames
    all_usernames = [user.get("username") for user in standard_users if user.get("username")]
    
    print(f"  - Collected {len(all_usernames)} potential users before filtering")
    
    # Use our simplified rule-based approach
    real_people_data = await identify_real_people_from_usernames(all_usernames, instagram_handle)
    
    # Create dictionary for easy lookup
    real_people_dict = {entry.get("username"): entry for entry in real_people_data}
    
    # Enhance original users with classification and filter
    enhanced_users = []
    for user in standard_users:
        username = user.get("username", "")
        if username in real_people_dict:
            # Get classification
            data = real_people_dict[username]
            user["classification"] = "likely_person"
            user["engagement_quality"] = data.get("engagement_quality", "low")
            user["reasoning"] = data.get("reasoning", "")
            enhanced_users.append(user)
    
    print(f"Enhanced audience collection complete:")
    print(f"  - Starting users: {len(standard_users)}")
    print(f"  - After rule-based filtering: {len(enhanced_users)}")
    
    # Return all users classified as real people, up to the increased limit
    return enhanced_users[:limit]

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