#!/usr/bin/env python3
"""
Instagram User Analyzer
-----------------------
A tool to analyze Instagram user profiles and their influence metrics.
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
from apify.instagram_profile import collect_instagram_profile, check_profile_visibility
from apify.instagram_posts import collect_instagram_posts, collect_user_profile_posts

# Import user analysis functions
from analysis.users.user_analysis import analyze_user_profile_with_llm
from analysis.users.influence_analysis import analyze_user_influence_with_llm, analyze_user_influence

# Make sure directories exist
os.makedirs("results", exist_ok=True)

async def process_user(username: str, use_llm: bool = True) -> Dict[str, Any]:
    """
    Process a single Instagram user through the analysis pipeline
    
    Args:
        username: Instagram username to analyze
        use_llm: Whether to use LLM for analysis (if False, uses rule-based)
        
    Returns:
        Dictionary with analysis results
    """
    print(f"\n=== Processing User: @{username} ===\n")
    
    try:
        # 1. Check if profile exists and is accessible
        print("Step 1/4: Checking profile visibility...")
        visibility = await check_profile_visibility(username)
        
        if not visibility.get("exists"):
            raise Exception(f"Profile @{username} does not exist")
            
        if visibility.get("is_private") and not visibility.get("is_business"):
            print(f"⚠️ Profile @{username} is private")
            # We can still collect limited data for private profiles
        
        print(f"✓ Profile exists and is {'public' if visibility.get('is_public') else 'private'}")
        
        # 2. Collect user profile and posts
        print("Step 2/4: Collecting profile data...")
        user_profile = await collect_user_profile_posts(username, limit=5)
        
        if not user_profile:
            raise Exception(f"Could not retrieve profile data for @{username}")
            
        profile_data = user_profile.get("profile_data", {})
        posts = user_profile.get("posts", [])
        
        print(f"✓ Successfully collected profile data and {len(posts)} posts")
        
        # 3. Analyze user profile
        print("Step 3/4: Analyzing user profile...")
        
        if use_llm:
            # Use LLM for analysis
            user_analysis = await analyze_user_influence_with_llm(user_profile)
            analysis_method = "llm"
        else:
            # Use rule-based analysis
            user_analysis = await analyze_user_influence(user_profile)
            analysis_method = "rule-based"
            
        print("✓ Successfully analyzed user profile")
        
        # 4. Prepare results
        print("Step 4/4: Preparing results...")
        
        results = {
            "username": username,
            "profile_data": profile_data,
            "posts_sample": posts[:3],  # Include 3 sample posts
            "user_analysis": user_analysis,
            "analysis_metadata": {
                "timestamp": datetime.now().isoformat(),
                "analysis_method": analysis_method,
                "is_private_profile": visibility.get("is_private", True),
                "is_business_profile": visibility.get("is_business", False),
                "status": "completed"
            }
        }
        
        # Save results to disk
        save_results(username, results)
        print("✓ Analysis complete")
        
        return results
        
    except Exception as e:
        print(f"Error processing user @{username}: {str(e)}")
        traceback.print_exc()
        
        # Save error results
        error_results = {
            "username": username,
            "error": str(e),
            "analysis_metadata": {
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error_details": traceback.format_exc()
            }
        }
        
        # Save error results to disk
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = f"results/{username}_{timestamp}_error.json"
        
        with open(result_file, 'w') as f:
            json.dump(error_results, f, indent=2)
            
        print(f"\nError during analysis! Error results saved to {result_file}")
        
        return error_results

def save_results(username: str, results: Dict[str, Any]):
    """Save results to JSON file"""
    os.makedirs("results", exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"results/{username}_{timestamp}.json"
    
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to {result_file}")

async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Instagram User Analysis Tool")
    parser.add_argument("--user", type=str, help="Process a single user by Instagram username")
    parser.add_argument("--file", type=str, help="Process users from a JSON file")
    parser.add_argument("--no-llm", action="store_true", help="Use rule-based analysis instead of LLM")
    
    args = parser.parse_args()
    
    if not args.user and not args.file:
        parser.print_help()
        print("\nError: You must specify either --user or --file")
        return
    
    use_llm = not args.no_llm
    analysis_method = "rule-based" if args.no_llm else "llm"
    print(f"Using {analysis_method} analysis method")
    
    if args.user:
        # Process a single user
        await process_user(args.user, use_llm=use_llm)
    
    elif args.file:
        # Process users from a file
        try:
            with open(args.file, 'r') as f:
                data = json.load(f)
                
            # The file can either be an array of usernames or an array of objects with username field
            if isinstance(data, list):
                usernames = []
                
                for item in data:
                    if isinstance(item, str):
                        usernames.append(item)
                    elif isinstance(item, dict) and "username" in item:
                        usernames.append(item["username"])
                
                if not usernames:
                    print(f"No valid usernames found in file {args.file}")
                    return
                
                print(f"Processing {len(usernames)} users from {args.file}")
                
                for username in usernames:
                    await process_user(username, use_llm=use_llm)
                    print("\n" + "="*50 + "\n")
                
                print("All users processed successfully!")
            
            else:
                print(f"Invalid format in {args.file}. Expected a list.")
        
        except FileNotFoundError:
            print(f"File not found: {args.file}")
        except json.JSONDecodeError:
            print(f"Invalid JSON in file: {args.file}")
        except Exception as e:
            print(f"Error processing file {args.file}: {str(e)}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 