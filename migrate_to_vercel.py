import re
import os

with open('backend/app/ocr.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Remove pytesseract import and configure_tesseract
code = re.sub(r'import pytesseract\n', 'import requests\nimport base64\n', code)

code = re.sub(r'def configure_tesseract.*?return ""', '', code, flags=re.DOTALL)
code = re.sub(r'TESSERACT_CMD = configure_tesseract\(\)\n', '', code)
code = re.sub(r'if TESSERACT_CMD:.*?tesseract_cmd = TESSERACT_CMD\n', '', code, flags=re.DOTALL)

# 2. Add OpenAI API integration
openai_func = '''
def call_cloud_ocr(image_bytes: bytes) -> str:
    """
    Calls a Cloud API (OpenAI GPT-4o-mini) to perform robust OCR.
    This replaces local Tesseract, making it compatible with Vercel Serverless.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "[OCR FAILED: OPENAI_API_KEY environment variable is not set. Please configure it in your Vercel or local environment.]"
    
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "You are a specialized OCR engine. Extract all text from the provided document accurately. Preserve numbers, dates, and names exactly. Output ONLY the extracted text, with no markdown, conversational filler, or introductory phrases."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 1500
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[OCR FAILED: Cloud API Error: {str(e)}]"
'''

# 3. Replace ocr_pixmap
new_ocr_pixmap = '''def ocr_pixmap(pix: pymupdf.Pixmap, psm: int = 3) -> str:
    """
    Converts a PyMuPDF Pixmap to JPEG bytes and sends to Cloud API.
    """
    img_bytes = pix.tobytes("jpeg")
    return call_cloud_ocr(img_bytes)'''

code = re.sub(r'def ocr_pixmap\(pix: pymupdf\.Pixmap, psm: int = 3\) -> str:.*?except Exception as e:.*?return ""', new_ocr_pixmap, code, flags=re.DOTALL)

# 4. Replace ocr_image
new_ocr_image = '''def ocr_image(img: Image.Image, psm: int = 3) -> str:
    """
    Converts a Pillow Image to JPEG bytes and sends to Cloud API.
    """
    import io
    buffered = io.BytesIO()
    # Convert to RGB if it has alpha channel to save as JPEG safely
    if img.mode in ("RGBA", "P"): 
        img = img.convert("RGB")
    img.save(buffered, format="JPEG", quality=85)
    return call_cloud_ocr(buffered.getvalue())'''

code = re.sub(r'def ocr_image\(img: Image\.Image, psm: int = 3\) -> str:.*?except Exception as e:.*?return ""', new_ocr_image, code, flags=re.DOTALL)

# Inject the openai function just before process_document_pipeline
code = re.sub(r'def process_document_pipeline\(', openai_func + '\ndef process_document_pipeline(', code)

# Change 'TESSERACT' to 'CLOUD_API'
code = re.sub(r'"ocrEngine": "TESSERACT"', '"ocrEngine": "CLOUD_API"', code)
code = re.sub(r'ocrEngine="TESSERACT"', 'ocrEngine="CLOUD_API"', code)

# Update requirements.txt
with open('backend/requirements.txt', 'r', encoding='utf-8') as f:
    reqs = f.read()
reqs = reqs.replace('pytesseract>=0.3.13', 'requests>=2.31.0')
with open('backend/requirements.txt', 'w', encoding='utf-8') as f:
    f.write(reqs)

with open('backend/app/ocr.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Migration to Cloud OCR complete!")
