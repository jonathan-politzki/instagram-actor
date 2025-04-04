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
        # Run the Instagram profile scraper actor
        run_input = {
            "directUrls": [f"https://www.instagram.com/{instagram_handle}/"],
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
        # Run the Instagram posts scraper actor
        run_input = {
            "directUrls": [f"https://www.instagram.com/{instagram_handle}/"],
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

async def collect_instagram_followers(instagram_handle: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Collect a sample of followers for a Shopify store's Instagram
    """
    print(f"Collecting followers for @{instagram_handle}")
    
    # Check cache first
    cache_file = f"cache/{instagram_handle}_followers.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cached_data = json.load(f)
            # Check if cache is less than 1 day old
            cache_time = datetime.fromisoformat(cached_data.get("cache_timestamp", "2000-01-01T00:00:00"))
            if (datetime.now() - cache_time).days < 1:
                print(f"Using cached followers data for @{instagram_handle}")
                return cached_data["followers"]
    
    try:
        # Run the Instagram followers scraper actor
        run_input = {
            "usernames": [instagram_handle],
            "resultsLimit": limit,
            "scrapeFollowers": True,
            "scrapeFollowing": False
        }
        
        run = apify_client.actor("lodovit/instagram-followers-scraper").call(run_input=run_input)
        followers_data = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
        
        # Extract just the followers
        followers = []
        for item in followers_data:
            if "followers" in item and instagram_handle.lower() == item.get("username", "").lower():
                followers = item["followers"]
                break
        
        # Cache the results
        cache_data = {
            "followers": followers,
            "cache_timestamp": datetime.now().isoformat()
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        return followers
    
    except Exception as e:
        print(f"Error collecting Instagram followers: {str(e)}")
        raise

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
        # First check if profile is public
        profile_run_input = {
            "directUrls": [f"https://www.instagram.com/{username}/"],
            "resultsType": "details"
        }
        
        profile_run = apify_client.actor("apify/instagram-profile-scraper").call(run_input=profile_run_input)
        profile_items = list(apify_client.dataset(profile_run["defaultDatasetId"]).iterate_items())
        
        if not profile_items:
            return {"username": username, "is_private": True, "is_valid_icp": False, "reason": "Profile not found"}
        
        profile_data = profile_items[0]
        
        # Check if profile is private
        if profile_data.get("is_private", True):
            profile_result = {
                "username": username,
                "is_private": True,
                "is_valid_icp": False,
                "reason": "Private profile",
                "cache_timestamp": datetime.now().isoformat()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(profile_result, f, indent=2)
                
            return profile_result
            
        # If profile is public, get their posts
        posts_run_input = {
            "directUrls": [f"https://www.instagram.com/{username}/"],
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
                "cache_timestamp": datetime.now().isoformat()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(profile_result, f, indent=2)
                
            return profile_result
        
        # Profile has enough public content for analysis
        profile_result = {
            "username": username,
            "is_private": False,
            "posts_count": len(posts),
            "is_valid_icp": True,
            "profile_data": profile_data,
            "posts": posts[:10],  # Limit to 10 posts
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
            "cache_timestamp": datetime.now().isoformat()
        }
        
        with open(cache_file, 'w') as f:
            json.dump(error_result, f, indent=2)
            
        return error_result 