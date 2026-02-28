
# Hebrew Book OCR & Verification Tool

A local Python utility designed to extract Hebrew book titles and authors from cover images, PDFs, and EPUB files using Vision-Language Models (VLM). It then generates verification links to popular Hebrew book retailers and databases.

## Features
- **Local OCR:** Uses Llama 3.2 Vision (11B) via [Ollama](https://ollama.com/) for high-quality Hebrew text extraction.
- **Multi-format Support:** Handles `.jpg`, `.png`, `.pdf`, and `.epub` (automatically extracts the first page/cover).
- **Online Verification:** Generates search links for **e-vrit**, **Steimatzky**, and **Simania**.
- **Verbosity Levels:** Control log output with `-v1`, `-v2`, or `-v3`.

## Prerequisites
1. **Ollama:** [Download and install Ollama](https://ollama.com/).
2. **Model:** Pull the vision model:
   ```bash
   ollama pull llama3.2-vision:11b
   ```

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
Run the script on a file or a directory:
```bash
# Basic usage
python3 book_verifier.py path/to/my_books/

# With high verbosity (shows more steps)
python3 book_verifier.py -v2 "~/Downloads/Telegram Desktop/"
```

## How it Works
1. **Extraction:** If the input is a PDF or EPUB, `PyMuPDF` (fitz) extracts the first page as an image.
2. **OCR:** The image is sent to the local Ollama instance for Hebrew metadata extraction.
3. **Link Generation:** The extracted title and author are used to build search queries for verified Hebrew book sites.
