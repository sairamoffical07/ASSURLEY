import pytest
from app.ocr import process_document_pipeline
import pymupdf
import tempfile
import pathlib

class MockPage:
    def __init__(self, text):
        self.text = text
        self.rect = pymupdf.Rect(0, 0, 100, 100)
    
    def get_text(self, mode):
        return self.text
        
    def get_pixmap(self, matrix, alpha):
        class MockPixmap:
            width = 100
            height = 100
            samples = b"x" * 10000
        return MockPixmap()

class MockDoc:
    def __init__(self, pages):
        self._pages = pages
        self.page_count = len(pages)
        
    def __getitem__(self, i):
        return self._pages[i]
        
    def __len__(self):
        return self.page_count
        
    def close(self):
        pass

def test_pdf_quality_heuristic_good_text(monkeypatch):
    # Good embedded text
    good_text = "This is a legitimate repair invoice with total amount Rs. 15000 and vehicle number AB12CD3456." * 3
    
    def mock_open(*args, **kwargs):
        return MockDoc([MockPage(good_text)])
        
    monkeypatch.setattr(pymupdf, "open", mock_open)
    
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        res = process_document_pipeline(f.name, "application/pdf")
        
    print(res)
    assert res["textSource"] == "embedded"
    assert res["pageCount"] == 1
    assert "Rs. 15000" in res["extractedText"]

def test_pdf_quality_heuristic_cid_garbage(monkeypatch):
    # Garbage CID text
    cid_text = "(cid:10) (cid:11) (cid:12) (cid:13) " * 20
    
    def mock_open(*args, **kwargs):
        return MockDoc([MockPage(cid_text)])
        
    monkeypatch.setattr(pymupdf, "open", mock_open)
    
    # We must also mock pytesseract so it doesn't crash on the mock pixmap
    import pytesseract
    monkeypatch.setattr(pytesseract, "image_to_string", lambda image, config: "OCR Fallback Text")
    
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        res = process_document_pipeline(f.name, "application/pdf")
        
    # It should have rejected the CID text and fallen back to OCR
    assert res["textSource"] == "ocr"
    assert "(cid:10)" not in res["extractedText"]

def test_pdf_quality_heuristic_unprintable_garbage(monkeypatch):
    # Garbage text with replacement characters
    bad_text = "XqZ Wrt " * 10 + "\ufffd\ufffd\ufffd" * 10
    
    def mock_open(*args, **kwargs):
        return MockDoc([MockPage(bad_text)])
        
    monkeypatch.setattr(pymupdf, "open", mock_open)
    
    import pytesseract
    monkeypatch.setattr(pytesseract, "image_to_string", lambda image, config: "OCR Fallback Text")
    
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        res = process_document_pipeline(f.name, "application/pdf")
        
    assert res["textSource"] == "ocr"

