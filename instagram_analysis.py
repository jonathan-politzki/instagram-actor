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
import traceback

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

async def get_gemini_json_response(model: str, prompts: List[str], retries: int = 3) -> Dict[str, Any]:
    """
    Make a structured request to Gemini API and return JSON response
    
    Args:
        model: Gemini model to use ('gemini-1.5-pro' or 'gemini-1.5-flash')
        prompts: List of text prompts to send
        retries: Number of retries on failure
        
    Returns:
        Parsed JSON response from Gemini
    """
    print(f"Making Gemini API call with model {model}...")
    
    # Apply rate limiting
    await rate_limit("gemini_api", 2.0)
    
    attempt = 0
    last_error = None
    
    while attempt < retries:
        try:
            # Create the model
            genai_model = genai.GenerativeModel(model)
            
            # Make the request
            response = genai_model.generate_content(prompts)
            
            # Extract the text response
            text_response = response.text
            
            # Check if response starts/ends with triple backticks for code blocks
            if text_response.startswith("```json") and "```" in text_response:
                # Extract just the JSON part
                json_text = text_response.split("```json")[1].split("```")[0].strip()
            elif text_response.startswith("```") and text_response.endswith("```"):
                json_text = text_response[3:-3].strip()
            else:
                json_text = text_response
            
            # Parse the JSON
            try:
                result = json.loads(json_text)
                return result
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
                print(f"Raw response: {text_response}")
                
                # Try to extract anything that looks like JSON with curly braces
                import re
                json_match = re.search(r'({.*})', text_response, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(1))
                        return result
                    except:
                        pass
                
                # More aggressive cleanup attempt - remove any non-JSON text before/after curly braces
                try:
                    # Find the first opening brace and last closing brace
                    start_idx = text_response.find('{')
                    end_idx = text_response.rfind('}')
                    
                    if start_idx >= 0 and end_idx > start_idx:
                        json_text = text_response[start_idx:end_idx+1]
                        result = json.loads(json_text)
                        return result
                except:
                    pass
                
                raise Exception(f"Could not parse JSON from response: {e}")
                
        except Exception as e:
            last_error = str(e)
            attempt += 1
            await asyncio.sleep(2)  # Wait before retrying
            print(f"Retrying Gemini API call ({attempt}/{retries}): {last_error}")
    
    # If we reach here, all retries failed
    print(f"All Gemini API attempts failed: {last_error}")
    return {"error": last_error}

async def analyze_comments_for_icp(comments: List[Dict[str, Any]], brand_handle: str, brand_name: str) -> List[Dict[str, Any]]:
    """
    Analyze comments to identify potential ICPs based on their engagement
    
    Args:
        comments: List of comments with quality analysis
        brand_handle: Instagram handle of the brand
        brand_name: Name of the brand
        
    Returns:
        List of potential ICP users with quality ratings
    """
    if not comments:
        return []
        
    print(f"Analyzing {len(comments)} comments to identify potential ICPs...")
    
    # Filter out very low-quality comments - more inclusive threshold
    quality_comments = [c for c in comments if c.get("quality_score", 0) >= 20]
    
    icp_candidates = {}
    
    # Normalize brand name for pattern matching
    brand_name_lower = brand_name.lower()
    brand_handle_lower = brand_handle.lower()
    
    # Evaluate each comment for ICP potential
    for comment in quality_comments:
        username = comment.get("ownerUsername")
        if not username:
            continue
            
        text = comment.get("text", "")
        sentiment = comment.get("sentiment", "neutral")
        
        # Skip if this user is already processed
        if username in icp_candidates:
            # Update existing record with better scoring if available
            if comment.get("quality_score", 0) > icp_candidates[username].get("quality_score", 0):
                icp_candidates[username]["quality_score"] = comment.get("quality_score", 0)
                icp_candidates[username]["comment_text"] = text
            
            # Count the comments from this user
            icp_candidates[username]["comment_count"] += 1
            
            # Accumulate ICP signals across multiple comments
            icp_candidates[username]["icp_signals"] += 1
            continue
            
        # Check for ICP signals in the comment text
        icp_signals = 0
        
        # Personal experience with product - expanded patterns
        if any(phrase in text.lower() for phrase in [
            "i have", "i bought", "i love", "i use", "i wear", "i own", "i got",
            "my pair", "my new", "mine", "i'm wearing", "i am wearing", "i ordered",
            "i received", "i purchased", "just got", "arrived today", "delivered",
            "i tried", "wearing my", "using my", "bought these", "got these"
        ]):
            icp_signals += 2
            
        # Product knowledge - expanded patterns
        if any(phrase in text.lower() for phrase in [
            "quality", "comfort", "fit", "design", "material", "feature", "technology",
            "waterproof", "breathable", "durable", "lightweight", "performance",
            "sizing", "color", "cushioning", "support", "style", "laces", "sole",
            "fabric", "stitching", "color way", "colorway", "release", "drop",
            "limited edition", "exclusive", "collaboration", "collab", "authentic"
        ]):
            icp_signals += 1
            
        # Brand loyalty - expanded patterns
        if any(phrase in text.lower() for phrase in [
            "favorite brand", "best brand", "loyal", "always buy", "never disappoint", 
            "never fails", "consistently", "collection", "fan", "love the brand",
            "always choose", "go-to", "go to", "only wear", "always wear", "trust",
            "reliable", "never lets me down", "been wearing for years", "since day one"
        ]):
            icp_signals += 2
            
        # Emotional connection - expanded patterns
        if any(word in text.lower() for word in [
            "amazing", "awesome", "incredible", "perfect", "love", "beautiful", "excellent",
            "outstanding", "extraordinary", "impressive", "exceptional", "fantastic",
            "great", "stunning", "wonderful", "stylish", "cool", "dope", "fire", "lit",
            "obsessed", "addicted", "can't get enough", "need more", "best", "favorite"
        ]):
            icp_signals += 1
            
        # Question about product/brand (engagement) - expanded patterns
        if "?" in text and any(word in text.lower() for word in [
            "available", "release", "when", "where", "how", "which", "recommend", "sizing", "price",
            "restock", "coming out", "sell", "shipping", "delivery", "store", "shop", "online",
            "website", "app", "discount", "sale", "upcoming", "next", "color", "size", "fit"
        ]):
            icp_signals += 1
            
        # Direct mention of the brand - new pattern
        if brand_name_lower in text.lower() or brand_handle_lower in text.lower():
            icp_signals += 1
            
        # High engagement - leaving detailed comment
        if len(text) > 100:
            icp_signals += 1
        
        # Any comment engagement is worth something - more inclusive
        if icp_signals == 0 and len(text) > 10:
            icp_signals = 0.5
            
        # Create ICP candidate record with more inclusive thresholds
        icp_quality = "low"
        if icp_signals >= 3:
            icp_quality = "high"
        elif icp_signals >= 1:
            icp_quality = "medium"
            
        icp_candidates[username] = {
            "username": username,
            "icp_quality": icp_quality,
            "icp_signals": icp_signals,
            "quality_score": comment.get("quality_score", 0),
            "sentiment": sentiment,
            "comment_text": text,
            "comment_count": 1
        }
    
    # Convert to list and sort by quality
    result = list(icp_candidates.values())
    result.sort(key=lambda x: (x.get("icp_signals", 0), x.get("quality_score", 0)), reverse=True)
    
    # Return all candidates - more inclusive
    return result

async def process_brand(brand: Dict[str, Any], quality_threshold: int = 30, use_ai_filtering: bool = True) -> Dict[str, Any]:
    """
    Process a single brand through the entire analysis pipeline with LLM-enhanced approach
    
    Args:
        brand: The brand data dictionary
        quality_threshold: Minimum quality score (0-100) for comments
        use_ai_filtering: Whether to use AI-based username filtering
    """
    name = brand.get("name", "Unknown")
    url = brand.get("url", "")
    instagram_handle = brand.get("instagram_handle", "")
    
    print(f"\n=== Processing Brand: {name} (@{instagram_handle}) ===\n")
    print(f"Using LLM-enhanced approach for deeper insights")
    
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
        
        # 4. Collect engaged users with rule-based filtering
        print("Step 4/5: Collecting and analyzing audience data...")
        
        # 4a. Get users from comments and analyze comment quality
        print("  - Collecting comments from recent posts...")
        all_comments = []
        
        for post in posts:
            if "shortCode" not in post:
                continue
                
            post_id = post.get("shortCode")
            
            # Apply rate limiting
            await rate_limit("instagram_comments", 3.0)
            
            # Get comments for this post
            try:
                run_input = {
                    "directUrls": [f"https://www.instagram.com/p/{post_id}/"],
                    "resultsLimit": 100  # Increased from 50 to get more comments
                }
                
                run = apify_client.actor("apify/instagram-comment-scraper").call(run_input=run_input, timeout_secs=60)
                comments = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
                
                # Analyze comment quality
                for comment in comments:
                    # Skip brand's own comments
                    if comment.get("ownerUsername") == instagram_handle:
                        continue
                    
                    analyzed_comment = await analyze_comment_quality(comment)
                    all_comments.append(analyzed_comment)
                
            except Exception as e:
                print(f"  - Error collecting comments for post {post_id}: {str(e)}")
                continue
        
        print(f"  - Collected and analyzed {len(all_comments)} comments")
        
        # 4b. Identify ICPs from comments - use a lower quality threshold
        comment_quality_threshold = max(10, quality_threshold - 15)  # Lower threshold to cast wider net
        filtered_comments = [c for c in all_comments if c.get("quality_score", 0) >= comment_quality_threshold]
        comment_icp_candidates = await analyze_comments_for_icp(filtered_comments, instagram_handle, name)
        print(f"  - Identified {len(comment_icp_candidates)} potential ICPs from comments")
        
        # 4c. Use rules-based username filtering as a secondary method - increased limit
        engaged_users = await enhanced_audience_collection(instagram_handle, limit=30, quality_threshold=quality_threshold)
        
        if engaged_users:
            print(f"  - Found {len(engaged_users)} users through username filtering")
        else:
            print("  - No engaged users found through username filtering")
            engaged_users = []
        
        # 4d. Combine the two sets of users, prioritizing comment-based ICPs
        combined_users = []
        seen_usernames = set()
        
        # Add comment-based ICPs first (they're higher quality)
        for user in comment_icp_candidates:
            username = user.get("username")
            if username:
                seen_usernames.add(username)
                combined_users.append({
                    "username": username,
                    "source": "comment",
                    "icp_quality": user.get("icp_quality", "low"),
                    "comment_text": user.get("comment_text", ""),
                    "comment_count": user.get("comment_count", 1),
                    "quality_score": user.get("quality_score", 0)
                })
        
        # Add username-filtered users that haven't been added yet
        for user in engaged_users:
            username = user.get("username")
            if username and username not in seen_usernames:
                seen_usernames.add(username)
                combined_users.append(user)
        
        print(f"  - Combined total of {len(combined_users)} unique engaged users")
        
        # 5. Analyze users for ICP data with LLM, but first check if they're public profiles
        print("Step 5/5: Performing deep ICP analysis with LLM...")
        icp_data = []
        icp_limit = 15  # Increased from 7 to 15 to analyze more users
        
        # Prioritize comment-based users
        users_to_analyze = combined_users[:icp_limit]
        
        # First, check which profiles are public to save time
        public_users = []
        private_users = []
        
        # Quick check for public vs private profiles in parallel
        async def check_profile_visibility(user):
            username = user.get("username")
            try:
                # Use a lightweight call to just check if profile is public
                profile_run_input = {
                    "usernames": [username],
                    "resultsType": "details"
                }
                
                await rate_limit("profile_check", 1.0)
                
                profile_run = apify_client.actor("apify/instagram-profile-scraper").call(run_input=profile_run_input)
                profile_items = list(apify_client.dataset(profile_run["defaultDatasetId"]).iterate_items())
                
                if not profile_items:
                    return {"user": user, "public": False, "exists": False}
                
                is_private = profile_items[0].get("is_private", True)
                return {"user": user, "public": not is_private, "exists": True, "profile_data": profile_items[0]}
            except:
                return {"user": user, "public": False, "exists": False}
        
        # Check all profiles in parallel with a semaphore to limit concurrency
        async def check_all_profiles():
            sem = asyncio.Semaphore(3)  # Limit to 3 concurrent API calls
            
            async def check_with_semaphore(user):
                async with sem:
                    return await check_profile_visibility(user)
            
            tasks = [check_with_semaphore(user) for user in users_to_analyze]
            return await asyncio.gather(*tasks)
        
        print("  - Pre-filtering for public profiles...")
        profile_checks = await check_all_profiles()
        
        for result in profile_checks:
            if result["public"]:
                public_users.append(result["user"])
            else:
                if result["exists"]:
                    private_users.append({
                        "user": result["user"],
                        "profile_data": result.get("profile_data", {})
                    })
                    print(f"  - Skipping private profile: @{result['user'].get('username')}")
                else:
                    print(f"  - Skipping non-existent profile: @{result['user'].get('username')}")
        
        print(f"  - Found {len(public_users)} public profiles to analyze")
        
        # If we have public profiles, analyze them in detail
        if public_users:
            for i, user in enumerate(public_users):
                username = user.get("username")
                if not username:
                    continue
                    
                # Show source for better insights
                source_info = ""
                if user.get("source") == "comment":
                    source_info = f" (comment-based, quality: {user.get('icp_quality', 'unknown')})"
                
                print(f"Analyzing potential ICP: @{username}{source_info}...")
                
                # Get user profile data
                user_profile = await collect_user_profile_posts(username, limit=3)
                
                # Add the comment text if available (helps with analysis)
                if user.get("comment_text"):
                    if "comments" not in user_profile:
                        user_profile["comments"] = []
                    user_profile["comments"].append({
                        "text": user.get("comment_text", ""),
                        "count": user.get("comment_count", 1)
                    })
                
                # LLM-based ICP analysis
                if user_profile:
                    analyzed_user = await analyze_user_profile_with_llm(user_profile, instagram_handle, name)
                    icp_data.append(analyzed_user)
        
        # Analyze private profiles with limited data-based analysis
        print(f"  - Analyzing {len(private_users)} private profiles with limited data...")
        
        for item in private_users:
            user = item["user"]
            username = user.get("username")
            if not username:
                continue
            
            # Basic inferred data from username and comments
            is_comment_user = user.get("source") == "comment"
            comment_text = user.get("comment_text", "")
            comment_count = user.get("comment_count", 0)
            
            # Get interests based on comment text if available
            inferred_interests = []
            engagement_potential = "low"
            
            # Enhanced visibility using available data
            if is_comment_user and comment_text:
                # Check for product interest signals
                if any(keyword in comment_text.lower() for keyword in [
                    "shoes", "sneakers", "running", "training", "workout", "sport", 
                    "apparel", "jersey", "jacket", "fit", "performance"
                ]):
                    inferred_interests.append("Athletic footwear")
                    inferred_interests.append("Sports apparel")
                    engagement_potential = "medium"
                
                # Check for brand interest
                if "nike" in comment_text.lower() or any(word in comment_text.lower() for word in ["jordans", "air max", "airmax"]):
                    inferred_interests.append("Nike products")
                    engagement_potential = "medium"
                    
                # Check for fashion interest
                if any(keyword in comment_text.lower() for keyword in [
                    "style", "fashion", "look", "design", "cool", "love", "want", "need"
                ]):
                    inferred_interests.append("Fashion")
                    inferred_interests.append("Streetwear")
                    
                # High engagement potential if multiple comments or detailed feedback
                if comment_count > 1 or len(comment_text) > 100:
                    engagement_potential = "high"
            
            # Try to infer interest from username patterns
            username_lower = username.lower()
            if any(keyword in username_lower for keyword in [
                "run", "fitness", "fit", "gym", "sport", "athlete", "coach", "train"
            ]):
                inferred_interests.append("Fitness")
                inferred_interests.append("Sports")
                engagement_potential = "medium"
                
            # Create a minimal profile with available data
            full_name = item.get("profile_data", {}).get("full_name", "Unknown")
            follower_count = item.get("profile_data", {}).get("followersCount", 0)
            
            # Set up reasoning based on available data
            if is_comment_user:
                reasoning = f"Limited analysis based on comment engagement. User has commented: '{comment_text[:100]}...'"
                if comment_count > 1:
                    reasoning += f" User has made {comment_count} comments on brand posts."
            else:
                reasoning = "Limited analysis based on username patterns only. Profile is private."
                
            # Make an inference on ICP suitability
            is_suitable = engagement_potential != "low" or len(inferred_interests) > 0
                
            minimal_profile = {
                "username": username,
                "profile_data": {
                    "username": username,
                    "full_name": full_name,
                    "bio": "Private profile",
                    "follower_count": follower_count
                },
                "icp_analysis": {
                    "is_suitable_icp": is_suitable,
                    "reasoning": reasoning,
                    "profile_summary": f"Private Instagram profile for @{username}",
                    "interests": inferred_interests if inferred_interests else ["Unknown due to private profile"],
                    "demographic_indicators": [],
                    "brand_affinities": ["Nike"] if "nike" in comment_text.lower() else [],
                    "engagement_potential": engagement_potential
                },
                "is_private": True,
                "posts_count": 0,
                "comments_count": comment_count
            }
            
            # Add to ICP data
            icp_data.append(minimal_profile)
        
        # If we don't have any ICP data from either public or private profiles, add minimal placeholder
        if not icp_data:
            print("  - No usable profile data found. Adding minimal placeholder for analysis.")
            icp_data.append({
                "username": "placeholder_user",
                "profile_data": {"username": "placeholder_user", "full_name": "Unknown", "bio": "No data available"},
                "icp_analysis": {
                    "is_suitable_icp": False,
                    "reasoning": "No usable profile data could be found for analysis.",
                    "profile_summary": "Placeholder for missing data",
                    "interests": ["Unknown"],
                    "demographic_indicators": [],
                    "brand_affinities": [],
                    "engagement_potential": "unknown"
                }
            })
        
        # Generate audience insights with LLM
        audience_insights = await generate_audience_insights_with_llm(icp_data, name, instagram_handle)
        
        # Complete results with all our data
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
                "engaged_users": [{"username": u.get("username")} for u in combined_users],
                "icp_data": icp_data,
                "comment_based_users": len(comment_icp_candidates),
                "username_based_users": len(engaged_users),
                "total_unique_users": len(combined_users),
                "public_profiles": len(public_users),
                "private_profiles": len(private_users)
            },
            "audience_insights": audience_insights,
            "analysis_metadata": {
                "timestamp": datetime.now().isoformat(),
                "analysis_type": "llm_enhanced_approach",
                "quality_threshold_used": quality_threshold,
                "status": "completed",
                "api_usage": "Active - Using Gemini API"
            }
        }
        
        # Save results to disk
        os.makedirs("results", exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = f"results/{instagram_handle}_{timestamp}.json"
        
        with open(result_file, 'w') as f:
            json.dump(results, f, indent=2)
            
        print(f"\nAnalysis complete! Results saved to {result_file}")
        
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
        os.makedirs("results", exist_ok=True)
        
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
    print("INSTAGRAM AUDIENCE ANALYSIS - LLM-ENHANCED APPROACH".center(80))
    print("="*80)
    print(f"""
This LLM-enhanced analysis tool examines Instagram brands and their audience by:

1. Brand Profile Analysis:
   - Visual and text content from the brand's posts
   - Brand voice, aesthetics, and positioning

2. Basic Audience Insights:
   - Finding users who interact with the brand's content
   - Rule-based filtering to identify real accounts
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
    
    parser = argparse.ArgumentParser(description="LLM-Enhanced Instagram Analysis Tool")
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
                print("LLM-ENHANCED INSTAGRAM ANALYSIS".center(80))
                print("="*80)
                print(f"""
Analyzing brand profile and finding engaged users through:
- Rule-based filtering
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