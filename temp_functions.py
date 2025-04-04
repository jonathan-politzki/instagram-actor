# AI-based Username Analysis Functions

async def identify_real_people_from_usernames(usernames: List[str], brand_handle: str) -> List[Dict[str, Any]]:
    """
    Uses Gemini to analyze a batch of Instagram usernames to identify those likely belonging to real people.
    Returns a list of dictionaries with username and classification information.
    
    Args:
        usernames: List of Instagram usernames to analyze
        brand_handle: The brand's Instagram handle for context
    
    Returns:
        List of dictionaries with username classification
    """
    if not usernames:
        return []
        
    print(f"Analyzing {len(usernames)} usernames with AI to identify real people...")
    
    # Split into smaller batches to avoid token limits
    batch_size = 40
    results = []
    
    for i in range(0, len(usernames), batch_size):
        batch = usernames[i:i+batch_size]
        
        # Format usernames for prompt
        formatted_usernames = "\n".join([f"{idx+1}. @{username}" for idx, username in enumerate(batch)])
        
        prompt = f"""
        Analyze these Instagram usernames associated with the @{brand_handle} brand and classify each as:
        1. "likely_person" - Probably a real person's account
        2. "likely_business" - Probably a business/brand account
        3. "likely_bot" - Probably a bot or fake account
        
        For those classified as "likely_person", estimate:
        - If they're likely a genuine engaged user (vs. casual follower or mass-follower)
        - Their estimated value as a brand connection (high/medium/low)
        
        Usernames to analyze:
        {formatted_usernames}
        
        Respond with VALID JSON only, in this format:
        {{
            "classifications": [
                {{
                    "username": "username1",
                    "category": "likely_person",
                    "engagement_quality": "high",
                    "reasoning": "Brief reason for classification"
                }},
                {{
                    "username": "username2",
                    "category": "likely_bot",
                    "reasoning": "Brief reason for classification"
                }}
            ]
        }}
        """
        
        try:
            # Use our JSON helper function
            response = await get_gemini_json_response('gemini-1.5-flash', [prompt], retries=1)
            
            if "classifications" in response and isinstance(response["classifications"], list):
                batch_results = response["classifications"]
                results.extend(batch_results)
            else:
                print(f"Warning: Invalid response format for username analysis batch {i//batch_size + 1}")
        except Exception as e:
            print(f"Error analyzing username batch {i//batch_size + 1}: {str(e)}")
            continue
    
    # Filter to focus on real people
    real_people = [r for r in results if r.get("category") == "likely_person"]
    high_value = [r for r in real_people if r.get("engagement_quality") == "high"]
    medium_value = [r for r in real_people if r.get("engagement_quality") == "medium"]
    
    print(f"AI analysis complete: {len(real_people)} likely real people identified")
    print(f"  - High-value connections: {len(high_value)}")
    print(f"  - Medium-value connections: {len(medium_value)}")
    
    # Sort by engagement quality
    quality_order = {"high": 3, "medium": 2, "low": 1}
    real_people.sort(key=lambda x: quality_order.get(x.get("engagement_quality", "low"), 0), reverse=True)
    
    return real_people

async def enhanced_audience_collection(instagram_handle: str, limit: int = 50, quality_threshold: int = 60) -> List[Dict[str, Any]]:
    """
    A more sophisticated approach to collect an audience for analysis that combines:
    1. Traditional comment quality filtering with sentiment analysis
    2. Hashtag-based collection with relevance filtering
    3. AI-based username analysis to identify real people
    
    This function prioritizes finding authentic human engagement over quantity.
    """
    print(f"🔍 Enhanced audience collection for @{instagram_handle}")
    print(f"  Using comment quality threshold: {quality_threshold}")
    
    # First collect the standard way (comments + hashtags with filtering)
    standard_users = await collect_instagram_followers(instagram_handle, limit=limit*2, quality_threshold=quality_threshold)
    
    if not standard_users:
        print("No standard users found. Trying alternate collection methods...")
        # Could implement fallback strategies here
        return []
    
    # Extract usernames
    all_usernames = [user.get("username") for user in standard_users if user.get("username")]
    
    # Now analyze these usernames to find real people
    real_people_data = await identify_real_people_from_usernames(all_usernames, instagram_handle)
    
    # Convert to a dictionary for easy lookup
    real_people_dict = {entry.get("username"): entry for entry in real_people_data}
    
    # Enhance the original user data with AI analysis
    enhanced_users = []
    for user in standard_users:
        username = user.get("username", "")
        if username in real_people_dict:
            # Enhance with AI analysis
            ai_data = real_people_dict[username]
            user["ai_classification"] = ai_data.get("category", "unknown")
            user["ai_engagement_quality"] = ai_data.get("engagement_quality", "low")
            user["ai_reasoning"] = ai_data.get("reasoning", "")
            
            # Calculate a combined quality score incorporating both
            # the comment quality and AI analysis
            comment_quality = user.get("quality_score", 50)
            
            # Map engagement quality to score boost
            ai_quality_boost = {
                "high": 30,
                "medium": 15,
                "low": 5,
                "unknown": 0
            }.get(ai_data.get("engagement_quality", "unknown"), 0)
            
            # Only boost score if it's a likely person
            if ai_data.get("category") == "likely_person":
                user["combined_quality_score"] = min(100, comment_quality + ai_quality_boost)
            else:
                user["combined_quality_score"] = max(0, comment_quality - 20)  # Penalize non-people
                
            enhanced_users.append(user)
        else:
            # Keep original data but mark as not analyzed
            user["ai_classification"] = "not_analyzed"
            user["combined_quality_score"] = user.get("quality_score", 30)
            enhanced_users.append(user)
    
    # Sort by combined quality score
    enhanced_users.sort(key=lambda x: x.get("combined_quality_score", 0), reverse=True)
    
    # Filter to only include likely_person with decent scores
    filtered_users = [
        u for u in enhanced_users 
        if (u.get("ai_classification") == "likely_person" and u.get("combined_quality_score", 0) >= quality_threshold)
        or (u.get("ai_classification") == "not_analyzed" and u.get("combined_quality_score", 0) >= quality_threshold + 10)
    ]
    
    print(f"Enhanced audience collection complete:")
    print(f"  - Starting users: {len(standard_users)}")
    print(f"  - After AI person filtering: {len(filtered_users)}")
    
    # Return the top results up to the limit
    return filtered_users[:limit] 