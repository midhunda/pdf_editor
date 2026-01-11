# PDFY - Modern PDF Editor

**PDFY** is a lightweight, privacy-focused PDF manipulation tool built with Python and CustomTkinter. It offers a modern dark-mode UI for viewing, editing, and optimizing PDF files completely offline.

## 🚀 Key Features

*   **⚡ High-Performance Viewing**: Instant loading of large PDFs using lazy-loaded, thread-safe thumbnail generation.
*   **🔒 Privacy-First**: All processing (compression, merging, editing) happens **locally on your device**. No files are uploaded to any server.
*   **🛠️ PDF Manipulation**:
    *   **Merge**: Combine multiple PDFs into one with drag-and-drop reordering.
    *   **Reorder**: Drag thumbnails to rearrange pages.
    *   **Rotate**: Rotate pages 90° clockwise.
    *   **Delete**: Remove single or multiple pages (ranges supported).
    *   **Insert**: Add pages from other PDFs at any position.
*   **📦 Smart Compression**: Reduce file size locally using efficient image re-encoding (Quality vs. Target Size modes).
*   **🎨 Modern UI**: Sleek dark interface with intuitive navigation and keyboard shortcuts.

## 🛠️ Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/pdfy.git

# Install dependencies
pip install -r requirements.txt
```

## 📦 Requirements

*   Python 3.8+
*   `customtkinter`
*   `PyMuPDF` (fitz)
*   `Pillow`
*   `tkinterdnd2`

##  ▶️ Usage

Run the application:
```bash
python pdf_editor.py
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
