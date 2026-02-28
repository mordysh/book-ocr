
import os
import json
import base64
import requests
import argparse
import fitz  # PyMuPDF
import subprocess
from PIL import Image
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
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ('.jpg', '.jpeg', '.png'):
        return Image.open(file_path)
    elif ext in ('.pdf', '.epub'):
        try:
            doc = fitz.open(file_path)
            page = doc.load_page(0)
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            doc.close()
            return Image.open(BytesIO(img_data))
        except Exception as e:
            log(1, f"Error extracting cover from {file_path}: {e}")
    return None

def extract_calibre_cover(book_id):
    """
    Extracts a cover for a book ID from Calibre.
    """
    log(2, f"Attempting to extract cover for Calibre ID: {book_id}")
    try:
        tmp_cover = f"/tmp/calibre_cover_{book_id}.jpg"
        subprocess.run(["calibredb", "export", str(book_id), "--as-single-dir", "--to", "/tmp", "--template", f"calibre_cover_{book_id}"], capture_output=True)
        # Calibre export creates a folder. Let's find the image inside.
        # Simpler: use 'show_metadata' to get the path
        result = subprocess.run(["calibredb", "show_metadata", str(book_id)], capture_output=True, text=True)
        # This is complex to parse. Let's assume the user points us to the Calibre Library folder instead.
        # But for now, we'll stick to file-based hints.
    except Exception as e:
        log(1, f"Calibre extraction error: {e}")
    return None

def encode_image(img):
    img.thumbnail((1024, 1024))
    buffered = BytesIO()
    img.convert("RGB").save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extract_metadata(file_path, hint=""):
    log(1, f"Processing: {os.path.basename(file_path)}")
    img = get_image_from_file(file_path)
    if not img: return None
    
    img_base64 = encode_image(img)
    
    # Use filename as a hint to the VLM
    hint_text = f"Hint: The filename is '{hint}'. Use this to confirm what you see on the cover." if hint else ""
    
    prompt = f"""
    Extract the Hebrew book title and the author's name from this cover.
    {hint_text}
    Return ONLY a JSON object: {{"title": "...", "author": "..."}}
    If you are unsure, provide your best guess.
    """
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "images": [img_base64],
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        return json.loads(response.json().get("response", "{}"))
    except Exception as e:
        log(1, f"OCR Error: {e}")
        return None

def calculate_accuracy(detected, hint):
    """
    Simple fuzzy match between OCR result and filename hint.
    """
    if not hint: return 50 # Default middle ground if no hint
    score = fuzz.token_set_ratio(f"{detected['author']} {detected['title']}", hint)
    return score

def rename_and_log(old_path, metadata, accuracy):
    directory = os.path.dirname(old_path)
    ext = os.path.splitext(old_path)[1]
    new_name = f"{metadata['author']} - {metadata['title']}{ext}".replace("/", "-")
    new_path = os.path.join(directory, new_name)
    
    log(1, f"Accuracy Score: {accuracy}%")
    
    # Create sidecar metadata file
    meta_path = old_path + ".metadata.json"
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump({"metadata": metadata, "accuracy": accuracy, "original_name": os.path.basename(old_path)}, f, ensure_ascii=False, indent=4)
    
    if accuracy > 80: # Only rename if we are fairly sure
        log(1, f"Renaming to: {new_name}")
        try:
            os.rename(old_path, new_path)
            return new_path
        except Exception as e:
            log(1, f"Rename failed: {e}")
    else:
        log(1, "Accuracy too low for auto-rename.")
    return old_path

def main():
    parser = argparse.ArgumentParser(description="Hebrew Book OCR and Verification Tool")
    parser.add_argument("input", help="Path to a file or directory")
    parser.add_argument("--rename", action="store_true", help="Automatically rename files if OCR is confident")
    parser.add_argument("-v1", action="store_true", help="Level 1 Verbosity")
    parser.add_argument("-v2", action="store_true", help="Level 2 Verbosity")
    parser.add_argument("-v3", action="store_true", help="Level 3 Verbosity")
    
    args = parser.parse_args()

    global VERBOSITY
    if args.v3: VERBOSITY = 3
    elif args.v2: VERBOSITY = 2
    else: VERBOSITY = 1

    input_path = os.path.expanduser(args.input)
    supported_exts = ('.png', '.jpg', '.jpeg', '.pdf', '.epub')
    
    files = []
    if os.path.isdir(input_path):
        for root, _, filenames in os.walk(input_path):
            for f in filenames:
                if f.lower().endswith(supported_exts):
                    files.append(os.path.join(root, f))
    else:
        files = [input_path]

    for path in files:
        filename_hint = os.path.splitext(os.path.basename(path))[0]
        metadata = extract_metadata(path, hint=filename_hint)
        
        if metadata:
            accuracy = calculate_accuracy(metadata, filename_hint)
            print(f"[+] Result: {metadata['author']} - {metadata['title']} (Conf: {accuracy}%)")
            
            if args.rename:
                path = rename_and_log(path, metadata, accuracy)
            
            # Show verification links
            for site in SEARCH_SITES:
                query = f"{metadata['title']} {metadata['author']}"
                print(f"    -> {site['name']}: {site['url'].format(query=query)}")

if __name__ == "__main__":
    main()
