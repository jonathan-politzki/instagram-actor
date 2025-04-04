# Instagram Analysis & Prospect Discovery System

A tool that analyzes Instagram profiles, identifies ideal customer profiles (ICPs) from followers and engaged users, and helps brands understand their audience for improved marketing strategies. It can also analyze individual Instagram user profiles for influence metrics.

## Overview

This system combines AI and rule-based approaches to:
1. Analyze Instagram brand profiles
2. Analyze Instagram user profiles
3. Identify engaged users and potential ideal customers
4. Filter for real people vs. bots or businesses
5. Generate marketing insights and recommendations

## Current Implementation Status

- ✅ Brand profile and posts collection via Apify
- ✅ User profile and influence analysis
- ✅ Comment collection and analysis
- ✅ User filtering based on quality thresholds
- ✅ Public profile detection to save analysis time
- ✅ User classification (real people vs. bots)
- ✅ AI-powered analysis using Google's Gemini models
- ✅ Basic audience insights generation
- ✅ Command-line interface with various options
- ✅ Modular architecture separating data collection from analysis

## Project Structure

The project is organized into the following structure:

```
instagram-actor/
├── apify/                      # Data collection via Apify
│   ├── client.py               # Apify client configuration
│   ├── instagram_profile.py    # Profile data collection
│   ├── instagram_posts.py      # Posts data collection
│   ├── instagram_comments.py   # Comments data collection
│   └── instagram_hashtags.py   # Hashtag data collection
│
├── analysis/                   # Analysis logic 
│   ├── common/                 # Shared analysis functions
│   │   └── llm_client.py       # LLM API client (Gemini)
│   │
│   ├── brands/                 # Brand-specific analysis
│   │   ├── brand_analysis.py   # Brand profile analysis
│   │   └── audience_analysis.py # Brand audience analysis
│   │
│   └── users/                  # User-specific analysis
│       ├── user_analysis.py    # User profile analysis
│       └── influence_analysis.py # User influence analysis
│
├── utils/                      # Utility functions
│   ├── cache.py                # Caching utilities
│   ├── rate_limit.py           # Rate limiting
│   └── image_utils.py          # Image processing utilities
│
├── app.py                      # Main coordinator application
├── brand_analyzer.py           # Command-line tool for brand analysis
├── user_analyzer.py            # Command-line tool for user analysis
```

## System Components

### Data Collection (apify/)
- Instagram profile data collection
- Post collection with engagement metrics
- Comment extraction and quality analysis
- User profile analysis

### Brand Analysis (analysis/brands/)
- Brand profile analysis with LLM
- Audience analysis and segmentation
- Engaged user identification
- Content recommendations

### User Analysis (analysis/users/)
- User profile analysis with LLM
- Influence metrics calculation
- Content theme detection
- Engagement quality assessment

### Utilities (utils/)
- Caching system for API responses
- Rate limiting for Apify requests
- Image processing for LLM analysis

### Output
- Brand analysis including tone, style, and positioning
- Ideal customer profile identification
- Audience demographics and interests
- Content and engagement recommendations
- User influence metrics and brand alignment potential

## Data Storage

The system creates various data files:

* **Cache Files**: Stored in the `cache/` directory
  * Profile data, posts, followers, and other API responses

* **Results**: Stored in the `results/` directory
  * Brand analysis results
  * User analysis results
  * Includes timestamps for tracking

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

### Main Application (Recommended)

The `app.py` script is the main entry point that can handle both brand and user analysis:

```bash
# Auto-detect and analyze an Instagram handle
python app.py instagramhandle

# Force brand analysis
python app.py instagramhandle --type brand

# Force user analysis
python app.py instagramhandle --type user

# Process multiple handles from a JSON file
python app.py --file handles.json

# Use rule-based analysis instead of LLM
python app.py instagramhandle --no-llm
```

### Brand Analysis

```bash
# List available brands in brands.json
python brand_analyzer.py --list

# Process a specific brand
python brand_analyzer.py --brand brandname

# Process all brands in brands.json
python brand_analyzer.py

# Set quality threshold (0-100) for filtering - lower values cast a wider net
python brand_analyzer.py --quality-threshold 30
```

### User Analysis

```bash
# Analyze a single user
python user_analyzer.py --user username

# Process multiple users from a JSON file
python user_analyzer.py --file users.json

# Use rule-based analysis instead of LLM
python user_analyzer.py --user username --no-llm
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
- User influence characteristics

### Public Profile Detection

The system pre-checks if profiles are public before attempting deeper analysis, saving time and API calls.

### Modular Architecture

The new architecture separates:
- Data collection (Apify calls)
- Analysis logic (both LLM-based and rule-based)
- Utilities (caching, rate limiting)
- Command-line interfaces

This allows for:
- Easier maintenance
- Better code organization
- Flexibility to add new features
- Support for both brand and user analysis

## Technical Implementation

### Key Modules

- **apify/**: Handles all Instagram data collection
- **analysis/brands/**: Brand analysis logic
- **analysis/users/**: User analysis logic
- **utils/**: Shared utilities
- **app.py**: Main coordinator
- **brand_analyzer.py**: Brand-specific CLI
- **user_analyzer.py**: User-specific CLI

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