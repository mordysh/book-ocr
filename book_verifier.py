
import os
import json
import base64
import requests
import argparse
import fitz  # PyMuPDF
from PIL import Image
from bs4 import BeautifulSoup
from thefuzz import fuzz
from io import BytesIO

# --- CONFIGURATION ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2-vision:11b"

SEARCH_SITES = [
    {"name": "e-vrit", "url": "https://www.e-vrit.co.il/Search/{query}"},
    {"name": "steimatzky", "url": "https://www.steimatzky.co.il/catalogsearch/result/?q={query}"},
    {"name": "simania", "url": "https://simania.co.il/searchBooks.php?searchString={query}"}
]

# Global verbosity level
VERBOSITY = 0

def log(level, message):
    if VERBOSITY >= level:
        prefix = "[*]" if level == 1 else "[**]" if level == 2 else "[***]"
        print(f"{prefix} {message}")

def get_image_from_file(file_path):
    """
    Returns a PIL Image from an image file, or the first page of a PDF/EPUB.
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in ('.jpg', '.jpeg', '.png'):
        log(2, f"Opening image: {file_path}")
        return Image.open(file_path)
    
    elif ext in ('.pdf', '.epub'):
        log(2, f"Extracting first page/cover from {ext.upper()}: {file_path}")
        try:
            doc = fitz.open(file_path)
            # Try to get the first page as a pixmap
            page = doc.load_page(0)
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            doc.close()
            return Image.open(BytesIO(img_data))
        except Exception as e:
            log(1, f"Error extracting cover from {file_path}: {e}")
            return None
    return None

def encode_image(img):
    """
    Takes a PIL Image and returns base64 string.
    """
    original_size = img.size
    img.thumbnail((1024, 1024))
    log(3, f"Resized from {original_size} to {img.size}")
    buffered = BytesIO()
    img.convert("RGB").save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extract_metadata(image_path):
    log(1, f"Processing: {os.path.basename(image_path)}")
    img = get_image_from_file(image_path)
    if not img:
        return "{}"
    
    img_base64 = encode_image(img)
    
    prompt = """
    Extract the Hebrew book title and the author's name from this cover.
    Return ONLY a JSON object in this format:
    {"title": "Hebrew Title", "author": "Hebrew Author"}
    If you cannot find the author, leave it blank. Return nothing but the JSON.
    """
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "images": [img_base64],
        "stream": False,
        "format": "json"
    }
    
    log(2, f"Sending request to Ollama ({MODEL_NAME})...")
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        raw_json = result.get("response", "{}")
        log(3, f"Raw VLM Response: {raw_json}")
        return raw_json
    except Exception as e:
        print(f"[!] Error calling Ollama: {e}")
        return "{}"

def verify_book(title, author):
    log(1, f"Searching for: '{title}' by '{author}'")
    results = []
    for site in SEARCH_SITES:
        query = f"{title} {author}".strip()
        search_url = site["url"].format(query=query)
        log(2, f"Targeting {site['name']}: {search_url}")
        results.append({"site": site["name"], "url": search_url})
    return results

def main():
    parser = argparse.ArgumentParser(description="Hebrew Book OCR and Verification Tool")
    parser.add_argument("input", nargs="?", default="./test_images", help="Path to a file or directory")
    parser.add_argument("-v1", action="store_true", help="Level 1 Verbosity: Basic progress updates")
    parser.add_argument("-v2", action="store_true", help="Level 2 Verbosity: Detailed step-by-step info")
    parser.add_argument("-v3", action="store_true", help="Level 3 Verbosity: Debugging, raw data, and internal states")
    
    args = parser.parse_args()

    global VERBOSITY
    if args.v3: VERBOSITY = 3
    elif args.v2: VERBOSITY = 2
    elif args.v1: VERBOSITY = 1
    else: VERBOSITY = 1

    input_path = os.path.expanduser(args.input)
    
    supported_exts = ('.png', '.jpg', '.jpeg', '.pdf', '.epub')
    
    if os.path.isdir(input_path):
        files = []
        for root, dirs, filenames in os.walk(input_path):
            for f in filenames:
                if f.lower().endswith(supported_exts):
                    files.append(os.path.join(root, f))
        log(1, f"Found {len(files)} supported files in {input_path}")
    elif os.path.isfile(input_path):
        files = [input_path]
    else:
        print(f"[!] Path not found: {input_path}")
        return

    for path in files:
        metadata_str = extract_metadata(path)
        try:
            metadata = json.loads(metadata_str)
            title = metadata.get('title', 'Unknown')
            author = metadata.get('author', 'Unknown')
            
            if title == 'Unknown' and author == 'Unknown':
                log(1, f"[-] SKIP: Could not extract metadata from {os.path.basename(path)}")
                continue

            print(f"[+] SUCCESS: Found '{title}' by '{author}'")
            
            links = verify_book(title, author)
            for link in links:
                print(f"    -> {link['site']}: {link['url']}")
        except Exception as e:
            log(1, f"Failed to parse metadata for {path}: {e}")
            log(3, f"Problematic string: {metadata_str}")

if __name__ == "__main__":
    main()
