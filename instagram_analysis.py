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

# ==========================================
# Analysis Functions
# ==========================================

def encode_image_to_base64(image_url: str) -> Optional[str]:
    """
    Download and encode image to base64 for Gemini Vision API
    """
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        
        # Check if the image is a valid image
        try:
            img = Image.open(BytesIO(response.content))
            img.verify()  # Verify it's an image
        except:
            return None
            
        return base64.b64encode(response.content).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image {image_url}: {str(e)}")
        return None

async def analyze_brand_profile(profile_data: Dict[str, Any], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze the brand's Instagram profile and posts to determine brand identity
    """
    print(f"Analyzing brand profile for @{profile_data.get('username')}")
    
    # Initialize Gemini model for multimodal input
    model = genai.GenerativeModel('gemini-2.0-pro-vision')
    
    # Prepare content parts for Gemini
    content_parts = [
        """Analyze this ecommerce store's Instagram profile as a marketing consultant. First, identify:
        1. Brand voice and messaging style
        2. Core product categories and focus
        3. Visual aesthetic and design preferences
        4. Target audience characteristics
        5. Key topics and themes in their content
        
        Provide your analysis in the following JSON structure:
        {
            "brand_identity": "Comprehensive description of the brand's identity and positioning",
            "messaging_style": "Analysis of their communication style and voice",
            "visual_identity": "Description of their visual aesthetic and imagery",
            "key_topics": ["Topic 1", "Topic 2", "Topic 3"],
            "apparent_target_audience": "Description of who they appear to be targeting",
            "strengths": ["Strength 1", "Strength 2"],
            "opportunity_areas": ["Opportunity 1", "Opportunity 2"]
        }
        
        Respond ONLY with valid JSON. No additional text or explanation.
        """
    ]
    
    # Add profile data
    content_parts.append(f"""
    Instagram Profile:
    Username: {profile_data.get('username', '')}
    Full Name: {profile_data.get('fullName', '')}
    Bio: {profile_data.get('biography', '')}
    Followers: {profile_data.get('followersCount', 0)}
    Following: {profile_data.get('followingCount', 0)}
    Posts Count: {profile_data.get('postsCount', 0)}
    Business Account: {profile_data.get('isBusinessAccount', False)}
    Business Category: {profile_data.get('businessCategory', 'N/A')}
    """)
    
    # Add post images and captions
    for i, post in enumerate(posts[:5]):  # Limit to 5 posts for analysis
        display_url = post.get("displayUrl")
        caption = post.get("caption", "")
        likes = post.get("likesCount", 0)
        comments = post.get("commentsCount", 0)
        
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
            Post {i+1}:
            Caption: {caption}
            Likes: {likes}
            Comments: {comments}
            """)
    
    try:
        # Generate content using Gemini
        response = model.generate_content(content_parts)
        text_analysis = response.text.strip()
        
        # Parse JSON response
        try:
            json_start = text_analysis.find("{")
            json_end = text_analysis.rfind("}") + 1
            json_str = text_analysis[json_start:json_end]
            analysis = json.loads(json_str)
        except:
            # If JSON parsing fails, try to extract structured data manually
            analysis = {
                "brand_identity": extract_section(text_analysis, "brand_identity"),
                "messaging_style": extract_section(text_analysis, "messaging_style"),
                "visual_identity": extract_section(text_analysis, "visual_identity"),
                "key_topics": extract_list(text_analysis, "key_topics"),
                "apparent_target_audience": extract_section(text_analysis, "apparent_target_audience"),
                "strengths": extract_list(text_analysis, "strengths"),
                "opportunity_areas": extract_list(text_analysis, "opportunity_areas")
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
    
    # Initialize Gemini model for multimodal input
    model = genai.GenerativeModel('gemini-2.0-pro-vision')
    
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
    for i, post in enumerate(posts[:7]):  # Include more posts for better analysis
        display_url = post.get("displayUrl")
        caption = post.get("caption", "")
        
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
            """)
    
    try:
        # Generate content using Gemini
        response = model.generate_content(content_parts)
        text_analysis = response.text.strip()
        
        # Parse JSON response
        try:
            json_start = text_analysis.find("{")
            json_end = text_analysis.rfind("}") + 1
            json_str = text_analysis[json_start:json_end]
            analysis = json.loads(json_str)
        except:
            # If JSON parsing fails, try to extract structured data manually
            analysis = {
                "is_suitable_icp": "true" in text_analysis.lower() and "false" not in text_analysis.lower(),
                "reasoning": extract_section(text_analysis, "reasoning"),
                "profile_summary": extract_section(text_analysis, "profile_summary"),
                "demographic_indicators": extract_list(text_analysis, "demographic_indicators"),
                "interests": extract_list(text_analysis, "interests"),
                "lifestyle_patterns": extract_list(text_analysis, "lifestyle_patterns"),
                "brand_affinities": extract_list(text_analysis, "brand_affinities"),
                "shopping_behaviors": extract_list(text_analysis, "shopping_behaviors")
            }
        
        # Update follower data with analysis
        follower_data.update({
            "icp_analysis": analysis,
            "is_suitable_icp": analysis.get("is_suitable_icp", False)
        })
        
        return follower_data
    
    except Exception as e:
        print(f"Error analyzing follower content for @{username}: {str(e)}")
        follower_data.update({
            "icp_analysis_error": str(e),
            "is_suitable_icp": False
        })
        return follower_data

async def compare_brand_to_icp(brand_analysis: Dict[str, Any], icp_profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare the brand's messaging with the identified ICPs
    """
    print("Comparing brand identity with ideal customer profiles")
    
    # Initialize Gemini model
    model = genai.GenerativeModel('gemini-2.0-pro')
    
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
        # Generate content using Gemini
        response = model.generate_content(prompt)
        text_analysis = response.text.strip()
        
        # Parse JSON response
        try:
            json_start = text_analysis.find("{")
            json_end = text_analysis.rfind("}") + 1
            json_str = text_analysis[json_start:json_end]
            comparison = json.loads(json_str)
        except:
            # If JSON parsing fails, try to extract structured data manually
            comparison = {
                "alignment_score": extract_number(text_analysis, "alignment_score"),
                "aligned_aspects": extract_list(text_analysis, "aligned_aspects"),
                "opportunity_areas": extract_list(text_analysis, "opportunity_areas"),
                "icp_summary": extract_section(text_analysis, "icp_summary"),
                "recommendations": extract_list(text_analysis, "recommendations")
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
    for icp in icp_profiles:
        username = icp.get("username")
        print(f"Finding prospects from followers of @{username}")
        
        try:
            # Get followers of this ICP
            followers = await collect_instagram_followers(username, limit=20)
            
            # Choose a random sample of followers to analyze (max 5)
            sample_size = min(5, len(followers))
            follower_sample = random.sample(followers, sample_size) if len(followers) > sample_size else followers
            
            # Analyze each follower in the sample
            for follower in follower_sample:
                follower_username = follower.get("username")
                
                # Skip if username is missing
                if not follower_username:
                    continue
                
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
        
        except Exception as e:
            print(f"Error processing ICP @{username} followers: {str(e)}")
            continue
    
    # Return however many prospects we found (might be less than the limit)
    return all_prospects

async def evaluate_prospect(prospect_data: Dict[str, Any], icp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate if a follower of an ICP would be a good prospect
    """
    username = prospect_data.get("username")
    print(f"Evaluating @{username} as a potential prospect")
    
    # Initialize Gemini model
    model = genai.GenerativeModel('gemini-2.0-pro')
    
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
        # Generate content using Gemini
        response = model.generate_content(prompt)
        text_analysis = response.text.strip()
        
        # Parse JSON response
        try:
            json_start = text_analysis.find("{")
            json_end = text_analysis.rfind("}") + 1
            json_str = text_analysis[json_start:json_end]
            evaluation = json.loads(json_str)
        except:
            # If JSON parsing fails, try to extract structured data manually
            evaluation = {
                "is_good_prospect": "true" in text_analysis.lower() and "false" not in text_analysis.lower(),
                "confidence_score": extract_number(text_analysis, "confidence_score"),
                "fit_reasoning": extract_section(text_analysis, "fit_reasoning"),
                "similarities_to_icp": extract_list(text_analysis, "similarities_to_icp"),
                "potential_interests": extract_list(text_analysis, "potential_interests"),
                "approach_suggestions": extract_section(text_analysis, "approach_suggestions")
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

async def process_brand(brand: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single brand through the entire analysis pipeline
    """
    name = brand.get("name", "Unknown")
    url = brand.get("url", "")
    instagram_handle = brand.get("instagram_handle", "")
    
    print(f"\n=== Processing Brand: {name} (@{instagram_handle}) ===\n")
    
    try:
        # 1. Collect brand's Instagram profile data
        profile_data = await collect_instagram_profile(instagram_handle)
        
        # 2. Collect brand's posts
        posts = await collect_instagram_posts(instagram_handle, limit=10)
        
        # 3. Analyze brand profile and posts
        brand_analysis = await analyze_brand_profile(profile_data, posts)
        
        # 4. Collect a sample of followers
        followers = await collect_instagram_followers(instagram_handle, limit=50)
        
        # 5. Filter and sample followers for ICP analysis
        print(f"Found {len(followers)} followers, filtering for analysis...")
        
        # Shuffle followers to get a random sample
        random.shuffle(followers)
        
        # Analyze followers to find potential ICPs (public profiles with enough content)
        potential_icps = []
        for follower in followers[:20]:  # Analyze up to 20 followers
            username = follower.get("username")
            if not username:
                continue
                
            # Check if this follower is a potential ICP
            follower_profile = await analyze_follower_profile(username)
            
            # If profile is valid for ICP analysis, add to potential ICPs
            if follower_profile.get("is_valid_icp", False):
                potential_icps.append(follower_profile)
                
                # If we have enough potential ICPs, stop analysis
                if len(potential_icps) >= 5:
                    break
            
            # Rate limiting between API calls
            await asyncio.sleep(1)
        
        print(f"Found {len(potential_icps)} potential ICPs for further analysis")
        
        # 6. Analyze each potential ICP's content
        analyzed_icps = []
        for potential_icp in potential_icps:
            icp_analysis = await analyze_follower_content(potential_icp)
            
            # Only include suitable ICPs
            if icp_analysis.get("is_suitable_icp", False) or \
               (icp_analysis.get("icp_analysis", {}) and icp_analysis.get("icp_analysis", {}).get("is_suitable_icp", False)):
                analyzed_icps.append(icp_analysis)
            
            # If we have enough analyzed ICPs, stop
            if len(analyzed_icps) >= 3:
                break
            
            # Rate limiting between API calls
            await asyncio.sleep(1)
        
        # 7. Compare brand to ICP
        brand_icp_comparison = await compare_brand_to_icp(brand_analysis, analyzed_icps) if analyzed_icps else {}
        
        # 8. Find potential prospects from ICP followers
        potential_prospects = await find_potential_prospects(analyzed_icps, limit=3) if analyzed_icps else []
        
        # 9. Compile and return results
        results = {
            "brand": {
                "name": name,
                "url": url,
                "instagram_handle": instagram_handle
            },
            "brand_profile": profile_data,
            "brand_analysis": brand_analysis,
            "follower_sample_size": len(followers),
            "ideal_customer_profiles": [
                {
                    "username": icp.get("username"),
                    "profile_url": f"https://instagram.com/{icp.get('username')}",
                    "profile_summary": icp.get("icp_analysis", {}).get("profile_summary", ""),
                    "fit_reasoning": icp.get("icp_analysis", {}).get("reasoning", ""),
                    "interests": icp.get("icp_analysis", {}).get("interests", []),
                    "demographic_indicators": icp.get("icp_analysis", {}).get("demographic_indicators", [])
                }
                for icp in analyzed_icps
            ],
            "brand_icp_comparison": brand_icp_comparison,
            "potential_prospects": [
                {
                    "username": prospect.get("username"),
                    "profile_url": f"https://instagram.com/{prospect.get('username')}",
                    "source_icp": prospect.get("source_icp"),
                    "fit_reasoning": prospect.get("evaluation", {}).get("fit_reasoning", ""),
                    "confidence_score": prospect.get("evaluation", {}).get("confidence_score", 0),
                    "similarities_to_icp": prospect.get("evaluation", {}).get("similarities_to_icp", []),
                    "approach_suggestions": prospect.get("evaluation", {}).get("approach_suggestions", "")
                }
                for prospect in potential_prospects
            ],
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
        }
        
        # Save results to file
        save_results(instagram_handle, results)
        
        return results
    
    except Exception as e:
        error_message = f"Error processing brand {name}: {str(e)}"
        print(error_message)
        
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
    
    # Process each brand sequentially
    for brand in brands:
        await process_brand(brand)
        print("\n" + "="*50 + "\n")
    
    print("All brands processed successfully!")

# ==========================================
# Command-line Interface
# ==========================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Instagram Analysis and Prospect Discovery Tool")
    parser.add_argument("--brand", type=str, help="Process a single brand by Instagram handle")
    parser.add_argument("--list", action="store_true", help="List all available brands")
    
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
                asyncio.run(process_brand(brand))
            else:
                print(f"Brand with Instagram handle @{args.brand} not found.")
        except FileNotFoundError:
            print("No brands.json file found.")
    else:
        # Process all brands
        asyncio.run(main())