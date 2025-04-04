# Instagram Analysis & Prospect Discovery System

A tool that analyzes Shopify stores' Instagram profiles, identifies their ideal customer profiles (ICPs) from followers, and discovers potential customer prospects from the followers of those ideal customers.

## Overview

This system helps ecommerce brands discover potential customers by analyzing the social graphs of their existing followers. It identifies patterns in the followers' profiles, determines which followers represent the "ideal customer," and then finds similar profiles that could be potential new customers.

## Current Implementation Status

- ✅ Brand profile collection
- ✅ Brand posts collection
- ⚠️ Brand analysis (text-only version implemented)
- 🔄 Follower collection (modified to use Instagram Scraper)
- 🔄 ICP identification
- 🔄 Brand-ICP comparison
- 🔄 Prospect discovery

## System Workflow

1. **Brand Analysis**: Analyze the brand's Instagram profile to understand their brand identity, messaging, and visual style
2. **Follower Discovery**: Analyze a sample of the brand's followers (with public profiles)
3. **ICP Identification**: Determine the ideal customer profile (ICP) based on follower analysis
4. **Brand-ICP Alignment**: Compare the brand's messaging with the ICP to identify opportunities
5. **Prospect Discovery**: Analyze the followers of identified ICPs to find potential new customers

## Data Storage

The system creates various data files:

* **Cache Files**:
  * `cache/{instagram_handle}_profile.json` - Instagram profile data
  * `cache/{instagram_handle}_posts.json` - Instagram posts
  * `cache/{instagram_handle}_followers.json` - Instagram followers
  * `cache/{username}_profile.json` - Follower profile data

* **Results**: `results/{instagram_handle}_{timestamp}.json` - Complete analysis including ICPs and prospects

## Setting Up

### Prerequisites

- Python 3.8+
- Apify API key
- Google Gemini API key

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/instagram-analysis.git
cd instagram-analysis

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
    "name": "Allbirds",
    "url": "https://www.allbirds.com",
    "instagram_handle": "allbirds"
  },
  {
    "name": "Warby Parker",
    "url": "https://www.warbyparker.com",
    "instagram_handle": "warbyparker"
  }
]
```

## Running the System

### Basic Collection (Current Working Mode)

```bash
# List available brands
python instagram_analysis.py --list

# Process a specific brand
python instagram_analysis.py --brand allbirds

# Process all brands
python instagram_analysis.py
```

### Full Analysis (Coming Soon)

The full analysis pipeline will be enabled once all components are tested and working.

## Output Data Format

The current output includes basic profile and post data:

```json
{
  "brand": {
    "name": "Brand Name",
    "url": "https://store-url.com",
    "instagram_handle": "brandname"
  },
  "brand_profile": {
    "username": "brandname",
    "fullName": "Brand Name",
    "biography": "Brand description...",
    "followersCount": 12345,
    "followingCount": 543,
    "postsCount": 321,
    "isBusinessAccount": true
  },
  "posts_sample": [
    {
      "type": "Image",
      "caption": "Post caption...",
      "likesCount": 123,
      "commentsCount": 45
    }
  ],
  "timestamp": "2025-04-03T21:37:16.123Z",
  "status": "completed"
}
```

Future versions will include full analysis with:
- Brand analysis (identity, messaging style, visual identity)
- Ideal customer profiles
- Brand-ICP comparison
- Potential prospects

## Development Roadmap

1. ✅ **Phase 1**: Basic data collection infrastructure
   - Instagram profile and post collection

2. 🔄 **Phase 2**: Analysis implementation
   - Brand analysis
   - Follower collection and filtering
   - ICP identification

3. 🔄 **Phase 3**: Discovery implementation
   - Brand-ICP comparison
   - Prospect identification
   - Fit reasoning

4. 🔄 **Phase 4**: Integration and refinement
   - UI development
   - Rate limiting and error handling improvements
   - Documentation and examples

## Technical Notes

- This tool uses Apify's Instagram scrapers for data collection
- Analysis is performed using Google's Gemini AI models
- The system implements caching to prevent redundant API calls
- All data is stored locally for privacy and cost efficiency

## Troubleshooting

### Common Issues

- **API Key Errors**: Ensure your `.env` file has the correct API keys
- **Rate Limiting**: Instagram may rate-limit scraping. Adding delays between requests can help
- **Missing Data**: Some profiles may be private or have limited content

### Debug Mode

For detailed logging during execution, run with the debug flag (coming soon):

```bash
python instagram_analysis.py --brand allbirds --debug
```

## License

[MIT License](LICENSE)