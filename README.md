# Hebrew Book OCR & Verification Tool

A local Python utility designed to extract Hebrew book titles and authors from cover images, PDFs, and EPUB files using Vision-Language Models (VLM). It then generates verification links and sidecar metadata for Calibre libraries or local directories.

## Features
- **Local OCR:** Uses Llama 3.2 Vision (11B) via [Ollama](https://ollama.com/) for high-quality Hebrew text extraction.
- **Multi-format Support:** Handles `.jpg`, `.png`, `.pdf`, and `.epub` (automatically extracts the first page/cover).
- **Calibre Integration:** Directly query a Calibre library via `calibredb` to verify and rename existing books.
- **Smart Renaming:** Conditionally rename files based on OCR confidence (using fuzzy string matching with a default 85% safety threshold).
- **Sidecar Metadata:** Generates `.metadata.json` sidecar files containing OCR results and accuracy scores.
- **Online Verification:** Generates search links for **e-vrit**, **Steimatzky**, and **Simania**.
- **Configurable Verbosity:** Control log output with `-v1` or `-v2`.

## Prerequisites
1. **Ollama:** [Download and install Ollama](https://ollama.com/).
2. **Model:** Pull the vision model:
   ```bash
   ollama pull llama3.2-vision:11b
   ```
3. **Calibre CLI (Optional):** If using `--calibre-db`, ensure `calibredb` is in your system PATH.

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/mordysh/book-ocr.git
   cd book-ocr
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage
Run the script on a local directory, file, or a Calibre library.

### Local Files
```bash
# Process a single file
python3 book_verifier.py path/to/book.epub

# Process a directory with verbose output
python3 book_verifier.py -v2 "~/Downloads/MyBooks/"
```

### Calibre Library
```bash
# Verify books in a Calibre library matching a title regex
python3 book_verifier.py --calibre-db "~/Desktop/books/ebooks_temp2/" --title-regex "חוכמת"

# Perform conditional renaming for high-confidence matches (>85%)
python3 book_verifier.py --calibre-db "~/Desktop/books/ebooks_temp2/" --rename
```

## How it Works
1. **Extraction:** If the input is a PDF or EPUB, `PyMuPDF` (fitz) extracts the first page. If a Calibre `cover.jpg` exists in the folder, it is preferred.
2. **OCR:** The image is sent to the local Ollama instance with a prompt optimized for Hebrew metadata extraction.
3. **Accuracy & Sidecars:** The tool compares OCR results against the filename (or Calibre metadata) using fuzzy matching. A `.metadata.json` sidecar is created for every processed file.
4. **Renaming:** If the `--rename` flag is present and the accuracy exceeds 85%, the file is renamed to a clean `Author - Title.ext` format.
5. **Link Generation:** Generates direct search queries for Hebrew retailers to facilitate manual verification.
