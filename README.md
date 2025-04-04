# Instagram Analysis & Prospect Discovery System

A tool that analyzes Instagram profiles, identifies ideal customer profiles (ICPs) from followers and engaged users, and helps brands understand their audience for improved marketing strategies.

## Overview

This system combines AI and rule-based approaches to:
1. Analyze Instagram brand profiles
2. Identify engaged users and potential ideal customers
3. Filter for real people vs. bots or businesses
4. Generate marketing insights and recommendations

## Current Implementation Status

- ✅ Brand profile and posts collection via Apify
- ✅ Comment collection and analysis
- ✅ User filtering based on quality thresholds
- ✅ Public profile detection to save analysis time
- ✅ User classification (real people vs. bots)
- ✅ AI-powered analysis using Google's Gemini models
- ✅ Basic audience insights generation
- ✅ Command-line interface with various options

## System Components

### Data Collection
- Instagram profile data collection
- Post collection with engagement metrics
- Comment extraction and quality analysis
- User profile analysis

### Analysis Features
- Comment quality scoring (0-100)
- Bot detection using pattern recognition
- Public profile detection before deeper analysis
- Username pattern analysis for filtering
- AI-enhanced profile and content analysis

### Output
- Brand analysis including tone, style, and positioning
- Ideal customer profile identification
- Audience demographics and interests
- Content and engagement recommendations

## Data Storage

The system creates various data files:

* **Cache Files**:
  * `cache/{instagram_handle}_profile.json` - Instagram profile data
  * `cache/{instagram_handle}_posts.json` - Instagram posts
  * `cache/{instagram_handle}_followers.json` - Instagram followers
  * `cache/{username}_profile.json` - Follower profile data

* **Results**: `results/{instagram_handle}_{timestamp}.json` - Complete analysis including ICPs and insights

## Setting Up

### Prerequisites

- Python 3.8+
- Apify API key
- Google Gemini API key

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/instagram-actor.git
cd instagram-actor

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file with API keys
echo "APIFY_API_KEY=your_apify_key_here" > .env
echo "GEMINI_API_KEY=your_gemini_key_here" >> .env
```

### Create Brand List

Create a `brands.json` file with your target brands:

```json
[
  {
    "name": "Brand Name",
    "url": "https://www.brand-website.com",
    "instagram_handle": "brandname"
  }
]
```

## Running the System

### Command Line Options

```bash
# List available brands
python instagram_analysis.py --list

# Process a specific brand
python instagram_analysis.py --brand brandname

# Process all brands
python instagram_analysis.py

# Set quality threshold (0-100) for filtering - lower values cast a wider net
python instagram_analysis.py --quality-threshold 30

# Manually add known engaged users
python instagram_analysis.py --add-engaged-users brandname,user1,user2,user3
```

## Key Features

### Quality Filtering and Bot Detection

The system uses several approaches to identify real, engaged users:
- Comment quality scoring based on length, sentiment, and content
- Bot detection using common patterns in usernames and comments
- AI-based username analysis to distinguish real people from businesses/bots

### LLM-Enhanced Analysis

Google's Gemini models provide deeper analysis:
- Brand profile and messaging analysis
- User profile interpretation
- Audience segment identification
- Content and engagement recommendations

### Public Profile Detection

The system now pre-checks if profiles are public before attempting deeper analysis, saving time and API calls.

### Customizable Quality Thresholds

You can adjust the quality threshold to balance between:
- Higher thresholds (70+): Stricter filtering, fewer but higher quality results
- Medium thresholds (30-70): Balanced approach
- Lower thresholds (<30): Cast a wider net, more results but potentially lower quality

## Technical Implementation

### Key Algorithms

- `analyze_comment_quality`: Evaluates comments on multiple dimensions
- `identify_real_people_from_usernames`: Uses AI to classify usernames
- `enhanced_audience_collection`: Combines multiple filtering methods
- `check_profile_visibility`: Efficiently determines if profiles are public
- `analyze_brand_profile_with_llm` & `analyze_user_profile_with_llm`: AI-driven analysis

### API Dependencies

- **Apify**: Instagram data collection (profile scraper, post scraper, comment scraper)
- **Google Gemini**: AI-powered analysis and insights generation

## Troubleshooting

### Common Issues

- **API Key Errors**: Ensure your `.env` file has the correct API keys
- **Rate Limiting**: Instagram may rate-limit scraping. The code includes built-in rate limiting.
- **Missing Data**: Private profiles will have limited data available
- **Timeout Errors**: Network issues or slow API responses may cause timeouts

### Performance Optimizations

- Caching system to prevent redundant API calls
- Parallel processing using asyncio for checking multiple profiles
- Rate limiting to prevent API throttling
- AI model selection based on task complexity

## License

[MIT License](LICENSE)