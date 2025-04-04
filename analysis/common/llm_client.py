import os
import json
import time
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure API keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("Warning: GEMINI_API_KEY not set. LLM features will not work.")

def get_gemini_json_response(model: str, prompts: List[str], retries: int = 3) -> Dict[str, Any]:
    """
    Makes a structured request to the Gemini API and returns a JSON response
    
    Args:
        model: The Gemini model to use
        prompts: List of prompts to send to the model
        retries: Number of retries in case of failure
        
    Returns:
        JSON response from the Gemini API
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
        
    attempts = 0
    last_error = None
    
    # Convert legacy model names to correct model names based on API documentation
    # Standard stable model names as of April 2025
    if model == "gemini-pro":
        model_name = "gemini-1.5-pro"  # Use the stable 1.5 Pro model
    elif model == "gemini-pro-vision":
        model_name = "gemini-1.5-pro"  # Use the stable 1.5 Pro model which also handles vision
    else:
        model_name = model
    
    # Adding explicit JSON formatting to the prompt
    structured_prompts = []
    for prompt in prompts:
        # Add JSON formatting instructions if not already present
        if "return a JSON" not in prompt.lower() and "respond with json" not in prompt.lower():
            prompt += "\n\nPlease respond with a valid JSON object only. Format your entire response as a valid JSON that can be parsed by JSON.parse()."
        structured_prompts.append(prompt)
    
    while attempts < retries:
        try:
            # Configure the model with the appropriate settings
            generation_config = {
                "temperature": 0.2,
                "top_p": 0.95,
                # response_mime_type is not supported in current API version
            }
            
            # Load the model
            model_obj = genai.GenerativeModel(model_name=model_name, generation_config=generation_config)
            
            # Generate content with Gemini
            prompt_text = "\n".join(structured_prompts)
            response = model_obj.generate_content(prompt_text)
            
            # Extract response text
            response_text = response.text
            
            # Parse JSON response
            try:
                # Sometimes Gemini adds markdown code blocks - handle that
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                
                return json.loads(response_text)
            except json.JSONDecodeError as json_err:
                print(f"Error parsing JSON response: {str(json_err)}")
                print(f"Raw response: {response_text}")
                
                # Try a more aggressive JSON extraction as last resort
                import re
                json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except:
                        pass
                
                last_error = json_err
                
        except Exception as e:
            print(f"Gemini API error (attempt {attempts+1}/{retries}): {str(e)}")
            last_error = e
            
        # Increase delay between retries
        time.sleep(2 * (attempts + 1))
        attempts += 1
    
    # Return error response after all retries fail
    error_msg = str(last_error) if last_error else "Unknown error"
    print(f"Failed to get response from Gemini API after {retries} attempts: {error_msg}")
    
    # Return a structured error response
    return {
        "error": True,
        "error_message": error_msg,
        "fallback_generated": True,
        "data": {}  # Empty data
    }

async def analyze_with_llm(data: Dict[str, Any], analysis_type: str, prompt_template: str) -> Dict[str, Any]:
    """
    Generic function to analyze data with LLM
    
    Args:
        data: Data to analyze
        analysis_type: Type of analysis to perform
        prompt_template: Template for the prompt
        
    Returns:
        Analysis results
    """
    try:
        # Format prompt with data
        prompt = prompt_template.format(**data)
        
        # Get response from Gemini
        response = get_gemini_json_response("gemini-pro", [prompt])
        
        # Add metadata
        response["analysis_type"] = analysis_type
        response["timestamp"] = time.time()
        
        return response
    except Exception as e:
        print(f"Error analyzing with LLM: {str(e)}")
        return {
            "error": True,
            "error_message": str(e),
            "analysis_type": analysis_type,
            "timestamp": time.time(),
            "fallback_generated": True
        } 