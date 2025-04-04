import base64
import requests
from io import BytesIO
from typing import Optional
from PIL import Image

def encode_image_to_base64(image_url: str, max_dimension: int = 1024) -> Optional[str]:
    """
    Download and encode image to base64 for AI API
    
    Args:
        image_url: URL of the image to download
        max_dimension: Maximum dimension for resizing the image
        
    Returns:
        Base64-encoded image, or None if download fails
    """
    if not image_url:
        return None
        
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            response = requests.get(image_url, timeout=15)
            response.raise_for_status()
            
            # Check if content is actually an image
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                print(f"Warning: URL {image_url} returned non-image content type: {content_type}")
                # Continue anyway, as Instagram sometimes has incorrect Content-Type headers
            
            # Verify it's an actual image by trying to open it
            try:
                img = Image.open(BytesIO(response.content))
                img.verify()  # Verify it's an image
                
                # If image is too large, resize it to reduce payload size
                img = Image.open(BytesIO(response.content))  # Need to reopen after verify
                
                if img.width > max_dimension or img.height > max_dimension:
                    # Calculate new dimensions while preserving aspect ratio
                    if img.width > img.height:
                        new_width = max_dimension
                        new_height = int(img.height * (max_dimension / img.width))
                    else:
                        new_height = max_dimension
                        new_width = int(img.width * (max_dimension / img.height))
                    
                    # Resize image
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Save to a new BytesIO object
                    img_bytes = BytesIO()
                    img.save(img_bytes, format=img.format or 'JPEG')
                    img_bytes.seek(0)
                    
                    # Return base64 of resized image
                    return base64.b64encode(img_bytes.read()).decode('utf-8')
                
                # If no resize needed, return original image
                return base64.b64encode(response.content).decode('utf-8')
                
            except Exception as img_error:
                print(f"Error verifying image from {image_url}: {str(img_error)}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image from {image_url} (attempt {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
                # Increase delay for next retry
                retry_delay *= 2
            else:
                return None
    
    return None

def get_image_dimensions(image_url: str) -> Optional[tuple]:
    """
    Get the dimensions of an image from its URL
    
    Args:
        image_url: URL of the image
        
    Returns:
        Tuple of (width, height), or None if download fails
    """
    if not image_url:
        return None
        
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        return img.size
    except Exception as e:
        print(f"Error getting image dimensions: {str(e)}")
        return None 