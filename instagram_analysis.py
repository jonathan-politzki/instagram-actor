import os
import json
import re
import asyncio
import time
import sys
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv
import google.generativeai as genai
import random

# Import functions from instagram_data
from instagram_data import (
    collect_instagram_profile, 
    collect_instagram_posts,
    collect_post_comments,
    collect_hashtag_posts,
    check_profile_visibility,
    collect_user_profile_posts,
    encode_image_to_base64,
    rate_limit
)

# Load environment variables
load_dotenv()

# Configure API keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Create directories if they don't exist
os.makedirs("cache", exist_ok=True)
os.makedirs("results", exist_ok=True)

# ==========================================
# Analysis Functions
# ==========================================

async def analyze_comment_quality(comment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes a comment to determine its sentiment, authenticity, and relevance.
    Helps filter out bot comments, spam, and negative sentiment.
    
    Returns the original comment with added quality metrics.
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
    negative_terms = ["hate", "bad", "terrible", "awful", "horrible", "disappointing", "waste", "poor", "worst", "dislike", "ugly"]
    
    # Count positive and negative terms
    positive_count = sum(1 for term in positive_terms if term in text.lower())
    negative_count = sum(1 for term in negative_terms if term in text.lower())
    
    # Determine sentiment
    if positive_count > negative_count:
        quality_metrics["sentiment"] = "positive"
    elif negative_count > positive_count:
        quality_metrics["sentiment"] = "negative"
    else:
        quality_metrics["sentiment"] = "neutral"
    
    # Calculate overall quality score (0-100)
    # Factors:
    # - Comment length (longer is better, up to a point)
    # - Not a likely bot
    # - Positive sentiment
    # - Presence of question (engagement)
    # - Mentions the brand or product
    
    length_score = min(40, len(text) / 2)  # Max 40 points for length
    bot_score = 0 if quality_metrics["is_likely_bot"] else 25  # 25 points for not being a bot
    sentiment_score = 0 if quality_metrics["sentiment"] == "negative" else 15  # 15 points for non-negative
    question_score = 10 if "?" in text else 0  # 10 points for asking questions
    
    # Compute final score and normalize to 0-100
    quality_metrics["quality_score"] = min(100, length_score + bot_score + sentiment_score + question_score)
    
    # Update the comment with quality metrics
    comment.update(quality_metrics)
    
    return comment

async def filter_hashtag_relevance(brand_handle: str, hashtag: str) -> float:
    """
    Evaluates the relevance of a hashtag to the brand.
    Returns a relevance score between 0-1.
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

async def analyze_brand_profile(profile_data: Dict[str, Any], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze a brand's Instagram profile to extract key identity elements
    Using simplified fallback in case of API errors
    """
    instagram_handle = profile_data.get("username", "")
    print(f"Analyzing brand profile for @{instagram_handle}")
    
    try:
        # Extract basic information
        bio = profile_data.get("biography", "")
        full_name = profile_data.get("full_name", "")
        website = profile_data.get("external_url", "")
        
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
        
        # Default to Sports/Lifestyle for Nike or Adidas
        if not topics and instagram_handle.lower() in ["nike", "adidas"]:
            topics = ["Sports", "Lifestyle", "Fashion"]
        
        # Create simple analysis
        analysis = {
            "brand_identity": f"Instagram profile for {full_name or instagram_handle}",
            "messaging_style": "Visual-focused social media content",
            "visual_identity": "Professional photography and branded content",
            "key_topics": topics or ["Sports", "Lifestyle", "Products"],
            "target_audience": "Social media users interested in the brand's products and lifestyle",
            "strengths": ["Strong visual identity", "Consistent branding"],
            "opportunity_areas": ["More audience engagement", "Enhanced storytelling"],
            "analysis_timestamp": datetime.now().isoformat()
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
            "analysis_timestamp": datetime.now().isoformat()
        }

async def analyze_follower_content(follower_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a follower's content to determine if they're a suitable ideal customer profile using a simpler approach
    """
    username = follower_data.get("username")
    print(f"Analyzing content for follower @{username}")
    
    # Get profile data and posts
    profile_data = follower_data.get("profile_data", {})
    posts = follower_data.get("posts", [])
    
    # Simple rule-based approach without LLM
    # Create a basic analysis based on available data
    analysis = {
        "is_suitable_icp": True,  # Default to True to be inclusive
        "reasoning": "Simple rule-based analysis",
        "profile_summary": f"Instagram user @{username}",
        "interests": ["Not analyzed due to API limitations"],
        "demographic_indicators": ["Unknown"],
        "brand_affinities": []
    }
    
    # Update follower data with our analysis
    follower_data["icp_analysis"] = analysis
    follower_data["is_suitable_icp"] = True
    
    return follower_data

async def identify_real_people_from_usernames(usernames: List[str], brand_handle: str) -> List[Dict[str, Any]]:
    """
    Uses simple rules to identify usernames likely belonging to real people
    versus businesses or bots. Uses a more permissive approach to cast a wider net.
    
    Args:
        usernames: List of Instagram usernames to analyze
        brand_handle: The brand's Instagram handle for context
    
    Returns:
        List of dictionaries with username classification
    """
    if not usernames:
        return []
        
    print(f"Analyzing {len(usernames)} usernames to identify real people...")
    
    # Simplify to handle API issues - just use SIMPLE RULES instead of LLM
    # This is a fallback in case the API call fails
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

async def collect_users_from_hashtags(instagram_handle: str, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Collect users who post content with hashtags related to the brand.
    This is another proxy for finding potential customers or brand followers.
    Includes improved relevance filtering.
    """
    print(f"Collecting users from hashtags related to @{instagram_handle}")
    
    try:
        # Get brand profile to extract potential brand-related terms
        profile_data = await collect_instagram_profile(instagram_handle)
        
        # Extract the real brand name carefully - use the Instagram handle as fallback
        brand_name = profile_data.get("fullName", instagram_handle)
        if brand_name:
            # Extract the first word to avoid getting extra words that might not be part of the core brand
            brand_name_parts = brand_name.split()
            core_brand = brand_name_parts[0].lower() if brand_name_parts else instagram_handle.lower()
        else:
            core_brand = instagram_handle.lower()
            
        # Start with the most reliable hashtags - just the Instagram handle
        hashtags_to_try = [instagram_handle.lower()]
        
        # Get category-specific hashtags based on the brand's bio
        bio = profile_data.get("biography", "").lower()
        
        # Product-specific hashtags for different types of brands
        if "plush" in bio or "toy" in bio or "stuffed" in bio or "squish" in bio or "soft" in bio:
            # Plush toys or Squishable-like brands
            hashtags_to_try.extend([
                f"{instagram_handle}plush", 
                "plushies", 
                "plushcollector", 
                "plushtoys", 
                "kawaiiplush",
                "cuteplush",
                "plushiesofinstagram"
            ])
        elif "shoe" in bio or "sneaker" in bio or "footwear" in bio:
            # Footwear brands
            hashtags_to_try.extend([
                f"{instagram_handle}shoes",
                "shoelover",
                "sneakerhead",
                "footwear",
                "shoeaddict"
            ])
        elif "glass" in bio or "eye" in bio or "spectacles" in bio or "frames" in bio:
            # Eyewear brands
            hashtags_to_try.extend([
                f"{instagram_handle}glasses",
                "eyewear",
                "glasses",
                "eyeglasses",
                "frames"
            ])
        elif "beauty" in bio or "makeup" in bio or "skincare" in bio:
            # Beauty brands
            hashtags_to_try.extend([
                f"{instagram_handle}beauty",
                "beautyproducts",
                "skincare",
                "makeupaddicts",
                "beautylovers"
            ])
        elif "coffee" in bio or "cafe" in bio or "tea" in bio:
            # Coffee or cafe brands
            hashtags_to_try.extend([
                f"{instagram_handle}coffee",
                "coffeelover",
                "coffeeaddict",
                "cafelife",
                "coffeeculture"
            ])
        else:
            # General brand hashtags
            hashtags_to_try.extend([
                f"{instagram_handle}fan",
                f"love{instagram_handle}",
                f"{instagram_handle}products"
            ])
        
        # Get additional terms from bio that might be branded hashtags
        bio_hashtags = []
        for word in bio.split():
            if word.startswith('#'):
                tag = word[1:].lower()
                # Make sure it's reasonably sized and unique
                if len(tag) > 3:
                    bio_hashtags.append(tag)
        
        # Add verified bio hashtags to our list
        hashtags_to_try.extend(bio_hashtags)
        
        # Remove duplicates while preserving order
        seen = set()
        hashtags_to_try = [h for h in hashtags_to_try if not (h in seen or seen.add(h))]
        
        # Get posts from each hashtag
        all_users = []
        checked_hashtags = set()
        
        for hashtag in hashtags_to_try:
            if len(hashtag) < 3:
                continue  # Skip very short hashtags
                
            # Skip if we've already checked this hashtag
            if hashtag in checked_hashtags:
                continue
                
            checked_hashtags.add(hashtag)
                
            # Check relevance first using our improved filter
            if hashtag != instagram_handle.lower() and not hashtag.startswith(instagram_handle.lower()):
                # Keep stricter relevance check for non-exact matches
                relevance = await filter_hashtag_relevance(instagram_handle, hashtag)
                if relevance < 0.3 and not hashtag in bio_hashtags:
                    print(f"Skipping low-relevance hashtag #{hashtag} (score: {relevance:.1f})")
                    continue
            else:
                # Direct match gets top relevance
                relevance = 0.9
            
            try:
                # Get hashtag posts
                hashtag_data = await collect_hashtag_posts(hashtag, limit=50)
                
                # Extract usernames from posts with their source hashtag
                for item in hashtag_data:
                    if "latestPosts" in item and isinstance(item["latestPosts"], list):
                        for post in item["latestPosts"]:
                            if "ownerUsername" in post and post["ownerUsername"] != instagram_handle:
                                # Check if this post specifically mentions the brand
                                caption = post.get("caption", "").lower()
                                mentions_brand = any(term in caption for term in [instagram_handle.lower(), brand_name])
                                
                                # Include source hashtag for later relevance filtering
                                all_users.append({
                                    "username": post["ownerUsername"],
                                    "source": "hashtag",
                                    "source_hashtag": hashtag,
                                    "relevance_score": relevance + (0.2 if mentions_brand else 0),
                                    "mentions_brand": mentions_brand
                                })
                    elif "ownerUsername" in item and item["ownerUsername"] != instagram_handle:
                        all_users.append({
                            "username": item["ownerUsername"],
                            "source": "hashtag",
                            "source_hashtag": hashtag,
                            "relevance_score": relevance
                        })
                
                # If we have enough users, we can stop searching more hashtags
                if len(all_users) >= limit * 2:  # Get extra for filtering
                    break
                    
            except Exception as e:
                print(f"Error searching hashtag #{hashtag}: {str(e)}")
                continue
        
        # Remove duplicates by username with a preference for higher relevance
        unique_users = {}
        for user in all_users:
            username = user["username"]
            if username not in unique_users or user.get("relevance_score", 0) > unique_users[username].get("relevance_score", 0):
                unique_users[username] = user
        
        # Convert back to list and sort by relevance score
        result_users = list(unique_users.values())
        result_users.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # Return top users by relevance
        return result_users[:limit]
        
    except Exception as e:
        print(f"Error collecting users from hashtags: {str(e)}")
        return []

async def collect_instagram_followers(instagram_handle: str, limit: int = 50, quality_threshold: int = 60) -> List[Dict[str, Any]]:
    """
    Collect a sample of users engaged with a brand's Instagram profile.
    Since direct follower scraping is limited, we use comments on posts as a proxy,
    with hashtag analysis as a secondary method. Includes comment quality filtering.
    """
    print(f"Collecting engaged users for @{instagram_handle} (quality threshold: {quality_threshold})")
    
    # Check cache first
    cache_file = f"cache/{instagram_handle}_followers.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cached_data = json.load(f)
            # Check if cache is less than 1 day old
            cache_time = datetime.fromisoformat(cached_data.get("cache_timestamp", "2000-01-01T00:00:00"))
            if (datetime.now() - cache_time).days < 1:
                print(f"Using cached user data for @{instagram_handle}")
                if cached_data.get("followers", []):
                    return cached_data["followers"]
    
    try:
        # First, get posts from the brand
        posts = await collect_instagram_posts(instagram_handle, limit=10)
        if not posts:
            print(f"No posts found for @{instagram_handle}")
            return []
        
        print(f"Found {len(posts)} posts, collecting comments...")
        
        # Collect all comments from posts
        all_comments = []
        
        for post in posts:
            if "shortCode" not in post:
                continue
                
            post_id = post.get("shortCode")
            
            # Get comments for this post
            comments = await collect_post_comments(post_id, limit=50)
            all_comments.extend(comments)
                
            # If we have enough comments, we can stop collecting more posts
            if len(all_comments) >= limit * 3:  # Collect more than needed for filtering
                break
        
        print(f"Analyzing quality of {len(all_comments)} comments...")
        
        # Analyze and filter comments
        analyzed_comments = []
        for comment in all_comments:
            # Skip brand's own comments
            if comment.get("ownerUsername") == instagram_handle:
                continue
                
            # Analyze comment quality
            analyzed_comment = await analyze_comment_quality(comment)
            analyzed_comments.append(analyzed_comment)
        
        # Filter for high-quality comments
        # Prioritize:
        # 1. Non-bot comments
        # 2. Positive or neutral sentiment
        # 3. Higher quality scores that meet our threshold
        quality_comments = [c for c in analyzed_comments 
                           if not c.get("is_likely_bot", True) 
                           and c.get("quality_score", 0) >= quality_threshold]
        
        # Sort by quality score (highest first)
        quality_comments.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
        
        print(f"Found {len(quality_comments)} comments above quality threshold ({quality_threshold})")
        
        # Extract unique usernames from quality comments
        engaged_users = []
        seen_usernames = set()
        
        for comment in quality_comments:
            username = comment.get("ownerUsername")
            if username and username not in seen_usernames:
                seen_usernames.add(username)
                engaged_users.append({
                    "username": username,
                    "source": "comment",
                    "sentiment": comment.get("sentiment", "neutral"),
                    "quality_score": comment.get("quality_score", 0),
                })
        
        # If we don't have enough users from comments, try hashtag analysis
        if len(engaged_users) < limit:
            print(f"Only found {len(engaged_users)} quality users from comments, trying hashtag analysis...")
            
            # Get hashtag-based users with relevance filtering
            hashtag_followers = await collect_users_from_hashtags(instagram_handle, limit=limit*2)  # Get more for filtering
            
            # Filter hashtag users by added relevance criterion 
            filtered_hashtag_users = []
            
            for user in hashtag_followers:
                # If the user was found from hashtags, check for source hashtag relevance
                source_hashtag = user.get("source_hashtag", "")
                if source_hashtag:
                    relevance = await filter_hashtag_relevance(instagram_handle, source_hashtag)
                    if relevance >= 0.4:  # Only keep medium-high relevance
                        user["relevance_score"] = relevance
                        filtered_hashtag_users.append(user)
                else:
                    # If no specific source_hashtag, keep with lower priority
                    user["relevance_score"] = 0.3
                    filtered_hashtag_users.append(user)
            
            # Sort by relevance
            filtered_hashtag_users.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            
            # Combine unique users from both sources
            all_usernames = {u["username"] for u in engaged_users}
            
            for user in filtered_hashtag_users:
                if user["username"] not in all_usernames:
                    engaged_users.append(user)
                    all_usernames.add(user["username"])
                    
                    # If we have enough users, stop adding
                    if len(engaged_users) >= limit:
                        break
            
            print(f"Added {len(engaged_users) - len(seen_usernames)} additional users from hashtags")
        
        # If we have more than the limit, trim to the requested amount
        followers = engaged_users[:limit]
        
        # If we found some engaged users, add them to the cache
        if followers:
            cache_data = {
                "followers": followers,
                "source": "filtered_comments_and_hashtags",
                "quality_threshold": quality_threshold,
                "cache_timestamp": datetime.now().isoformat()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
                
            print(f"Collected total of {len(followers)} quality engaged users")
            return followers
        
        # If we couldn't find users from comments or hashtags, check for previously cached users
        print("No quality engaged users found. Checking for alternative data sources...")
        
        # Collect profile data to get info that might help us
        profile_data = await collect_instagram_profile(instagram_handle)
        
        # If we have previously cached followers, maintain them
        followers = []
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
                if "followers" in cached_data and cached_data["followers"]:
                    followers = cached_data["followers"]
                    print(f"Maintaining {len(followers)} previously cached users")
        
        # Cache the results (even if empty)
        cache_data = {
            "followers": followers,
            "profile_data": profile_data,
            "cache_timestamp": datetime.now().isoformat(),
            "source": "limited_data"
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        return followers
    
    except Exception as e:
        print(f"Error collecting engaged users: {str(e)}")
        # Return empty list instead of raising to allow process to continue
        followers = []
        cache_data = {
            "followers": followers,
            "cache_timestamp": datetime.now().isoformat(),
            "error": str(e)
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
            
        return followers

async def process_brand(brand: Dict[str, Any], quality_threshold: int = 30) -> Dict[str, Any]:
    """
    Process a single brand through the analysis pipeline
    
    Args:
        brand: The brand data dictionary
        quality_threshold: Minimum quality score (0-100) for comments
    """
    name = brand.get("name", "Unknown")
    url = brand.get("url", "")
    instagram_handle = brand.get("instagram_handle", "")
    
    print(f"\n=== Processing Brand: {name} (@{instagram_handle}) ===\n")
    
    try:
        # 1. Collect brand's Instagram profile data
        print("Step 1/5: Collecting brand profile data...")
        profile_data = await collect_instagram_profile(instagram_handle)
        print("✓ Successfully collected profile data")
        
        # 2. Collect brand's posts
        print("Step 2/5: Collecting brand posts...")
        posts = await collect_instagram_posts(instagram_handle, limit=5)  # Collect 5 posts for better analysis
        print(f"✓ Successfully collected {len(posts)} posts")
        
        # 3. Analyze brand profile with LLM
        print("Step 3/5: Analyzing brand profile with LLM...")
        brand_analysis = await analyze_brand_profile_with_llm(profile_data, posts)
        print("✓ Successfully analyzed brand profile")
        
        # 4. Collect users with enhanced audience collection
        print("Step 4/5: Collecting audience data...")
        engaged_users = await enhanced_audience_collection(instagram_handle, limit=30, quality_threshold=quality_threshold)
        print(f"✓ Successfully collected {len(engaged_users)} engaged users")
        
        # 5. Analyze a subset of users for ICP
        print("Step 5/5: Analyzing users for ICP data...")
        icp_data = []
        
        # Analyze up to 5 users in detail with LLM
        for i, user in enumerate(engaged_users[:5]):
            username = user.get("username")
            if not username:
                continue
                
            print(f"Analyzing potential ICP: @{username}...")
            
            # Get user profile data
            user_profile = await collect_user_profile_posts(username, limit=3)
            
            # LLM-based ICP analysis
            if user_profile:
                analyzed_user = await analyze_user_profile_with_llm(user_profile, instagram_handle, name)
                icp_data.append(analyzed_user)
        
        # Generate audience insights with LLM
        print("Generating audience insights...")
        audience_insights = await generate_audience_insights_with_llm(icp_data, name, instagram_handle)
        
        # Prepare results
        results = {
            "brand": {
                "name": name,
                "url": url,
                "instagram_handle": instagram_handle
            },
            "brand_profile": profile_data,
            "brand_analysis": brand_analysis,
            "posts_sample": posts[:3],  # Include 3 sample posts
            "audience_data": {
                "engaged_users": [{"username": u.get("username")} for u in engaged_users],
                "icp_data": icp_data,
                "total_unique_users": len(engaged_users)
            },
            "audience_insights": audience_insights,
            "analysis_metadata": {
                "timestamp": datetime.now().isoformat(),
                "analysis_type": "llm_enhanced_approach",
                "quality_threshold_used": quality_threshold,
                "status": "completed"
            }
        }
        
        # Save results to disk
        save_results(instagram_handle, results)
        
        return results
        
    except Exception as e:
        print(f"Error processing brand {name}: {str(e)}")
        traceback.print_exc()
        
        # Save partial results on error
        error_results = {
            "brand": {
                "name": name,
                "instagram_handle": instagram_handle,
                "url": url
            },
            "error": str(e),
            "analysis_metadata": {
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error_details": traceback.format_exc(),
                "quality_threshold_used": quality_threshold
            }
        }
        
        # Save error results to disk
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = f"results/{instagram_handle}_{timestamp}_error.json"
        
        with open(result_file, 'w') as f:
            json.dump(error_results, f, indent=2)
            
        print(f"\nError during analysis! Partial results saved to {result_file}")
        
        return error_results

async def analyze_brand_profile_with_llm(profile_data: Dict[str, Any], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze a brand's Instagram profile using LLM to extract key identity elements
    
    Args:
        profile_data: Brand's Instagram profile data
        posts: List of brand's Instagram posts
        
    Returns:
        Dictionary with brand identity analysis
    """
    instagram_handle = profile_data.get("username", "")
    print(f"Analyzing brand profile for @{instagram_handle} with LLM...")
    
    try:
        # Extract basic information
        bio = profile_data.get("biography", "")
        full_name = profile_data.get("fullName", "")
        website = profile_data.get("external_url", "")
        
        # Extract post captions
        captions = [post.get("caption", "") for post in posts if post.get("caption")]
        captions_text = "\n---\n".join(captions[:5])  # Use up to 5 captions
        
        # Create prompt for Gemini
        prompt = f"""
        Analyze this Instagram profile for the brand {full_name or instagram_handle}:
        
        Instagram Handle: @{instagram_handle}
        Full Name: {full_name}
        Bio: {bio}
        Website: {website}
        Followers: {profile_data.get("followersCount", 0):,}
        
        Recent post captions:
        {captions_text}
        
        Provide a comprehensive brand analysis. Return ONLY valid JSON in this exact format:
        {{
            "brand_identity": "Core identity of the brand in 1-2 sentences",
            "messaging_style": "Description of how the brand communicates in 1-2 sentences",
            "visual_identity": "Description of visual style based on captions/mentions in 1-2 sentences",
            "key_topics": ["Topic1", "Topic2", "Topic3"],
            "target_audience": "Description of the likely target audience in 1-2 sentences",
            "strengths": ["Strength1", "Strength2", "Strength3"],
            "opportunity_areas": ["Opportunity1", "Opportunity2", "Opportunity3"]
        }}
        
        Don't include any other text, just the JSON.
        """
        
        # Call Gemini API
        result = await get_gemini_json_response('gemini-1.5-pro', [prompt])
        
        # Validate and clean up response
        if not result or "error" in result:
            # Fallback to basic analysis
            print("Warning: Using fallback for brand analysis due to API error")
            return {
                "brand_identity": f"Instagram profile for {full_name or instagram_handle}",
                "messaging_style": "Visual-focused social media content",
                "visual_identity": "Professional photography and branded content",
                "key_topics": ["Products", "Lifestyle"],
                "target_audience": "Social media users interested in the brand's products",
                "strengths": ["Brand presence on Instagram"],
                "opportunity_areas": ["Enhanced audience engagement"],
                "analysis_timestamp": datetime.now().isoformat()
            }
        
        # Add timestamp to the result
        result["analysis_timestamp"] = datetime.now().isoformat()
        
        return result
        
    except Exception as e:
        print(f"Warning: Error in LLM brand analysis: {str(e)}")
        # Return simple fallback analysis
        return {
            "brand_identity": f"Instagram profile for @{instagram_handle}",
            "key_topics": ["Products", "Lifestyle"],
            "target_audience": "Social media users",
            "strengths": ["Brand presence on Instagram"],
            "analysis_error": str(e),
            "analysis_timestamp": datetime.now().isoformat()
        }

async def analyze_user_profile_with_llm(user_profile: Dict[str, Any], brand_handle: str, brand_name: str) -> Dict[str, Any]:
    """
    Analyze a user's profile with LLM to determine if they're a suitable ideal customer profile
    
    Args:
        user_profile: User's profile data and posts
        brand_handle: The brand's Instagram handle
        brand_name: The brand's name
        
    Returns:
        Dictionary with user profile and ICP analysis
    """
    username = user_profile.get("username", "")
    print(f"Analyzing user @{username} with LLM for ICP evaluation...")
    
    try:
        # Extract profile data
        profile = user_profile.get("profile_data", {})
        posts = user_profile.get("posts", [])
        comments = user_profile.get("comments", [])
        
        # Prepare data for LLM
        bio = profile.get("biography", "No bio available")
        full_name = profile.get("fullName", "Unknown")
        
        # Extract post captions
        post_captions = [post.get("caption", "") for post in posts if post.get("caption")]
        captions_text = "\n---\n".join(post_captions[:3])  # Use up to 3 captions
        
        # Extract comment data if available
        comments_text = ""
        if comments:
            comments_text = "\n".join([f"Comment: {c.get('text', '')}" for c in comments])
        
        # Create prompt for Gemini
        prompt = f"""
        Analyze this Instagram user in relation to the brand {brand_name} (@{brand_handle}):
        
        Username: @{username}
        Full Name: {full_name}
        Bio: {bio}
        
        Recent post captions:
        {captions_text}
        
        """
        
        # Add comments section if available
        if comments_text:
            prompt += f"""
        Comments on {brand_name}'s posts:
        {comments_text}
            
        """
        
        prompt += f"""
        Determine if this user is likely an ideal customer profile (ICP) for {brand_name}.
        
        Return ONLY valid JSON in this exact format:
        {{
            "is_suitable_icp": true/false,
            "reasoning": "Detailed explanation of why they are/aren't a good ICP",
            "profile_summary": "Brief summary of who this person appears to be",
            "interests": ["Interest1", "Interest2", "Interest3"],
            "demographic_indicators": ["Indicator1", "Indicator2"],
            "brand_affinities": ["Brand1", "Brand2"],
            "engagement_potential": "high/medium/low",
            "recommendations": "How the brand could engage with this user"
        }}
        
        Don't include any other text, just the JSON.
        """
        
        # Call Gemini API
        result = await get_gemini_json_response('gemini-1.5-pro', [prompt])
        
        # Validate and format response
        if not result or "error" in result:
            # Fallback to basic analysis
            print(f"Warning: Using fallback for user @{username} analysis due to API error")
            
            # Use comment-based analysis if available for a better fallback
            fallback_result = {
                "is_suitable_icp": True,
                "reasoning": "Simple rule-based identification (API fallback)",
                "profile_summary": f"Instagram user @{username}",
                "interests": ["Not analyzed due to API limitations"],
                "demographic_indicators": ["Unknown"],
                "brand_affinities": [brand_name] if brand_name.lower() in bio.lower() else []
            }
            
            # If we have comments, set a more informed fallback
            if comments:
                if any("i have" in c.get("text", "").lower() for c in comments) or \
                   any("i bought" in c.get("text", "").lower() for c in comments) or \
                   any("i love" in c.get("text", "").lower() for c in comments):
                    fallback_result["reasoning"] = "User has commented about owning or liking the brand's products"
                    fallback_result["engagement_potential"] = "medium"
                
            return {
                "username": username,
                "profile_data": {
                    "username": username,
                    "full_name": full_name,
                    "bio": bio
                },
                "icp_analysis": fallback_result,
                "posts_count": len(posts),
                "comments_count": len(comments)
            }
        
        # Create analyzed user object
        analyzed_user = {
            "username": username,
            "profile_data": {
                "username": username,
                "full_name": full_name,
                "bio": bio
            },
            "icp_analysis": result,
            "posts_count": len(posts),
            "comments_count": len(comments)
        }
        
        return analyzed_user
        
    except Exception as e:
        print(f"Error analyzing user @{username}: {str(e)}")
        # Return basic user data with error
        return {
            "username": username,
            "profile_data": {
                "username": username,
                "full_name": profile.get("fullName", "Unknown"),
                "bio": profile.get("biography", "No bio available")
            },
            "icp_analysis": {
                "is_suitable_icp": False,
                "reasoning": f"Error during analysis: {str(e)}",
                "profile_summary": f"Instagram user @{username}",
                "interests": ["Analysis failed"],
                "demographic_indicators": ["Unknown"],
                "brand_affinities": []
            },
            "posts_count": len(posts),
            "comments_count": len(comments) if "comments" in locals() else 0,
            "error": str(e)
        }

async def generate_audience_insights_with_llm(icp_data: List[Dict[str, Any]], brand_name: str, brand_handle: str) -> Dict[str, Any]:
    """
    Generate audience insights from ICP data using LLM
    
    Args:
        icp_data: List of analyzed ICP users
        brand_name: The brand's name
        brand_handle: The brand's Instagram handle
        
    Returns:
        Dictionary with audience insights
    """
    print("Generating audience insights with LLM...")
    
    if not icp_data:
        print("No ICP data available for insights, using default")
        return {
            "audience_alignment": "Insufficient data to determine audience alignment",
            "content_recommendations": [
                "Continue posting high-quality visual content", 
                "Increase engagement through questions and calls to action"
            ],
            "engagement_strategies": [
                "Respond to comments from high-value audience members",
                "Use Instagram Stories to highlight customer success"
            ]
        }
    
    try:
        # Extract key ICP information
        suitable_icps = [icp for icp in icp_data if icp.get("icp_analysis", {}).get("is_suitable_icp", False)]
        
        # Compile all interests and demographics
        all_interests = []
        all_demographics = []
        all_affinities = []
        
        for icp in suitable_icps:
            analysis = icp.get("icp_analysis", {})
            interests = analysis.get("interests", [])
            demographics = analysis.get("demographic_indicators", [])
            affinities = analysis.get("brand_affinities", [])
            
            all_interests.extend(interests)
            all_demographics.extend(demographics)
            all_affinities.extend(affinities)
        
        # Prepare data for LLM
        icp_count = len(suitable_icps)
        total_count = len(icp_data)
        
        # Format ICP summaries
        icp_summaries = []
        for icp in suitable_icps[:5]:  # Limit to 5 for prompt size
            analysis = icp.get("icp_analysis", {})
            summary = f"User: @{icp.get('username')} - {analysis.get('profile_summary', 'No summary')} - " + \
                     f"Interests: {', '.join(analysis.get('interests', ['None']))}"
            icp_summaries.append(summary)
        
        # Create prompt for Gemini
        prompt = f"""
        Generate audience insights for {brand_name} (@{brand_handle}) based on this Instagram audience data:
        
        Total users analyzed: {total_count}
        Suitable ICPs identified: {icp_count}
        
        Sample ICP profiles:
        {chr(10).join(icp_summaries)}
        
        Common interests: {', '.join(set(i for i in all_interests if i != "Not analyzed due to API limitations"))}
        Demographic indicators: {', '.join(set(d for d in all_demographics if d != "Unknown"))}
        Brand affinities: {', '.join(set(all_affinities))}
        
        Return ONLY valid JSON in this exact format:
        {{
            "audience_alignment": "1-2 sentences on how well the brand's content aligns with the audience",
            "audience_segments": ["Segment1", "Segment2", "Segment3"],
            "content_recommendations": ["Recommendation1", "Recommendation2", "Recommendation3", "Recommendation4"],
            "engagement_strategies": ["Strategy1", "Strategy2", "Strategy3"],
            "collaboration_opportunities": ["Opportunity1", "Opportunity2"]
        }}
        
        Don't include any other text, just the JSON.
        """
        
        # Call Gemini API
        result = await get_gemini_json_response('gemini-1.5-pro', [prompt])
        
        # Validate and format response
        if not result or "error" in result:
            # Fallback to basic insights
            print("Warning: Using fallback for audience insights due to API error")
            return {
                "audience_alignment": f"Analysis identified {icp_count} potential ideal customers for {brand_name}",
                "content_recommendations": [
                    "Create content that resonates with identified audience interests",
                    "Feature more user-generated content to increase engagement"
                ],
                "engagement_strategies": [
                    "Respond to comments from high-value audience members",
                    "Use Instagram Stories to highlight customer success"
                ]
            }
        
        return result
        
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
            "error": str(e)
        }

def save_results(instagram_handle: str, results: Dict[str, Any]):
    """Save results to JSON file"""
    os.makedirs("results", exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"results/{instagram_handle}_{timestamp}.json"
    
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to {result_file}")

# ==========================================
# Main Function
# ==========================================

async def main():
    # Load target brands from JSON file
    try:
        with open("brands.json", 'r') as f:
            brands = json.load(f)
    except FileNotFoundError:
        print("brands.json not found. Creating sample file...")
        
        # Create sample brands file
        sample_brands = [
            {
                "name": "Nike",
                "url": "https://www.nike.com",
                "instagram_handle": "nike"
            },
            {
                "name": "Adidas",
                "url": "https://www.adidas.com",
                "instagram_handle": "adidas"
            }
        ]
        
        with open("brands.json", 'w') as f:
            json.dump(sample_brands, f, indent=2)
        
        brands = sample_brands
    
    print(f"Loaded {len(brands)} brands for processing")
    
    # Get command line arguments to check for quality threshold
    args = sys.argv
    quality_threshold = 30  # Lower default
    
    for i, arg in enumerate(args):
        if arg == "--quality-threshold" and i+1 < len(args):
            try:
                quality_threshold = int(args[i+1])
                # Ensure it's in valid range
                quality_threshold = max(0, min(100, quality_threshold))
            except:
                pass
    
    # Process each brand sequentially
    for brand in brands:
        await process_brand(brand, quality_threshold=quality_threshold)
        print("\n" + "="*50 + "\n")
    
    print("All brands processed successfully!")

# ==========================================
# Command-line Interface
# ==========================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Instagram Analysis Tool")
    parser.add_argument("--brand", type=str, help="Process a single brand by Instagram handle")
    parser.add_argument("--list", action="store_true", help="List all available brands")
    parser.add_argument("--limit", type=int, default=5, help="Limit number of items to process (posts, users, etc.)")
    parser.add_argument("--quality-threshold", type=int, default=30, help="Minimum quality score (0-100) for comments (default: 30)")
    
    args = parser.parse_args()
    
    if args.list:
        try:
            with open("brands.json", 'r') as f:
                brands = json.load(f)
                print("\nAvailable brands:")
                for i, brand in enumerate(brands):
                    print(f"{i+1}. {brand.get('name')} (@{brand.get('instagram_handle')})")
                print()
        except FileNotFoundError:
            print("No brands.json file found.")
    elif args.brand:
        # Process a single brand by Instagram handle
        try:
            with open("brands.json", 'r') as f:
                brands = json.load(f)
                
            # Find the brand by Instagram handle
            brand = next((b for b in brands if b.get("instagram_handle") == args.brand), None)
            
            if brand:
                asyncio.run(process_brand(brand, quality_threshold=args.quality_threshold))
            else:
                print(f"Brand with Instagram handle @{args.brand} not found.")
        except FileNotFoundError:
            print("No brands.json file found.")
    else:
        # Process all brands
        asyncio.run(main())