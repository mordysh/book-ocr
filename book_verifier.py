import os
import json
import base64
import requests
import argparse
import fitz  # PyMuPDF
import subprocess
import re
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
    # Check for Calibre's cover.jpg in the same directory first
    dir_path = os.path.dirname(file_path)
    calibre_cover = os.path.join(dir_path, "cover.jpg")
    if os.path.exists(calibre_cover):
        log(2, f"Using existing Calibre cover: {calibre_cover}")
        return Image.open(calibre_cover)

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

def encode_image(img):
    img.thumbnail((768, 768))
    buffered = BytesIO()
    img.convert("RGB").save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extract_metadata(file_path, hint=""):
    log(1, f"Processing: {os.path.basename(file_path)}")
    img = get_image_from_file(file_path)
    if not img: return None
    
    img_base64 = encode_image(img)
    hint_text = f"Hint: The expected title/author might be related to '{hint}'." if hint else ""
    
    prompt = f"""
    You are a librarian. Extract the Hebrew book title and the author's name from this cover.
    {hint_text}
    Return ONLY a JSON object: {{"title": "...", "author": "..."}}
    Ensure the Hebrew is correctly ordered (RTL).
    """
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "images": [img_base64],
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=300)
        response.raise_for_status()
        return json.loads(response.json().get("response", "{}"))
    except Exception as e:
        log(1, f"OCR Error for {file_path}: {e}")
        return None

def calculate_accuracy(detected, hint):
    if not hint: return 50
    # Clean hint for better comparison
    clean_hint = re.sub(r'[\(\)\[\]\-_]', ' ', hint)
    score = fuzz.token_set_ratio(f"{detected.get('author', '')} {detected.get('title', '')}", clean_hint)
    return score

def get_calibre_books(db_path, author_regex=None, title_regex=None):
    log(1, f"Querying Calibre library at: {db_path}")
    # Expand user path
    db_path = os.path.expanduser(db_path)
    cmd = ["calibredb", "list", "--with-library", db_path, "--fields", "authors,title,formats", "--for-machine"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(1, f"Calibre error: {result.stderr}")
            return []
        
        books = json.loads(result.stdout)
        log(2, f"Total books found in Calibre: {len(books)}")
        filtered = []
        
        for book in books:
            authors_str = book.get('authors', '')
            if isinstance(authors_str, list):
                authors_str = ", ".join(authors_str)
            
            title_str = book.get('title', '')
            log(2, f"Checking book: {authors_str} - {title_str}")
            
            if author_regex and not re.search(author_regex, authors_str, re.IGNORECASE):
                continue
            if title_regex and not re.search(title_regex, title_str, re.IGNORECASE):
                continue
            
            formats = book.get('formats', [])
            for fmt in formats:
                if fmt.lower().endswith(('.epub', '.pdf')):
                    filtered.append({
                        "path": fmt,
                        "hint": f"{authors_str} - {title_str}"
                    })
                    break
        
        log(1, f"Filtered to {len(filtered)} books matching regex.")
        return filtered
    except Exception as e:
        log(1, f"Error querying Calibre: {e}")
        return []

def rename_and_sidecar(old_path, metadata, accuracy, do_rename=False):
    directory = os.path.dirname(old_path)
    ext = os.path.splitext(old_path)[1]
    
    # Create clean filename
    clean_author = re.sub(r'[\\/*?:"<>|]', "", metadata.get('author', 'Unknown'))
    clean_title = re.sub(r'[\\/*?:"<>|]', "", metadata.get('title', 'Unknown'))
    new_name = f"{clean_author} - {clean_title}{ext}"
    new_path = os.path.join(directory, new_name)
    
    # Sidecar file
    sidecar_path = old_path + ".metadata.json"
    with open(sidecar_path, 'w', encoding='utf-8') as f:
        json.dump({
            "ocr_metadata": metadata,
            "accuracy_score": accuracy,
            "original_filename": os.path.basename(old_path)
        }, f, ensure_ascii=False, indent=4)
    log(2, f"Created sidecar: {os.path.basename(sidecar_path)}")

    if do_rename and accuracy > 85 and not os.path.exists(new_path):
        try:
            os.rename(old_path, new_path)
            log(1, f"Renamed to: {new_name}")
            return new_path
        except Exception as e:
            log(1, f"Rename error: {e}")
    return old_path

def main():
    parser = argparse.ArgumentParser(description="Hebrew Book OCR and Verification Tool")
    parser.add_argument("input", nargs="?", help="Local path to file or directory")
    parser.add_argument("--calibre-db", help="Path to Calibre Library")
    parser.add_argument("--author-regex", help="Filter by author (Regex)")
    parser.add_argument("--title-regex", help="Filter by title (Regex)")
    parser.add_argument("--model", default="llama3.2-vision:11b", help="Ollama model name")
    parser.add_argument("--rename", action="store_true", help="Rename files if confidence > 85%%")
    parser.add_argument("-v1", action="store_true", help="Log level 1")
    parser.add_argument("-v2", action="store_true", help="Log level 2")
    
    args = parser.parse_args()

    global MODEL_NAME
    MODEL_NAME = args.model

    global VERBOSITY
    if args.v2: VERBOSITY = 2
    else: VERBOSITY = 1

    jobs = []

    if args.calibre_db:
        books = get_calibre_books(args.calibre_db, args.author_regex, args.title_regex)
        jobs = books
    elif args.input:
        input_path = os.path.expanduser(args.input)
        if os.path.isdir(input_path):
            for root, _, filenames in os.walk(input_path):
                for f in filenames:
                    if f.lower().endswith(('.epub', '.pdf', '.jpg', '.png')):
                        jobs.append({"path": os.path.join(root, f), "hint": f})
        else:
            jobs.append({"path": input_path, "hint": os.path.basename(input_path)})
    else:
        parser.print_help()
        return

    for job in jobs:
        metadata = extract_metadata(job['path'], hint=job['hint'])
        if metadata:
            score = calculate_accuracy(metadata, job['hint'])
            print(f"[+] Result: {metadata.get('author')} - {metadata.get('title')} (Conf: {score}%)")
            
            # Action: Rename and Sidecar
            rename_and_sidecar(job['path'], metadata, score, do_rename=args.rename)
            
            # Output search links
            for site in SEARCH_SITES:
                q = f"{metadata.get('title')} {metadata.get('author')}"
                print(f"    -> {site['name']}: {site['url'].format(query=q)}")

if __name__ == "__main__":
    main()
