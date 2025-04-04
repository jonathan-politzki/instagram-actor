import os
import json
import base64
import random
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv
import google.generativeai as genai
from apify_client import ApifyClient
import requests
from PIL import Image
from io import BytesIO
from tqdm.asyncio import tqdm_asyncio
import sys
import re

# Load environment variables
load_dotenv()

# Configure API keys
APIFY_API_KEY = os.getenv("APIFY_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Apify client
apify_client = ApifyClient(APIFY_API_KEY)

# Create directories
os.makedirs("cache", exist_ok=True)
os.makedirs("results", exist_ok=True)

# Rate limiting settings
LAST_API_CALL = {}  # Store timestamps of last API calls

async def rate_limit(api_name: str, min_delay_seconds: float = 1.0):
    """
    Implement rate limiting for API calls to prevent hitting rate limits
    """
    now = time.time()
    last_call = LAST_API_CALL.get(api_name, 0)
    elapsed = now - last_call
    
    if elapsed < min_delay_seconds:
        delay = min_delay_seconds - elapsed
        print(f"Rate limiting: waiting {delay:.2f}s for {api_name} API")
        await asyncio.sleep(delay)
    
    LAST_API_CALL[api_name] = time.time()

# ==========================================
# Data Collection Functions
# ==========================================

async def collect_instagram_profile(instagram_handle: str) -> Dict[str, Any]:
    """
    Collect Instagram profile data for a Shopify store
    """
    print(f"Collecting Instagram profile for @{instagram_handle}")
    
    # Check cache first
    cache_file = f"cache/{instagram_handle}_profile.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cached_data = json.load(f)
            # Check if cache is less than 1 day old
            cache_time = datetime.fromisoformat(cached_data.get("cache_timestamp", "2000-01-01T00:00:00"))
            if (datetime.now() - cache_time).days < 1:
                print(f"Using cached profile data for @{instagram_handle}")
                return cached_data
    
    try:
        # Apply rate limiting
        await rate_limit("instagram_profile", 2.0)
        
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
                        businessCategory: $.business_category_name
                    }
                }
            """
        }
        
        run = apify_client.actor("apify/instagram-profile-scraper").call(run_input=run_input)
        items = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
        
        if not items:
            raise Exception(f"No profile data found for @{instagram_handle}")
        
        profile_data = items[0]
        profile_data["cache_timestamp"] = datetime.now().isoformat()
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump(profile_data, f, indent=2)
        
        return profile_data
    
    except Exception as e:
        print(f"Error collecting Instagram profile: {str(e)}")
        raise

async def collect_instagram_posts(instagram_handle: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Collect Instagram posts for a Shopify store
    """
    print(f"Collecting Instagram posts for @{instagram_handle}")
    
    # Check cache first
    cache_file = f"cache/{instagram_handle}_posts.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cached_data = json.load(f)
            # Check if cache is less than 1 day old
            cache_time = datetime.fromisoformat(cached_data.get("cache_timestamp", "2000-01-01T00:00:00"))
            if (datetime.now() - cache_time).days < 1:
                print(f"Using cached posts data for @{instagram_handle}")
                return cached_data["posts"]
    
    try:
        # Apply rate limiting
        await rate_limit("instagram_posts", 2.0)
        
        # Run the Instagram posts scraper actor
        run_input = {
            "usernames": [instagram_handle],
            "resultsType": "posts",
            "resultsLimit": limit,
            "addParentData": False
        }
        
        run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input)
        posts = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
        
        # Cache the results
        cache_data = {
            "posts": posts,
            "cache_timestamp": datetime.now().isoformat()
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        return posts
    
    except Exception as e:
        print(f"Error collecting Instagram posts: {str(e)}")
        raise

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
        brand_name = profile_data.get("fullName", "").lower().replace(" ", "")
        
        # First try an exact match hashtag
        hashtags_to_try = [instagram_handle.lower()]
        
        # Add brand name if different from handle
        if brand_name and brand_name != instagram_handle.lower():
            hashtags_to_try.append(brand_name)
        
        # Get additional terms from bio that might be branded hashtags
        bio = profile_data.get("biography", "")
        bio_hashtags = []
        for word in bio.split():
            if word.startswith('#'):
                tag = word[1:].lower()
                if len(tag) > 3:  # Only reasonably sized tags
                    bio_hashtags.append(tag)
        
        # Add bio hashtags to our list
        hashtags_to_try.extend(bio_hashtags)
        
        # Also add common suffix/prefix patterns
        if brand_name:
            hashtags_to_try.extend([
                f"{brand_name}life",
                f"{brand_name}style",
                f"{brand_name}fan",
                f"love{brand_name}"
            ])
        
        # Get posts from each hashtag
        all_users = []
        
        for hashtag in hashtags_to_try:
            if len(hashtag) < 3:
                continue  # Skip very short hashtags
                
            # Check relevance first
            relevance = await filter_hashtag_relevance(instagram_handle, hashtag)
            if relevance < 0.3:
                print(f"Skipping low-relevance hashtag #{hashtag} (score: {relevance:.1f})")
                continue
                
            try:
                # Apply rate limiting
                await rate_limit("instagram_hashtags", 5.0)  # Longer delay for hashtag searches
                
                print(f"Searching hashtag #{hashtag} (relevance: {relevance:.1f})...")
                
                # Call the hashtag scraper
                run_input = {
                    "hashtags": [hashtag],
                    "resultsLimit": 50  # Limit posts per hashtag
                }
                
                run = apify_client.actor("apify/instagram-hashtag-scraper").call(run_input=run_input, timeout_secs=60)
                hashtag_data = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
                
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
    
    Args:
        instagram_handle: The Instagram handle to collect followers for
        limit: Maximum number of users to collect
        quality_threshold: Minimum quality score (0-100) for comments
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
            
            # Apply rate limiting
            await rate_limit("instagram_comments", 3.0)
            
            # Get comments for this post using the Instagram Comment Scraper
            try:
                run_input = {
                    "directUrls": [f"https://www.instagram.com/p/{post_id}/"],
                    "resultsLimit": 50  # Get a reasonable number of comments per post
                }
                
                run = apify_client.actor("apify/instagram-comment-scraper").call(run_input=run_input, timeout_secs=60)
                comments = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
                all_comments.extend(comments)
                
                # If we have enough comments, we can stop collecting more posts
                if len(all_comments) >= limit * 3:  # Collect more than needed for filtering
                    break
                    
            except Exception as e:
                print(f"Error collecting comments for post {post_id}: {str(e)}")
                continue
        
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

async def analyze_follower_profile(username: str) -> Dict[str, Any]:
    """
    Analyze a single follower's profile to determine if they're a good candidate for ICP
    """
    print(f"Analyzing follower profile: @{username}")
    
    # Check cache first
    cache_file = f"cache/{username}_profile.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cached_data = json.load(f)
            # Check if cache is less than 1 day old
            cache_time = datetime.fromisoformat(cached_data.get("cache_timestamp", "2000-01-01T00:00:00"))
            if (datetime.now() - cache_time).days < 1:
                print(f"Using cached profile data for @{username}")
                return cached_data
    
    try:
        # Apply rate limiting for profile API
        await rate_limit("follower_profile", 2.5)
        
        # First check if profile is public
        profile_run_input = {
            "usernames": [username],
            "resultsType": "details"
        }
        
        profile_run = apify_client.actor("apify/instagram-profile-scraper").call(run_input=profile_run_input)
        profile_items = list(apify_client.dataset(profile_run["defaultDatasetId"]).iterate_items())
        
        if not profile_items:
            # Profile not found or inaccessible
            result = {
                "username": username, 
                "is_private": True, 
                "is_valid_icp": False, 
                "reason": "Profile not found or inaccessible",
                "cache_timestamp": datetime.now().isoformat(),
                "error_type": "profile_not_found"
            }
            with open(cache_file, 'w') as f:
                json.dump(result, f, indent=2)
            return result
        
        profile_data = profile_items[0]
        
        # Check if profile is private
        if profile_data.get("is_private", True):
            profile_result = {
                "username": username,
                "is_private": True,
                "is_valid_icp": False,
                "reason": "Private profile",
                "cache_timestamp": datetime.now().isoformat(),
                "error_type": "private_profile"
            }
            
            with open(cache_file, 'w') as f:
                json.dump(profile_result, f, indent=2)
                
            return profile_result
            
        # Apply rate limiting for posts API
        await rate_limit("follower_posts", 2.5)
        
        # If profile is public, get their posts
        posts_run_input = {
            "usernames": [username],
            "resultsType": "posts",
            "resultsLimit": 10,
            "addParentData": False
        }
        
        posts_run = apify_client.actor("apify/instagram-scraper").call(run_input=posts_run_input)
        posts = list(apify_client.dataset(posts_run["defaultDatasetId"]).iterate_items())
        
        # Check if they have enough posts
        if len(posts) < 5:
            profile_result = {
                "username": username,
                "is_private": False,
                "posts_count": len(posts),
                "is_valid_icp": False,
                "reason": "Not enough posts (minimum 5)",
                "profile_data": profile_data,
                "cache_timestamp": datetime.now().isoformat(),
                "error_type": "insufficient_posts"
            }
            
            with open(cache_file, 'w') as f:
                json.dump(profile_result, f, indent=2)
                
            return profile_result
        
        # Filter out posts without captions or images
        valid_posts = []
        for post in posts:
            if post.get("caption") or post.get("displayUrl"):
                valid_posts.append(post)
                
        # Check if they have enough usable posts
        if len(valid_posts) < 3:
            profile_result = {
                "username": username,
                "is_private": False,
                "posts_count": len(posts),
                "valid_posts_count": len(valid_posts),
                "is_valid_icp": False,
                "reason": "Not enough posts with content (minimum 3)",
                "profile_data": profile_data,
                "cache_timestamp": datetime.now().isoformat(),
                "error_type": "insufficient_valid_posts"
            }
            
            with open(cache_file, 'w') as f:
                json.dump(profile_result, f, indent=2)
                
            return profile_result
        
        # Profile has enough public content for analysis
        profile_result = {
            "username": username,
            "is_private": False,
            "posts_count": len(posts),
            "valid_posts_count": len(valid_posts),
            "is_valid_icp": True,
            "profile_data": profile_data,
            "posts": valid_posts[:10],  # Limit to 10 posts
            "cache_timestamp": datetime.now().isoformat()
        }
        
        with open(cache_file, 'w') as f:
            json.dump(profile_result, f, indent=2)
            
        return profile_result
    
    except Exception as e:
        print(f"Error analyzing follower profile @{username}: {str(e)}")
        error_result = {
            "username": username,
            "is_valid_icp": False,
            "error": str(e),
            "reason": "Error analyzing profile",
            "cache_timestamp": datetime.now().isoformat(),
            "error_type": "api_error"
        }
        
        with open(cache_file, 'w') as f:
            json.dump(error_result, f, indent=2)
            
        return error_result

# ==========================================
# Analysis Functions
# ==========================================

def encode_image_to_base64(image_url: str) -> Optional[str]:
    """
    Download and encode image to base64 for Gemini Vision API
    """
    if not image_url:
        return None
        
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            response = requests.get(image_url, timeout=15)
            response.raise_for_status()
            
            # Check if content is actually an image
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                print(f"Warning: URL {image_url} returned non-image content type: {content_type}")
                # Continue anyway, as Instagram sometimes has incorrect Content-Type headers
            
            # Verify it's an actual image by trying to open it
            try:
                img = Image.open(BytesIO(response.content))
                img.verify()  # Verify it's an image
                
                # If image is too large, resize it to reduce payload size
                img = Image.open(BytesIO(response.content))  # Need to reopen after verify
                max_dimension = 1024
                if img.width > max_dimension or img.height > max_dimension:
                    # Calculate new dimensions while preserving aspect ratio
                    if img.width > img.height:
                        new_width = max_dimension
                        new_height = int(img.height * (max_dimension / img.width))
                    else:
                        new_height = max_dimension
                        new_width = int(img.width * (max_dimension / img.height))
                    
                    # Resize image
                    img = img.resize((new_width, new_height), Image.LANCZOS)
                    
                    # Save to a new BytesIO object
                    img_bytes = BytesIO()
                    img.save(img_bytes, format=img.format or 'JPEG')
                    img_bytes.seek(0)
                    
                    # Return base64 of resized image
                    return base64.b64encode(img_bytes.read()).decode('utf-8')
                
                # If no resize needed, return original image
                return base64.b64encode(response.content).decode('utf-8')
                
            except Exception as img_error:
                print(f"Error verifying image from {image_url}: {str(img_error)}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image from {image_url} (attempt {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                # Increase delay for next retry
                retry_delay *= 2
            else:
                return None
    
    return None

async def analyze_brand_profile(profile_data: Dict[str, Any], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze the brand's Instagram profile and posts to determine brand identity
    """
    print(f"Analyzing brand profile for @{profile_data.get('username')}")
    
    # Prepare content for Gemini
    content_parts = [
        f"""Analyze this ecommerce store's Instagram profile as a marketing consultant. Identify:
        1. Brand voice and messaging style
        2. Core product categories and focus
        3. Visual aesthetic and design preferences
        4. Target audience characteristics
        5. Key topics and themes in their content
        
        Instagram Profile:
        Username: {profile_data.get('username', '')}
        Full Name: {profile_data.get('fullName', '')}
        Bio: {profile_data.get('biography', '')}
        Followers: {profile_data.get('followersCount', 0)}
        Business Category: {profile_data.get('businessCategory', 'N/A')}
        
        Provide your analysis in JSON format:
        {{
            "brand_identity": "Comprehensive description of the brand's identity",
            "messaging_style": "Analysis of their communication style",
            "visual_identity": "Description of their visual aesthetic",
            "key_topics": ["Topic 1", "Topic 2", "Topic 3"],
            "apparent_target_audience": "Description of their target audience",
            "strengths": ["Strength 1", "Strength 2"],
            "opportunity_areas": ["Opportunity 1", "Opportunity 2"]
        }}
        
        Respond ONLY with valid JSON. No additional text.
        """
    ]
    
    # Add post captions and images
    for i, post in enumerate(posts[:5]):  # Limit to 5 posts for analysis
        caption = post.get("caption", "")
        display_url = post.get("displayUrl")
        
        if display_url:
            # Add image to content parts
            image_base64 = encode_image_to_base64(display_url)
            if image_base64:
                content_parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                })
        
        # Add post metadata
        content_parts.append(f"""
        Post {i+1} Caption: {caption}
        Likes: {post.get("likesCount", 0)}
        Comments: {post.get("commentsCount", 0)}
        """)
    
    try:
        # Use our helper function to get a JSON response from Gemini
        analysis = await get_gemini_json_response('gemini-pro', content_parts)
        
        # Check if there was an error
        if "error" in analysis:
            print(f"Warning: Error in brand analysis: {analysis.get('error')}")
            
            # Create a fallback analysis
            analysis = {
                "brand_identity": "Could not analyze brand identity due to API error",
                "messaging_style": "Unknown due to error",
                "visual_identity": "Unknown due to error",
                "key_topics": [],
                "apparent_target_audience": "Unknown due to error",
                "strengths": [],
                "opportunity_areas": ["Retry analysis with fewer images or different content"]
            }
        
        return analysis
    
    except Exception as e:
        print(f"Error analyzing brand profile: {str(e)}")
        return {"error": str(e)}

async def analyze_follower_content(follower_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a follower's content to determine if they're a suitable ideal customer profile
    """
    username = follower_data.get("username")
    print(f"Analyzing content for follower @{username}")
    
    # If not a valid ICP candidate, return early
    if not follower_data.get("is_valid_icp", False):
        return follower_data
    
    # Get profile data and posts
    profile_data = follower_data.get("profile_data", {})
    posts = follower_data.get("posts", [])
    
    # Prepare content parts for Gemini
    content_parts = [
        f"""Analyze this Instagram user @{username} to determine if they would make a good "ideal customer profile" (ICP) for an e-commerce brand. 
        
        An ICP should:
        1. Have substantial personal content (not just food/pets/memes)
        2. Reveal demographic information and interests
        3. Show consistent lifestyle patterns
        4. Demonstrate shopping behaviors or brand affinities
        
        First, evaluate if this is a suitable ICP based on their content. Then, if suitable, provide a detailed persona.
        
        Respond with ONLY valid JSON in this format:
        {{
          "is_suitable_icp": true/false,
          "reasoning": "Explanation of why they are or aren't suitable",
          "profile_summary": "If suitable, a summary of who this person is",
          "demographic_indicators": ["Age range", "Location", "Gender", "Other factors"],
          "interests": ["Interest 1", "Interest 2", "Interest 3"],
          "lifestyle_patterns": ["Pattern 1", "Pattern 2"],
          "brand_affinities": ["Brand 1", "Brand 2"],
          "shopping_behaviors": ["Behavior 1", "Behavior 2"]
        }}
        """
    ]
    
    # Add profile data
    content_parts.append(f"""
    Instagram Profile:
    Username: {profile_data.get('username', '')}
    Full Name: {profile_data.get('full_name', '')}
    Bio: {profile_data.get('biography', '')}
    Posts Count: {profile_data.get('postsCount', 0) or profile_data.get('edge_owner_to_timeline_media', {}).get('count', 0)}
    """)
    
    # Add post images and captions
    images_added = 0
    for i, post in enumerate(posts[:7]):  # Include more posts for better analysis
        display_url = post.get("displayUrl")
        caption = post.get("caption", "")
        
        if display_url and images_added < 5:  # Limit to 5 images to avoid token limits
            # Add image to content parts
            image_base64 = encode_image_to_base64(display_url)
            if image_base64:
                content_parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                })
                images_added += 1
            
        # Add post metadata (always include caption)
        content_parts.append(f"""
        Post {i+1} Caption: {caption}
        """)
    
    try:
        # Use our helper function to get JSON response
        analysis = await get_gemini_json_response('gemini-pro-vision', content_parts)
        
        # Check if there was an error or parsing issue
        if "error" in analysis or "parsing_error" in analysis:
            print(f"Warning: Error analyzing follower @{username}: {analysis.get('error', analysis.get('parsing_error', 'Unknown error'))}")
            
            # If we got a raw response, try to extract structured data
            if "raw_response" in analysis:
                raw_text = analysis.get("raw_response", "")
                # Extract boolean value for is_suitable_icp
                is_suitable = "true" in raw_text.lower() and "false" not in raw_text.lower()
                
                evaluation = {
                    "is_suitable_icp": is_suitable,
                    "confidence_score": extract_number(raw_text, "confidence_score"),
                    "fit_reasoning": extract_section(raw_text, "fit_reasoning"),
                    "similarities_to_icp": extract_list(raw_text, "similarities_to_icp"),
                    "potential_interests": extract_list(raw_text, "potential_interests"),
                    "approach_suggestions": extract_section(raw_text, "approach_suggestions")
                }
            else:
                # Create default values
                evaluation = {
                    "is_suitable_icp": False,
                    "confidence_score": 0,
                    "fit_reasoning": "Could not evaluate due to API error",
                    "error": analysis.get("error", "Unknown error")
                }
        
        # Update follower data with analysis
        follower_data.update({
            "icp_analysis": evaluation,
            "is_suitable_icp": evaluation.get("is_suitable_icp", False)
        })
        
        return follower_data
    
    except Exception as e:
        print(f"Error analyzing follower content for @{username}: {str(e)}")
        follower_data.update({
            "icp_analysis_error": str(e),
            "is_suitable_icp": False
        })
        return follower_data

async def identify_real_people_from_usernames(usernames: List[str], brand_handle: str) -> List[Dict[str, Any]]:
    """
    Uses a simple analysis to identify usernames likely belonging to real people.
    This is a simplified version that is less resource-intensive.
    
    Args:
        usernames: List of Instagram usernames to analyze
        brand_handle: The brand's Instagram handle for context
    
    Returns:
        List of dictionaries with username classification
    """
    if not usernames:
        return []
        
    print(f"Analyzing {len(usernames)} usernames to identify real people...")
    
    # Create a simpler, rule-based classifier instead of using LLM
    real_people = []
    
    for username in usernames:
        # Skip empty usernames
        if not username:
            continue
            
        # Simple scoring system (0-100)
        score = 50  # Start at neutral
        category = "likely_person"  # Default assumption
        quality = "medium"  # Default quality
        
        # Bot/Spam patterns
        bot_patterns = [
            username.endswith("bot"),
            "_bot" in username,
            "spam" in username,
            "follow" in username and ("back" in username or "gain" in username),
            len(username) > 30,  # Excessively long
            username.count("_") > 3,  # Too many underscores
            bool(re.search(r'\d{5,}', username)),  # 5+ consecutive digits
            bool(re.search(r'^[a-zA-Z]+\d{4,}$', username))  # Letters followed by 4+ digits
        ]
        
        # Business patterns
        business_patterns = [
            "official" in username,
            "store" in username,
            "shop" in username,
            "boutique" in username,
            "brand" in username,
            "inc" in username or "llc" in username,
            username.endswith("_store"),
            username.endswith("_shop"),
            username.endswith("_brand"),
            username.endswith("_inc"),
            username.endswith("_llc"),
            "wear" in username,
            "style" in username and len(username) > 10,
            "beauty" in username,
            "fashion" in username
        ]
        
        # Real person indicators (simple heuristics)
        person_indicators = [
            bool(re.search(r'^[a-z]+\.[a-z]+$', username)),  # firstname.lastname pattern
            bool(re.search(r'^[a-z]+_[a-z]+$', username)),   # firstname_lastname pattern
            len(username) >= 5 and len(username) <= 15,       # Reasonable length
            username.count("_") <= 1,                         # Not too many separators
            not any(c.isdigit() for c in username),           # No digits
            any(name in username.lower() for name in ["alex", "sam", "chris", "kim", "pat", "taylor", "jamie", "jordan", "casey"])  # Common names
        ]
        
        # Count pattern matches
        bot_score = sum(bot_patterns)
        business_score = sum(business_patterns)
        person_score = sum(person_indicators)
        
        # Determine category based on highest score
        if bot_score > business_score and bot_score > person_score:
            category = "likely_bot"
            score -= 25 * bot_score  # Penalize bot indicators
        elif business_score > bot_score and business_score > person_score:
            category = "likely_business"
            score -= 15 * business_score  # Penalize business indicators
        else:
            category = "likely_person"
            score += 10 * person_score  # Boost for person indicators
        
        # Determine quality based on score
        if score >= 70:
            quality = "high"
        elif score >= 40:
            quality = "medium"
        else:
            quality = "low"
        
        # If we still think it's a person, add to results
        if category == "likely_person":
            real_people.append({
                "username": username,
                "category": category,
                "engagement_quality": quality,
                "reasoning": f"Simple rule-based analysis (score: {score})"
            })
    
    # Get counts for each category
    high_value = [r for r in real_people if r.get("engagement_quality") == "high"]
    medium_value = [r for r in real_people if r.get("engagement_quality") == "medium"]
    
    print(f"Analysis complete: {len(real_people)} likely real people identified")
    print(f"  - High-value connections: {len(high_value)}")
    print(f"  - Medium-value connections: {len(medium_value)}")
    
    # Sort by engagement quality
    quality_order = {"high": 3, "medium": 2, "low": 1}
    real_people.sort(key=lambda x: quality_order.get(x.get("engagement_quality", "low"), 0), reverse=True)
    
    return real_people

async def enhanced_audience_collection(instagram_handle: str, limit: int = 50, quality_threshold: int = 30) -> List[Dict[str, Any]]:
    """
    A simplified approach to collect an audience that uses basic filtering
    and rule-based username analysis to identify real people.
    
    Args:
        instagram_handle: Instagram handle to collect audience for
        limit: Maximum number of users to return
        quality_threshold: Minimum quality score (lowered from default)
    
    Returns:
        List of users identified as likely real people
    """
    print(f"🔍 Enhanced audience collection for @{instagram_handle}")
    print(f"  Using comment quality threshold: {quality_threshold}")
    
    # First collect users with a LOWER threshold than specified
    # to get more candidates (we'll still filter later)
    actual_threshold = max(20, quality_threshold - 20)  # Use a lower bar
    standard_users = await collect_instagram_followers(instagram_handle, limit=limit*2, quality_threshold=actual_threshold)
    
    if not standard_users:
        print("No users found. Trying alternate collection methods...")
        # Try hashtag-based collection as fallback with very low quality requirements
        standard_users = await collect_users_from_hashtags(instagram_handle, limit=limit*2)
    
    if not standard_users:
        print("⚠️ Could not collect any users for analysis")
        return []
    
    # Extract usernames
    all_usernames = [user.get("username") for user in standard_users if user.get("username")]
    
    # Simple rule-based classification
    real_people_data = await identify_real_people_from_usernames(all_usernames, instagram_handle)
    
    # Convert to a dictionary for easy lookup
    real_people_dict = {entry.get("username"): entry for entry in real_people_data}
    
    # Enhance original users with classification
    enhanced_users = []
    for user in standard_users:
        username = user.get("username", "")
        if username in real_people_dict:
            # Get classification
            ai_data = real_people_dict[username]
            user["classification"] = ai_data.get("category", "unknown")
            user["engagement_quality"] = ai_data.get("engagement_quality", "low")
            
            # Always include users classified as real people
            enhanced_users.append(user)
    
    print(f"Enhanced audience collection complete:")
    print(f"  - Starting users: {len(standard_users)}")
    print(f"  - After filtering: {len(enhanced_users)}")
    
    # Return all users classified as real people, up to the limit
    return enhanced_users[:limit]

async def compare_brand_to_icp(brand_analysis: Dict[str, Any], icp_profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare the brand's messaging with the identified ICPs
    """
    print("Comparing brand identity with ideal customer profiles")
    
    # Extract ICP summaries
    icp_summaries = []
    for icp in icp_profiles:
        icp_analysis = icp.get("icp_analysis", {})
        summary = {
            "username": icp.get("username"),
            "profile_summary": icp_analysis.get("profile_summary", ""),
            "demographic_indicators": icp_analysis.get("demographic_indicators", []),
            "interests": icp_analysis.get("interests", []),
            "lifestyle_patterns": icp_analysis.get("lifestyle_patterns", []),
            "brand_affinities": icp_analysis.get("brand_affinities", [])
        }
        icp_summaries.append(summary)
    
    # Prepare content for Gemini
    prompt = f"""
    As a marketing consultant, compare this brand's Instagram presence with its identified ideal customer profiles (ICPs).
    
    BRAND ANALYSIS:
    {json.dumps(brand_analysis, indent=2)}
    
    IDEAL CUSTOMER PROFILES:
    {json.dumps(icp_summaries, indent=2)}
    
    Provide your analysis as valid JSON in this format:
    {{
      "alignment_score": 85, // 0-100 score of how well the brand aligns with ICPs
      "aligned_aspects": ["Aspect 1", "Aspect 2"], // Where brand and ICPs align well
      "opportunity_areas": ["Opportunity 1", "Opportunity 2"], // Areas for better alignment
      "icp_summary": "A unified summary of the ideal customer based on all profiles",
      "recommendations": ["Recommendation 1", "Recommendation 2"] // How to better connect with ICPs
    }}
    
    Respond ONLY with valid JSON. No additional text.
    """
    
    try:
        # Use our helper function to get JSON response
        comparison = await get_gemini_json_response('gemini-pro', [prompt])
        
        # Check if there was an error or parsing issue
        if "error" in comparison or "parsing_error" in comparison:
            print(f"Warning: Error in brand-ICP comparison: {comparison.get('error', comparison.get('parsing_error', 'Unknown error'))}")
            
            # If we got a raw response, try to extract structured data
            if "raw_response" in comparison:
                raw_text = comparison.get("raw_response", "")
                comparison = {
                    "alignment_score": extract_number(raw_text, "alignment_score"),
                    "aligned_aspects": extract_list(raw_text, "aligned_aspects"),
                    "opportunity_areas": extract_list(raw_text, "opportunity_areas"),
                    "icp_summary": extract_section(raw_text, "icp_summary"),
                    "recommendations": extract_list(raw_text, "recommendations")
                }
            else:
                # Create default values
                comparison = {
                    "alignment_score": 0,
                    "aligned_aspects": [],
                    "opportunity_areas": ["Could not analyze alignment due to API error"],
                    "icp_summary": "Analysis failed due to API error",
                    "recommendations": ["Retry the analysis with different parameters"],
                    "error": comparison.get("error", "Unknown error")
                }
        
        return comparison
    
    except Exception as e:
        print(f"Error comparing brand to ICP: {str(e)}")
        return {"error": str(e)}

async def find_potential_prospects(icp_profiles: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    """
    Analyze followers of the identified ICPs to find potential new customers
    """
    print("Finding potential customer prospects from ICP followers")
    
    all_prospects = []
    
    # Process each ICP to find their followers
    icp_progress = tqdm_asyncio(icp_profiles, desc="Processing ICPs")
    for icp in icp_progress:
        username = icp.get("username")
        icp_progress.set_description(f"Finding prospects from @{username}")
        
        try:
            # Get followers of this ICP
            followers = await collect_instagram_followers(username, limit=20)
            
            # Choose a random sample of followers to analyze (max 5)
            sample_size = min(5, len(followers))
            follower_sample = random.sample(followers, sample_size) if len(followers) > sample_size else followers
            
            # Analyze each follower in the sample
            follower_progress = tqdm_asyncio(follower_sample, desc=f"Analyzing @{username} followers", leave=False)
            for follower in follower_progress:
                follower_username = follower.get("username")
                
                # Skip if username is missing
                if not follower_username:
                    continue
                
                follower_progress.set_description(f"Analyzing @{follower_username}")
                
                # Analyze this follower as a potential prospect
                follower_profile = await analyze_follower_profile(follower_username)
                
                # If profile is not valid, skip further analysis
                if not follower_profile.get("is_valid_icp", False):
                    continue
                
                # Evaluate this follower as a prospect (compared to the ICP)
                prospect_evaluation = await evaluate_prospect(follower_profile, icp)
                
                # If considered a good prospect, add to prospects list
                if prospect_evaluation.get("is_good_prospect", False):
                    all_prospects.append({
                        "username": follower_username,
                        "source_icp": username,
                        "profile_data": follower_profile.get("profile_data", {}),
                        "evaluation": prospect_evaluation
                    })
                
                # If we've found enough total prospects, we can stop
                if len(all_prospects) >= limit:
                    return all_prospects[:limit]
                
                # Rate limiting between API calls
                await asyncio.sleep(1)
            
            follower_progress.close()
        
        except Exception as e:
            print(f"Error processing ICP @{username} followers: {str(e)}")
            continue
    
    icp_progress.close()
    
    # Return however many prospects we found (might be less than the limit)
    return all_prospects

async def evaluate_prospect(prospect_data: Dict[str, Any], icp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate if a follower of an ICP would be a good prospect
    """
    username = prospect_data.get("username")
    print(f"Evaluating @{username} as a potential prospect")
    
    # Extract ICP analysis
    icp_username = icp.get("username")
    icp_analysis = icp.get("icp_analysis", {})
    
    # Get profile data and a sample of posts
    profile_data = prospect_data.get("profile_data", {})
    posts = prospect_data.get("posts", [])
    post_texts = []
    
    # Add post captions
    for i, post in enumerate(posts[:5]):
        caption = post.get("caption", "")
        if caption:
            post_texts.append(f"Post {i+1}: {caption}")
    
    # Prepare prompt for Gemini
    prompt = f"""
    As a marketing consultant, evaluate if this Instagram user (@{username}) would be a good prospect for a product that appeals to our Ideal Customer Profile.
    
    IDEAL CUSTOMER PROFILE (@{icp_username}):
    {json.dumps(icp_analysis, indent=2)}
    
    POTENTIAL PROSPECT (@{username}):
    Username: {username}
    Full Name: {profile_data.get('full_name', '')}
    Bio: {profile_data.get('biography', '')}
    Posts Count: {len(posts)}
    
    Post Captions:
    {"".join(post_texts)}
    
    Provide your evaluation as valid JSON in this format:
    {{
      "is_good_prospect": true/false,
      "confidence_score": 85, // 0-100 score
      "fit_reasoning": "Explanation of why they would be a good customer prospect",
      "similarities_to_icp": ["Similarity 1", "Similarity 2"],
      "potential_interests": ["Interest 1", "Interest 2"],
      "approach_suggestions": "How to approach this prospect with marketing"
    }}
    
    Respond ONLY with valid JSON. No additional text or explanation.
    """
    
    try:
        # Use our helper function to get JSON response
        evaluation = await get_gemini_json_response('gemini-pro-vision', [prompt])
        
        # Check if there was an error or parsing issue
        if "error" in evaluation or "parsing_error" in evaluation:
            print(f"Warning: Error evaluating prospect @{username}: {evaluation.get('error', evaluation.get('parsing_error', 'Unknown error'))}")
            
            # If we got a raw response, try to extract structured data
            if "raw_response" in evaluation:
                raw_text = evaluation.get("raw_response", "")
                # Extract boolean value for is_good_prospect
                is_good_prospect = "true" in raw_text.lower() and "false" not in raw_text.lower()
                
                evaluation = {
                    "is_good_prospect": is_good_prospect,
                    "confidence_score": extract_number(raw_text, "confidence_score"),
                    "fit_reasoning": extract_section(raw_text, "fit_reasoning"),
                    "similarities_to_icp": extract_list(raw_text, "similarities_to_icp"),
                    "potential_interests": extract_list(raw_text, "potential_interests"),
                    "approach_suggestions": extract_section(raw_text, "approach_suggestions")
                }
            else:
                # Create default values
                evaluation = {
                    "is_good_prospect": False,
                    "confidence_score": 0,
                    "fit_reasoning": "Could not evaluate due to API error",
                    "error": evaluation.get("error", "Unknown error")
                }
        
        return evaluation
    
    except Exception as e:
        print(f"Error evaluating prospect @{username}: {str(e)}")
        return {
            "is_good_prospect": False,
            "error": str(e),
            "confidence_score": 0
        }

# ==========================================
# Helper Functions
# ==========================================

async def get_gemini_json_response(model_name: str, prompt_parts: List[Any], retries: int = 2) -> Dict[str, Any]:
    """
    Helper function to get a JSON response from Gemini models with retry logic
    """
    model = genai.GenerativeModel(model_name)
    
    for attempt in range(retries + 1):
        try:
            # Apply rate limiting for Gemini API
            await rate_limit("gemini_api", 1.5)
            
            # Generate content
            response = model.generate_content(prompt_parts)
            text_response = response.text.strip()
            
            # Try to parse JSON directly
            try:
                # Find JSON in the response
                json_start = text_response.find("{")
                json_end = text_response.rfind("}") + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = text_response[json_start:json_end]
                    return json.loads(json_str)
                else:
                    raise ValueError("No JSON object found in response")
                    
            except json.JSONDecodeError as e:
                if attempt < retries:
                    print(f"JSON parse error (attempt {attempt+1}/{retries+1}): {str(e)}")
                    # Try once more with a slightly longer delay
                    await asyncio.sleep(2)
                    continue
                else:
                    # Last attempt, fall back to manual extraction
                    return {
                        "parsing_error": "Could not parse JSON response",
                        "raw_response": text_response
                    }
        except Exception as e:
            if attempt < retries:
                print(f"Gemini API error (attempt {attempt+1}/{retries+1}): {str(e)}")
                await asyncio.sleep(2)
                continue
            else:
                return {"error": str(e)}
    
    return {"error": "Failed to get valid response after all retries"}

def extract_section(text: str, section_name: str) -> str:
    """Extract a text section from the Gemini response"""
    try:
        start_pattern = f'"{section_name}":'
        if start_pattern not in text:
            start_pattern = f'{section_name}:'
        
        start_idx = text.find(start_pattern)
        if start_idx == -1:
            return ""
        
        start_idx += len(start_pattern)
        
        # Find the content between quotes if quoted
        if text[start_idx:].strip().startswith('"'):
            quote_start = text.find('"', start_idx) + 1
            quote_end = text.find('"', quote_start)
            if quote_end > quote_start:
                return text[quote_start:quote_end].strip()
        
        # Otherwise find until comma or closing brace
        comma_idx = text.find(',', start_idx)
        brace_idx = text.find('}', start_idx)
        
        end_idx = min(comma_idx, brace_idx) if comma_idx > 0 and brace_idx > 0 else max(comma_idx, brace_idx)
        if end_idx == -1:
            end_idx = len(text)
        
        return text[start_idx:end_idx].strip().strip('"\'[]{}').strip()
    except:
        return ""

def extract_list(text: str, list_name: str) -> List[str]:
    """Extract a list from the Gemini response"""
    try:
        start_pattern = f'"{list_name}":'
        if start_pattern not in text:
            start_pattern = f'{list_name}:'
        
        start_idx = text.find(start_pattern)
        if start_idx == -1:
            return []
        
        start_idx += len(start_pattern)
        
        # Find the array content
        array_start = text.find('[', start_idx)
        array_end = find_matching_bracket(text, array_start)
        
        if array_start == -1 or array_end == -1:
            return []
        
        array_str = text[array_start:array_end+1]
        
        # Try to parse as JSON first
        try:
            return json.loads(array_str)
        except:
            # Fallback to simple parsing
            items = []
            for item in array_str.strip('[]').split(','):
                item = item.strip().strip('"\'')
                if item:
                    items.append(item)
            return items
    except:
        return []

def extract_number(text: str, number_name: str) -> int:
    """Extract a number from the Gemini response"""
    try:
        start_pattern = f'"{number_name}":'
        if start_pattern not in text:
            start_pattern = f'{number_name}:'
        
        start_idx = text.find(start_pattern)
        if start_idx == -1:
            return 0
        
        start_idx += len(start_pattern)
        
        # Find the number
        end_idx = text.find(',', start_idx)
        if end_idx == -1:
            end_idx = text.find('}', start_idx)
        if end_idx == -1:
            end_idx = len(text)
        
        number_str = text[start_idx:end_idx].strip().strip('"\'')
        
        # Extract digits only
        number_str = ''.join([c for c in number_str if c.isdigit() or c == '.'])
        
        # Convert to int or float
        if '.' in number_str:
            return float(number_str)
        elif number_str:
            return int(number_str)
        else:
            return 0
    except:
        return 0

def find_matching_bracket(text: str, start_pos: int) -> int:
    """Find the matching closing bracket"""
    if start_pos >= len(text) or text[start_pos] != '[':
        return -1
    
    stack = 1
    pos = start_pos + 1
    
    while pos < len(text) and stack > 0:
        if text[pos] == '[':
            stack += 1
        elif text[pos] == ']':
            stack -= 1
        pos += 1
    
    return pos - 1 if stack == 0 else -1

# ==========================================
# Main Process Functions
# ==========================================

async def process_brand(brand: Dict[str, Any], quality_threshold: int = 30, use_ai_filtering: bool = True) -> Dict[str, Any]:
    """
    Process a single brand through the entire analysis pipeline
    
    Args:
        brand: The brand data dictionary
        quality_threshold: Minimum quality score (0-100) for comments
        use_ai_filtering: Whether to use AI-based username filtering
    """
    name = brand.get("name", "Unknown")
    url = brand.get("url", "")
    instagram_handle = brand.get("instagram_handle", "")
    
    print(f"\n=== Processing Brand: {name} (@{instagram_handle}) ===\n")
    print(f"Using quality threshold of {quality_threshold} for engagement filtering")
    
    try:
        # 1. Collect brand's Instagram profile data
        print("Step 1/4: Collecting brand profile data...")
        profile_data = await collect_instagram_profile(instagram_handle)
        print("✓ Successfully collected profile data")
        
        # 2. Collect brand's posts
        print("Step 2/4: Collecting brand posts...")
        posts = await collect_instagram_posts(instagram_handle, limit=5)  # Reduced from 10
        print(f"✓ Successfully collected {len(posts)} posts")
        
        # 3. Analyze brand profile with images
        print("Step 3/4: Analyzing brand profile...")
        brand_analysis = await analyze_brand_profile(profile_data, posts)
        print("✓ Successfully analyzed brand profile")
        
        # 4. Collect engaged users with quality filtering - simplified approach
        print("Step 4/4: Collecting basic audience data...")
        print("   - Looking for users who engage with the brand")
        print("   - Using simple username analysis")
        
        # Use a very low quality threshold (override parameter)
        actual_threshold = min(quality_threshold, 30)  # Cap at 30 max
        
        # Try to collect some users, even with very low threshold
        engaged_users = await enhanced_audience_collection(instagram_handle, limit=20, quality_threshold=actual_threshold)
        
        # Even if we don't have many, proceed anyway
        if not engaged_users:
            print("⚠️ No engaged users found, but continuing with brand analysis")
            engaged_users = []
        else:
            print(f"✓ Found {len(engaged_users)} users to analyze")
            
        # Just collect basic ICP data - don't filter too much
        icp_candidates = []
        
        if engaged_users:
            # Sample just a few users to analyze as ICPs, don't be too picky
            sample_size = min(5, len(engaged_users))
            audience_sample = engaged_users[:sample_size]
            
            for user in audience_sample:
                username = user.get("username")
                if not username:
                    continue
                
                print(f"Analyzing user @{username}...")
                
                # Basic profile analysis
                user_profile = await analyze_follower_profile(username)
                
                # If we can get some data, include it
                if user_profile.get("is_valid_icp", False) or user_profile.get("posts", []):
                    icp_candidates.append(user_profile)
            
            print(f"✓ Analyzed {len(icp_candidates)} users for insights")
        
        # Try to do comparison if we have any data
        comparison = {}
        if icp_candidates:
            # Compare brand to profiles we have
            comparison = await compare_brand_to_icp(brand_analysis, icp_candidates)
        
        # Complete results - simpler structure
        results = {
            "brand": {
                "name": name,
                "url": url,
                "instagram_handle": instagram_handle
            },
            "brand_profile": profile_data,
            "brand_analysis": brand_analysis,
            "posts_sample": posts[:2],  # Just include 2 sample posts
            "audience_data": {
                "engaged_users": [{"username": u.get("username")} for u in engaged_users],
                "analyzed_profiles": icp_candidates
            },
            "analysis_results": comparison,
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
        }
        
        save_results(instagram_handle, results)
        print("\n✓ Analysis complete! Results saved to file.")
        return results
        
    except Exception as e:
        error_message = f"Error processing brand {name}: {str(e)}"
        print(f"\n❌ {error_message}")
        
        # Save error results
        error_results = {
            "brand": {
                "name": name,
                "url": url,
                "instagram_handle": instagram_handle
            },
            "error": error_message,
            "timestamp": datetime.now().isoformat(),
            "status": "error"
        }
        
        save_results(instagram_handle, error_results)
        return error_results

def save_results(instagram_handle: str, results: Dict[str, Any]):
    """Save results to JSON file"""
    filename = f"results/{instagram_handle}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to {filename}")

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
    
    # Display information about our approach
    print("\n" + "="*80)
    print("INSTAGRAM AUDIENCE ANALYSIS - SIMPLIFIED APPROACH".center(80))
    print("="*80)
    print(f"""
This simplified analysis tool examines Instagram brands and their audience by:

1. Brand Profile Analysis:
   - Visual and text content from the brand's posts
   - Brand voice, aesthetics, and positioning

2. Basic Audience Insights:
   - Finding users who interact with the brand's content
   - Simple rule-based filtering to identify real accounts
   - Basic username pattern analysis
   - Using lower quality threshold: {quality_threshold}/100

3. Quick Insights:
   - Summarizing brand identity and messaging
   - Identifying potential audience interests and demographics
   - Generating marketing recommendations

With simpler requirements, this tool prioritizes getting useful results
over perfect filtering and complex analysis.
    """)
    print("="*80 + "\n")
    
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
    
    parser = argparse.ArgumentParser(description="Simplified Instagram Analysis Tool")
    parser.add_argument("--brand", type=str, help="Process a single brand by Instagram handle")
    parser.add_argument("--list", action="store_true", help="List all available brands")
    parser.add_argument("--add-engaged-users", type=str, help="Add known engaged users to a brand (format: brand,user1,user2,...)")
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
    elif args.add_engaged_users:
        # Handle adding known engaged users to a brand's cache
        try:
            parts = args.add_engaged_users.split(',')
            if len(parts) < 2:
                print("Error: Format should be 'brand,user1,user2,...'")
                sys.exit(1)
                
            brand_handle = parts[0]
            usernames = parts[1:]
            
            # Check if cache file exists
            cache_file = f"cache/{brand_handle}_followers.json"
            
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                
                # Get existing users
                existing_users = cached_data.get("followers", [])
                existing_usernames = {f.get("username") for f in existing_users if "username" in f}
                
                # Add new users
                for username in usernames:
                    if username and username not in existing_usernames:
                        existing_users.append({"username": username, "source": "manual", "quality_score": 100})
                        existing_usernames.add(username)
                
                # Update cache
                cached_data["followers"] = existing_users
                cached_data["cache_timestamp"] = datetime.now().isoformat()
                cached_data["manually_added"] = True
                
                with open(cache_file, 'w') as f:
                    json.dump(cached_data, f, indent=2)
                
                print(f"Added {len(usernames)} engaged users to @{brand_handle}'s cache.")
                print(f"Total engaged users in cache: {len(existing_users)}")
                
            else:
                # Create new cache file
                followers = [{"username": username, "source": "manual", "quality_score": 100} for username in usernames if username]
                cache_data = {
                    "followers": followers,
                    "cache_timestamp": datetime.now().isoformat(),
                    "manually_added": True,
                    "source": "manual"
                }
                
                # Create cache directory if it doesn't exist
                os.makedirs("cache", exist_ok=True)
                
                with open(cache_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                
                print(f"Created new cache for @{brand_handle} with {len(followers)} engaged users.")
            
        except Exception as e:
            print(f"Error adding engaged users: {str(e)}")
    elif args.brand:
        # Process a single brand by Instagram handle
        try:
            with open("brands.json", 'r') as f:
                brands = json.load(f)
                
            # Find the brand by Instagram handle
            brand = next((b for b in brands if b.get("instagram_handle") == args.brand), None)
            
            if brand:
                # Display analysis approach information
                print("\n" + "="*80)
                print("SIMPLIFIED INSTAGRAM ANALYSIS".center(80))
                print("="*80)
                print(f"""
Analyzing brand profile and finding engaged users through:
- Simple comment and hashtag collection
- Basic username pattern analysis
- Using lower quality threshold: {args.quality_threshold}/100

For more engaged users, you can manually add them with:
python instagram_analysis.py --add-engaged-users brand,user1,user2,...
                """)
                print("="*80 + "\n")
                
                asyncio.run(process_brand(brand, quality_threshold=args.quality_threshold))
            else:
                print(f"Brand with Instagram handle @{args.brand} not found.")
        except FileNotFoundError:
            print("No brands.json file found.")
    else:
        # Process all brands
        asyncio.run(main())