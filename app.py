#!/usr/bin/env python3
"""
Instagram Analysis App
---------------------
Main application for running Instagram analysis for both brands and users.
"""

import os
import sys
import asyncio
import argparse
from typing import Dict, List, Any, Optional

# Import brand analysis
from brand_analyzer import process_brand, save_results as save_brand_results

# Import user analysis
from user_analyzer import process_user, save_results as save_user_results

# Import data collection
from apify.instagram_profile import check_profile_visibility

async def analyze_instagram_handle(handle: str, analysis_type: Optional[str] = None, 
                                   use_llm: bool = True, quality_threshold: int = 30) -> Dict[str, Any]:
    """
    Analyze an Instagram handle, automatically determining if it's a brand or user
    
    Args:
        handle: Instagram handle to analyze
        analysis_type: Force 'brand' or 'user' analysis, or None to auto-detect
        use_llm: Whether to use LLM for analysis
        quality_threshold: Quality threshold for comments (brand analysis only)
        
    Returns:
        Analysis results
    """
    # If analysis type not specified, try to determine automatically
    if not analysis_type:
        print(f"Auto-detecting account type for @{handle}...")
        
        try:
            # Check profile visibility
            visibility = await check_profile_visibility(handle)
            
            if not visibility.get("exists"):
                print(f"Profile @{handle} does not exist")
                return {"error": f"Profile @{handle} does not exist"}
            
            # Check if it's a business account
            is_business = visibility.get("is_business", False)
            
            # For now, treat business accounts as brands and personal accounts as users
            if is_business:
                analysis_type = "brand"
                print(f"Detected @{handle} as a business account, using brand analysis")
            else:
                analysis_type = "user"
                print(f"Detected @{handle} as a personal account, using user analysis")
                
        except Exception as e:
            print(f"Error detecting account type: {str(e)}")
            print("Defaulting to user analysis")
            analysis_type = "user"
    
    # Perform the appropriate analysis
    if analysis_type == "brand":
        # Create brand data structure
        brand_data = {
            "name": handle.capitalize(),  # Default to capitalized handle as name
            "instagram_handle": handle,
            "url": f"https://www.instagram.com/{handle}/"
        }
        
        # Run brand analysis
        results = await process_brand(brand_data, quality_threshold=quality_threshold)
        return results
        
    else:  # Default to user analysis
        # Run user analysis
        results = await process_user(handle, use_llm=use_llm)
        return results

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Instagram Analysis Tool")
    
    # General arguments
    parser.add_argument("handle", nargs="?", help="Instagram handle to analyze")
    parser.add_argument("--type", choices=["brand", "user"], help="Force analysis type (brand or user)")
    parser.add_argument("--file", type=str, help="Process multiple handles from a JSON file")
    parser.add_argument("--no-llm", action="store_true", help="Use rule-based analysis instead of LLM")
    
    # Brand-specific arguments
    parser.add_argument("--quality-threshold", type=int, default=30, 
                        help="Minimum quality score for comments in brand analysis (default: 30)")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Check if we have enough information to proceed
    if not args.handle and not args.file:
        parser.print_help()
        print("\nError: You must specify either an Instagram handle or a file")
        return
    
    use_llm = not args.no_llm
    
    if args.handle:
        # Process a single handle
        await analyze_instagram_handle(
            args.handle, 
            analysis_type=args.type, 
            use_llm=use_llm, 
            quality_threshold=args.quality_threshold
        )
    
    elif args.file:
        # Process multiple handles from a file
        import json
        
        try:
            with open(args.file, 'r') as f:
                data = json.load(f)
            
            # File format determination
            if isinstance(data, list):
                # List of handles or objects
                handles = []
                
                for item in data:
                    if isinstance(item, str):
                        # Just a handle
                        handles.append({"handle": item, "type": args.type})
                    elif isinstance(item, dict):
                        # Object with configuration
                        if "handle" in item or "instagram_handle" in item:
                            handle = item.get("handle", item.get("instagram_handle"))
                            handles.append({
                                "handle": handle,
                                "type": item.get("type", args.type),
                                "name": item.get("name"),
                                "url": item.get("url")
                            })
                
                if not handles:
                    print(f"No valid Instagram handles found in {args.file}")
                    return
                
                print(f"Processing {len(handles)} Instagram accounts from {args.file}")
                
                for item in handles:
                    handle = item["handle"]
                    analysis_type = item["type"]
                    
                    if analysis_type == "brand" and "name" in item:
                        # Brand with additional information
                        brand_data = {
                            "name": item["name"],
                            "instagram_handle": handle,
                            "url": item.get("url", f"https://www.instagram.com/{handle}/")
                        }
                        
                        await process_brand(brand_data, quality_threshold=args.quality_threshold)
                    else:
                        # Regular analysis
                        await analyze_instagram_handle(
                            handle, 
                            analysis_type=analysis_type, 
                            use_llm=use_llm,
                            quality_threshold=args.quality_threshold
                        )
                    
                    print("\n" + "="*50 + "\n")
                
                print("All accounts processed successfully!")
            
            else:
                print(f"Invalid format in {args.file}. Expected a list.")
        
        except FileNotFoundError:
            print(f"File not found: {args.file}")
        except json.JSONDecodeError:
            print(f"Invalid JSON in file: {args.file}")
        except Exception as e:
            import traceback
            print(f"Error processing file {args.file}: {str(e)}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 