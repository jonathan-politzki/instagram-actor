# instagram-actor
Actor that analyzes company Instagram pages and their followers and their followers' followers.

# Instagram Analysis & Prospect Discovery System

A tool that analyzes Shopify stores' Instagram profiles, identifies their ideal customer profiles (ICPs) from followers, and discovers potential customer prospects from the followers of those ideal customers.

## Overview

This system helps ecommerce brands discover potential customers by analyzing the social graphs of their existing followers. It identifies patterns in the followers' profiles, determines which followers represent the "ideal customer," and then finds similar profiles that could be potential new customers.

## System Workflow

1. **Brand Analysis**: Analyze the brand's Instagram profile to understand their brand identity, messaging, and visual style
2. **Follower Discovery**: Analyze a sample of the brand's followers (with public profiles)
3. **ICP Identification**: Determine the ideal customer profile (ICP) based on follower analysis
4. **Brand-ICP Alignment**: Compare the brand's messaging with the ICP to identify opportunities
5. **Prospect Discovery**: Analyze the followers of identified ICPs to find potential new customers

## Data Structure

The system creates two primary data files:

* **Cache**: `cache/{instagram_handle}_data.json` - Raw Instagram data including profile and posts
* **Results**: `results/{instagram_handle}_{timestamp}.json` - Complete analysis including ICPs and prospects

## Core Process

### 1. Brand Data Collection

- Input: Brand name, URL, and Instagram username
- Process: Scrape the brand's Instagram profile and posts
- Output: Brand profile data, messaging style, visual identity

### 2. Follower Analysis

- Input: Brand's Instagram followers
- Process: Filter for public profiles with substantial content (excluding food/pet-only accounts)
- Output: Sample of analyzable follower profiles (20-50 accounts)

### 3. ICP Determination

- Input: Follower sample data
- Process: Analyze patterns in follower profiles, identify common characteristics
- Output: Ideal customer profile description and 2-3 example accounts

### 4. Brand-ICP Comparison

- Input: Brand profile and ICP data
- Process: Compare brand messaging with ICP characteristics
- Output: Alignment analysis and opportunity identification

### 5. Prospect Discovery

- Input: ICP example accounts
- Process: Analyze followers of ICP accounts
- Output: 3-5 potential customer prospects with explanation of fit

## Running the System

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with API keys
echo "APIFY_API_KEY=your_apify_key_here" > .env
echo "GEMINI_API_KEY=your_gemini_key_here" >> .env

# Create a brands.json file with target brands
# Example:
# [
#   {
#     "name": "Brand Name",
#     "url": "https://store-url.com",
#     "instagram_handle": "brandname"
#   }
# ]

# Run the analysis
python instagram_analysis.py
```

## Output Data Format

The result file (`results/{instagram_handle}_{timestamp}.json`) contains:

```json
{
  "brand": {
    "name": "Brand Name",
    "url": "https://store-url.com",
    "instagram_handle": "brandname"
  },
  "brand_analysis": {
    "brand_identity": "Description of brand identity...",
    "messaging_style": "Description of messaging approach...",
    "visual_identity": "Description of visual style...",
    "key_topics": ["Topic 1", "Topic 2", "Topic 3"]
  },
  "follower_analysis": {
    "sample_size": 25,
    "demographics": {
      "age_range": "25-34 primarily",
      "common_locations": ["New York", "Los Angeles", "Chicago"],
      "interests": ["Fashion", "Sustainability", "Travel"]
    }
  },
  "ideal_customer_profiles": [
    {
      "username": "follower1",
      "profile_summary": "Description of this ICP...",
      "fit_reasoning": "Why this represents an ideal customer...",
      "profile_url": "https://instagram.com/follower1"
    },
    {
      "username": "follower2",
      "profile_summary": "Description of this ICP...",
      "fit_reasoning": "Why this represents an ideal customer...",
      "profile_url": "https://instagram.com/follower2"
    }
  ],
  "brand_icp_comparison": {
    "alignment_score": 85,
    "aligned_aspects": ["Visual style", "Value messaging"],
    "opportunity_areas": ["Could better highlight sustainability", "More user-generated content"]
  },
  "potential_prospects": [
    {
      "username": "prospect1",
      "source_icp": "follower1",
      "profile_summary": "Description of this prospect...",
      "fit_reasoning": "Why they would be a good customer...",
      "profile_url": "https://instagram.com/prospect1"
    },
    {
      "username": "prospect2",
      "source_icp": "follower1",
      "profile_summary": "Description of this prospect...",
      "fit_reasoning": "Why they would be a good customer...",
      "profile_url": "https://instagram.com/prospect2"
    }
  ],
  "timestamp": "2025-04-03T14:35:22.123Z"
}
```

## Next Steps

1. Run initial analysis on a few test brands
2. Review the quality of ICP identification
3. Assess the relevance of discovered prospects
4. Build a simple UI to visualize the results

## Technical Components

- Instagram data collection via Apify
- Visual analysis using Google's Gemini Vision API
- Content analysis for profile filtering
- Profile similarity detection
- Structured data storage