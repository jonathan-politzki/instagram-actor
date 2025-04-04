import os
import json
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from apify_client import ApifyClient
import requests
from io import BytesIO
from PIL import Image
import base64

# Load environment variables
load_dotenv()

# Configure API keys
APIFY_API_KEY = os.getenv("APIFY_API_KEY")

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
    Collect Instagram profile data for a brand
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
                        businessCategory: $.business_category_name,
                        is_private: $.is_private,
                        has_public_story: $.has_public_story
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
    Collect Instagram posts for a brand's Instagram account
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
                posts = cached_data["posts"]
                print(f"Using cached posts data for @{instagram_handle} ({len(posts)} posts)")
                if len(posts) < 3:
                    print(f"Warning: Only {len(posts)} cached posts found, collecting fresh data")
                else:
                    return posts
    
    try:
        # Apply rate limiting
        await rate_limit("instagram_posts", 2.0)
        
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
            run = apify_client.actor("apify/instagram-scraper").call(run_input=run_input, timeout_secs=120)
            posts = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
            
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
            
            run = apify_client.actor("apify/instagram-profile-scraper").call(run_input=profile_run_input, timeout_secs=120)
            posts = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
        
        print(f"Successfully collected {len(posts)} posts for @{instagram_handle}")
        
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
        # Return empty list instead of raising to prevent analysis from failing
        return []

async def collect_post_comments(post_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Collect comments for a specific Instagram post
    """
    print(f"Collecting comments for post {post_id}")
    
    try:
        # Apply rate limiting
        await rate_limit("instagram_comments", 3.0)
        
        # Get comments for this post using the Instagram Comment Scraper
        run_input = {
            "directUrls": [f"https://www.instagram.com/p/{post_id}/"],
            "resultsLimit": limit
        }
        
        run = apify_client.actor("apify/instagram-comment-scraper").call(run_input=run_input, timeout_secs=60)
        comments = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
        
        return comments
    
    except Exception as e:
        print(f"Error collecting comments for post {post_id}: {str(e)}")
        return []

async def collect_hashtag_posts(hashtag: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Collect posts for a specific hashtag
    """
    print(f"Collecting posts for hashtag #{hashtag}")
    
    try:
        # Apply rate limiting
        await rate_limit("instagram_hashtags", 5.0)  # Longer delay for hashtag searches
        
        # Call the hashtag scraper
        run_input = {
            "hashtags": [hashtag],
            "resultsLimit": limit
        }
        
        run = apify_client.actor("apify/instagram-hashtag-scraper").call(run_input=run_input, timeout_secs=60)
        hashtag_data = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
        
        return hashtag_data
    
    except Exception as e:
        print(f"Error collecting hashtag posts for #{hashtag}: {str(e)}")
        return []

async def check_profile_visibility(username: str) -> Dict[str, Any]:
    """
    Check if an Instagram profile is public or private and retrieve basic profile data
    Improved version that fixes issues with private/public detection
    """
    print(f"Checking visibility for @{username}")
    
    try:
        # Apply rate limiting
        await rate_limit("profile_check", 1.0)
        
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
        profile_run = apify_client.actor("apify/instagram-profile-scraper").call(run_input=profile_run_input, timeout_secs=60)
        profile_items = list(apify_client.dataset(profile_run["defaultDatasetId"]).iterate_items())
        
        if not profile_items:
            # Try one more time with a basic call
            await rate_limit("profile_check", 1.0)
            simple_run_input = {"usernames": [username]}
            profile_run = apify_client.actor("apify/instagram-profile-scraper").call(run_input=simple_run_input, timeout_secs=60)
            profile_items = list(apify_client.dataset(profile_run["defaultDatasetId"]).iterate_items())
            
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
                await rate_limit("profile_posts_check", 2.0)
                
                # Try to get posts - if we can, it's public
                posts_input = {
                    "usernames": [username],
                    "resultsType": "posts",
                    "resultsLimit": 1
                }
                
                posts_run = apify_client.actor("apify/instagram-profile-scraper").call(run_input=posts_input, timeout_secs=30)
                posts = list(apify_client.dataset(posts_run["defaultDatasetId"]).iterate_items())
                
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

def encode_image_to_base64(image_url: str) -> Optional[str]:
    """
    Download and encode image to base64 for AI API
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