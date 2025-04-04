#!/usr/bin/env python3
"""
Instagram Brand Analyzer
-----------------------
A tool to analyze Instagram brand profiles and their audience.
"""

import os
import json
import asyncio
import sys
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional
import argparse

# Import data collection functions
from apify.instagram_profile import collect_instagram_profile
from apify.instagram_posts import collect_instagram_posts

# Import brand analysis functions
from analysis.brands.brand_analysis import analyze_brand_profile_with_llm
from analysis.brands.audience_analysis import (
    generate_audience_insights_with_llm,
    identify_real_people_from_usernames
)

# Import user analysis functions
from analysis.users.user_analysis import analyze_user_profile_with_llm

# Import from audience analysis module
from analysis.brands.audience_analysis import enhanced_audience_collection

# Make sure directories exist
os.makedirs("results", exist_ok=True)

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
            user_profile = {}
            
            # Import here to avoid circular imports
            from apify.instagram_posts import collect_user_profile_posts
            
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

def save_results(instagram_handle: str, results: Dict[str, Any]):
    """Save results to JSON file"""
    os.makedirs("results", exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"results/{instagram_handle}_{timestamp}.json"
    
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to {result_file}")

async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Instagram Brand Analysis Tool")
    parser.add_argument("--brand", type=str, help="Process a single brand by Instagram handle")
    parser.add_argument("--list", action="store_true", help="List all available brands")
    parser.add_argument("--quality-threshold", type=int, default=30, help="Minimum quality score (0-100) for comments (default: 30)")
    parser.add_argument("--brands-file", type=str, default="brands.json", help="JSON file containing brands to analyze")
    
    args = parser.parse_args()
    
    # Path to brands file
    brands_file = args.brands_file
    
    # Load target brands from JSON file
    try:
        with open(brands_file, 'r') as f:
            brands = json.load(f)
    except FileNotFoundError:
        print(f"{brands_file} not found. Creating sample file...")
        
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
        
        with open(brands_file, 'w') as f:
            json.dump(sample_brands, f, indent=2)
        
        brands = sample_brands
    
    if args.list:
        # List all available brands
        print("\nAvailable brands:")
        for i, brand in enumerate(brands):
            print(f"{i+1}. {brand.get('name')} (@{brand.get('instagram_handle')})")
        print()
        return
    
    elif args.brand:
        # Process a single brand by Instagram handle
        brand = next((b for b in brands if b.get("instagram_handle") == args.brand), None)
        
        if brand:
            await process_brand(brand, quality_threshold=args.quality_threshold)
        else:
            print(f"Brand with Instagram handle @{args.brand} not found.")
    
    else:
        # Process all brands
        print(f"Processing {len(brands)} brands...")
        
        for brand in brands:
            await process_brand(brand, quality_threshold=args.quality_threshold)
            print("\n" + "="*50 + "\n")
        
        print("All brands processed successfully!")

if __name__ == "__main__":
    asyncio.run(main()) 