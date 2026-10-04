from __future__ import annotations

import io
import math
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pymupdf  # PyMuPDF
import requests
import base64

# Configure Pillow decompression bomb protection
Image.MAX_IMAGE_PIXELS = 60_000_000

# Constants for document processing limits
MAX_PDF_PAGES = 15
MAX_IMAGE_DIM = 3500
MIN_TEXT_DIM = 900
TARGET_PDF_DPI_ZOOM = 2.77  # ~200 DPI from 72 DPI base


def configure_tesseract() -> str:
    """
    Locates and sets the Tesseract executable in order of priority:
    1. PATH
    2. TESSERACT_CMD environment variable
    3. Standard Windows installation paths
    """
    # 1. Check existing PATH
    which_cmd = shutil.which("tesseract")
    if which_cmd:
        pytesseract.pytesseract.tesseract_cmd = which_cmd
        return which_cmd

    # 2. Check TESSERACT_CMD environment variable
    env_cmd = os.getenv("TESSERACT_CMD")
    if env_cmd and os.path.isfile(env_cmd):
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return env_cmd

    # 3. Check standard Windows locations
    standard_windows_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for p in standard_windows_paths:
        if os.path.isfile(p):
            pytesseract.pytesseract.tesseract_cmd = p
            return p

    return "tesseract"


# Initialize tesseract on import
configure_tesseract()


# ---------------------------------------------------------------------------
# MIME & Content Validation
# ---------------------------------------------------------------------------

SUPPORTED_MIMES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
    "image/tiff": [".tif", ".tiff"],
    "application/pdf": [".pdf"],
}


def validate_file_content(content: bytes, original_filename: str = "") -> tuple[str, str, list[str]]:
    """
    Validates file content by inspecting magic headers and attempting to parse it.
    Rejects unsupported or corrupt files with ValueError.
    Returns: (canonical_mime, detected_format, warnings)
    """
    if not content or len(content) == 0:
        raise ValueError("The uploaded file is empty.")

    warnings: list[str] = []

    # Check for PDF
    if content.startswith(b"%PDF"):
        try:
            doc = pymupdf.open(stream=content, filetype="pdf")
            if doc.is_encrypted:
                raise ValueError("Password-protected or encrypted PDFs are not supported.")
            if len(doc) == 0:
                raise ValueError("The uploaded PDF has no pages.")
            doc.close()
            return ("application/pdf", "PDF", warnings)
        except Exception as e:
            if "encrypted" in str(e).lower() or "password" in str(e).lower():
                raise ValueError("Password-protected or encrypted PDFs are not supported.")
            raise ValueError(f"Corrupt or invalid PDF file: {e}")

    # Check for Image formats
    try:
        buf = io.BytesIO(content)
        with Image.open(buf) as img:
            fmt = (img.format or "").upper()
            if fmt in ("JPEG", "JPG"):
                canonical_mime = "image/jpeg"
            elif fmt == "PNG":
                canonical_mime = "image/png"
            elif fmt == "WEBP":
                canonical_mime = "image/webp"
            elif fmt == "TIFF":
                canonical_mime = "image/tiff"
            else:
                raise ValueError(
                    f"Unsupported image format: '{fmt}'. Only JPEG, PNG, WEBP, TIFF, and PDF files are supported."
                )

            # Verify integrity
            img.verify()

        # Re-open to confirm full raster readability
        buf.seek(0)
        with Image.open(buf) as img:
            img.load()
            w, h = img.size
            if w <= 0 or h <= 0:
                raise ValueError("Invalid image dimensions.")

        return (canonical_mime, fmt, warnings)

    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise ValueError("Image dimensions exceed safety limits (potential decompression bomb).")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"The uploaded file is corrupt or unreadable: {e}")


# ---------------------------------------------------------------------------
# Image Normalization
# ---------------------------------------------------------------------------

def normalize_pil_image(img: Image.Image) -> tuple[Image.Image, list[str]]:
    """
    Normalizes a PIL image:
    1. Corrects EXIF orientation.
    2. Converts transparent images onto a solid white background.
    3. Converts to RGB.
    4. Upscales if resolution is too low for text legibility.
    5. Constrains extreme dimensions to avoid unbounded memory usage.
    """
    warnings: list[str] = []

    # 1. EXIF orientation correction
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # 2. Transparency handling -> composite onto white background
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        try:
            rgba = img.convert("RGBA")
            white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            composite = Image.alpha_composite(white_bg, rgba)
            img = composite.convert("RGB")
        except Exception:
            img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size

    # 3. Upscale if text resolution is too low
    min_dim = min(w, h)
    max_dim = max(w, h)
    if min_dim < MIN_TEXT_DIM and max_dim < 1800:
        scale = min(2.5, MIN_TEXT_DIM / max(1, min_dim))
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        warnings.append(f"Image upscaled from {w}x{h} to {new_w}x{new_h} for OCR text legibility.")
        w, h = new_w, new_h

    # 4. Constrain extreme dimensions
    if max_dim > MAX_IMAGE_DIM:
        scale = MAX_IMAGE_DIM / max_dim
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        warnings.append(f"Image constrained from {w}x{h} to {new_w}x{new_h} to optimize memory.")

    return (img, warnings)


# ---------------------------------------------------------------------------
# Deskew & Preprocessing Variants (OpenCV)
# ---------------------------------------------------------------------------

def deskew_image(gray: np.ndarray) -> tuple[np.ndarray, Optional[float], list[str]]:
    """
    Detects document skew angle and rotates the image upright if a meaningful
    skew (0.75° to 45°) is detected. Returns (deskewed_gray, angle, warnings).
    """
    warnings: list[str] = []
    try:
        # Otsu threshold foreground text
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

        # Ignore tiny isolated dots/noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 3))
        dilated = cv2.dilate(thresh, kernel, iterations=1)

        coords = np.column_stack(np.where(dilated > 0))
        if len(coords) < 100:
            return gray, None, warnings

        # Calculate bounding rect angle
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]

        # In OpenCV, minAreaRect angle is in [-90, 0)
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # Only deskew if meaningful
        if 0.75 <= abs(angle) <= 45.0:
            (h, w) = gray.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                gray,
                M,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=255,
            )
            warnings.append(f"Document deskewed by {angle:+.1f}°.")
            return rotated, angle, warnings

        return gray, None, warnings
    except Exception as e:
        warnings.append(f"Deskew skipped: {e}")
        return gray, None, warnings


def generate_preprocessing_variants(pil_rgb: Image.Image) -> tuple[list[tuple[str, np.ndarray]], list[str]]:
    """
    Generates multiple targeted image preprocessing variants for Tesseract:
    - Variant A: Grayscale + CLAHE / Autocontrast
    - Variant B: Grayscale + Denoise + Adaptive Gaussian Threshold
    - Variant C: Grayscale + Unsharp Mask (Sharpen)
    """
    warnings: list[str] = []

    # Convert PIL RGB to OpenCV BGR then Grayscale
    open_cv_image = np.array(pil_rgb)
    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2GRAY)

    # Deskew base grayscale image
    gray_deskewed, _, deskew_warnings = deskew_image(gray)
    warnings.extend(deskew_warnings)

    variants: list[tuple[str, np.ndarray]] = []

    # Variant A: Grayscale + CLAHE (Autocontrast)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    var_a = clahe.apply(gray_deskewed)
    variants.append(("variant_a_autocontrast", var_a))

    # Variant B: Grayscale + Bilateral Filter Denoise + Adaptive Threshold
    denoised = cv2.bilateralFilter(gray_deskewed, d=7, sigmaColor=50, sigmaSpace=50)
    var_b = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        21,
        11,
    )
    variants.append(("variant_b_adaptive_thresh", var_b))

    # Variant C: Grayscale + Unsharp Mask (Sharpening)
    gaussian = cv2.GaussianBlur(gray_deskewed, (0, 0), 2.0)
    var_c = cv2.addWeighted(gray_deskewed, 1.5, gaussian, -0.5, 0)
    variants.append(("variant_c_sharpen", var_c))

    return variants, warnings


# ---------------------------------------------------------------------------
# Tesseract Execution & Candidate Scoring
# ---------------------------------------------------------------------------

class OCRPageResult:
    def __init__(
        self,
        text: str,
        confidence: float,
        tokens_count: int,
        word_count: int,
        variant_name: str,
        psm_mode: int,
    ):
        self.text = text
        self.confidence = confidence
        self.tokens_count = tokens_count
        self.word_count = word_count
        self.variant_name = variant_name
        self.psm_mode = psm_mode


def _run_tesseract_on_variant(
    img_array: np.ndarray,
    variant_name: str,
    psm: int,
) -> Optional[OCRPageResult]:
    """
    Runs pytesseract.image_to_data on an image array with specified PSM mode.
    Computes valid tokens, confidence, and returns an OCRPageResult.
    """
    config = f"--psm {psm} --oem 3"
    try:
        data = pytesseract.image_to_data(
            img_array,
            output_type=pytesseract.Output.DICT,
            config=config,
        )
    except Exception:
        return None

    raw_texts = data.get("text", [])
    raw_confs = data.get("conf", [])

    valid_words: list[str] = []
    valid_confs: list[float] = []

    for word, conf in zip(raw_texts, raw_confs):
        w = (word or "").strip()
        try:
            cf = float(conf)
        except Exception:
            cf = -1.0

        if w and cf >= 0:
            valid_words.append(w)
            valid_confs.append(cf)

    if not valid_words:
        return None

    avg_conf = (sum(valid_confs) / len(valid_confs)) / 100.0
    text_content = " ".join(valid_words)

    return OCRPageResult(
        text=text_content,
        confidence=round(max(0.0, min(1.0, avg_conf)), 4),
        tokens_count=len(valid_confs),
        word_count=len(valid_words),
        variant_name=variant_name,
        psm_mode=psm,
    )


def _score_candidate(res: OCRPageResult) -> float:
    """
    Heuristic to score OCR candidates balancing confidence and text density:
    - Prefer results with realistic word counts and higher alphanumeric ratio
    - Penalize garbage / noise results
    """
    if not res.text or res.word_count < 2:
        return 0.0

    chars = [c for c in res.text if not c.isspace()]
    if not chars:
        return 0.0

    alphanum = sum(1 for c in chars if c.isalnum())
    alpha_ratio = alphanum / len(chars)
    if alpha_ratio < 0.35:
        # Heavily noise-corrupted
        return res.confidence * 0.2

    # Scale factor for word density (plateaus around 25 words)
    density_factor = min(1.0, res.word_count / 25.0)

    return res.confidence * 0.6 + (density_factor * 0.3) + (alpha_ratio * 0.1)


def ocr_single_pil_image(pil_img: Image.Image) -> tuple[OCRPageResult, list[str]]:
    """
    Preprocesses a normalized PIL image through variants and PSMs,
    evaluates candidates, and picks the highest-scoring OCR result.
    """
    variants, warnings = generate_preprocessing_variants(pil_img)
    candidates: list[OCRPageResult] = []

    # Priority PSMs for financial/invoice documents:
    # --psm 6: Assume a single uniform block of text (ideal for structured invoices)
    # --psm 11: Sparse text. Find as much text as possible in no particular order.
    # --psm 12: Sparse text with OSD.
    psm_modes = [6, 11, 12]

    # Evaluate Variant A with PSM 6 first
    first_res = _run_tesseract_on_variant(variants[0][1], variants[0][0], 6)
    if first_res:
        candidates.append(first_res)

    # Evaluate Variant B with PSM 6 (adaptive threshold)
    second_res = _run_tesseract_on_variant(variants[1][1], variants[1][0], 6)
    if second_res:
        candidates.append(second_res)

    # If confidence is moderate or low, evaluate other PSMs and Variant C
    best_current = max(candidates, key=_score_candidate) if candidates else None
    if not best_current or best_current.confidence < 0.82 or best_current.word_count < 10:
        for vname, var_arr in variants:
            for psm in (11, 12):
                res = _run_tesseract_on_variant(var_arr, vname, psm)
                if res:
                    candidates.append(res)

        # Also test Variant C with PSM 6
        res_c = _run_tesseract_on_variant(variants[2][1], variants[2][0], 6)
        if res_c:
            candidates.append(res_c)

    if not candidates:
        return (
            OCRPageResult(
                text="",
                confidence=0.0,
                tokens_count=0,
                word_count=0,
                variant_name="none",
                psm_mode=6,
            ),
            warnings,
        )

    best_candidate = max(candidates, key=_score_candidate)
    return best_candidate, warnings


# ---------------------------------------------------------------------------
# Multi-Page Document Pipeline (PDF & TIFF & Single Images)
# ---------------------------------------------------------------------------

def determine_ocr_status(confidence: float, text: str) -> str:
    """
    Workflow heuristics:
    - >= 75% -> PROCESSED
    - 50-74% -> LOW_CONFIDENCE
    - < 50% but meaningful text -> REVIEW_REQUIRED
    - No text / unreadable -> FAILED
    """
    cleaned_words = [w for w in text.split() if any(c.isalnum() for c in w)]
    if not cleaned_words or len(cleaned_words) < 2:
        return "FAILED"

    if confidence >= 0.75:
        return "PROCESSED"
    elif confidence >= 0.50:
        return "LOW_CONFIDENCE"
    else:
        return "REVIEW_REQUIRED"



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

def process_document_pipeline(file_path: str, mime: str) -> dict[str, Any]:
    """
    Unified, robust OCR pipeline for images and PDFs:
    - Handles PDF (multi-page up to MAX_PDF_PAGES) via PyMuPDF rasterization
    - Handles multi-page TIFF
    - Handles single images (PNG, JPEG, WEBP)
    - Normalizes, deskews, evaluates multi-variant & multi-PSM Tesseract
    - Assembles ordered multi-page text with '--- Page X ---' markers
    - Calculates aggregate confidence and determines explicit OCR status
    - Never throws; catches exceptions and returns error dict
    """
    warnings: list[str] = []
    p = Path(file_path)

    if not p.exists() or not p.is_file():
        return {
            "extractedText": "",
            "ocrConfidence": 0.0,
            "ocrStatus": "FAILED",
            "pageCount": 0,
            "ocrEngine": "CLOUD_API",
            "ocrConfig": {},
            "processingWarnings": ["Document file not found on server."],
            "pages": [],
            "error": "Document file not found on server.",
            "textSource": "none",
        }

    try:
        # ==========================
        # Case 1: PDF Document
        # ==========================
        if mime == "application/pdf" or p.suffix.lower() == ".pdf":
            doc = pymupdf.open(file_path)
            total_pages = len(doc)
            if total_pages == 0:
                doc.close()
                return {
                    "extractedText": "",
                    "ocrConfidence": 0.0,
                    "ocrStatus": "FAILED",
                    "pageCount": 0,
                    "ocrEngine": "CLOUD_API",
                    "ocrConfig": {},
                    "processingWarnings": ["PDF contains no pages."],
                    "pages": [],
                    "error": "PDF contains no pages.",
                    "textSource": "ocr",
                }

            process_pages = min(total_pages, MAX_PDF_PAGES)
            if total_pages > MAX_PDF_PAGES:
                warnings.append(
                    f"PDF has {total_pages} pages; processing limited to first {MAX_PDF_PAGES} pages."
                )

            embedded_texts = []
            total_embedded_words = 0
            total_embedded_alnum = 0
            total_embedded_chars = 0

            for page_idx in range(process_pages):
                page = doc[page_idx]
                text = page.get_text("text")
                embedded_texts.append(text)
                words = [w for w in text.split() if any(c.isalnum() for c in w)]
                total_embedded_words += len(words)
                chars = [c for c in text if not c.isspace()]
                total_embedded_chars += len(chars)
                total_embedded_alnum += sum(1 for c in chars if c.isalnum())

            full_text = " ".join(embedded_texts)
            chars = [c for c in full_text if not c.isspace()]
            valid_embedded = False
            if total_embedded_words >= 15 and len(chars) >= 50:
                printable_count = sum(1 for c in chars if c.isprintable())
                printable_ratio = printable_count / len(chars)
                alnum_ratio = total_embedded_alnum / len(chars)
                cid_artifacts = full_text.lower().count("(cid:")
                replacement_chars = full_text.count("\ufffd")
                if printable_ratio >= 0.75 and alnum_ratio >= 0.40 and cid_artifacts <= 3 and replacement_chars <= 5:
                    valid_embedded = True

            page_texts: list[str] = []
            page_confs: list[float] = []
            pages_meta: list[dict] = []
            chosen_configs: list[dict] = []
            text_source = "ocr"

            if valid_embedded:
                text_source = "embedded"
                for page_idx, text in enumerate(embedded_texts):
                    page_texts.append(text)
                    words = [w for w in text.split() if any(c.isalnum() for c in w)]
                    word_count = len(words)
                    conf = 0.95 if word_count > 0 else 0.0
                    if word_count > 0:
                        page_confs.append(conf)
                    pages_meta.append({
                        "page": page_idx + 1,
                        "confidence": conf,
                        "wordCount": word_count,
                        "variant": "embedded",
                        "psm": 0,
                    })
                    chosen_configs.append({
                        "variant": "embedded",
                        "psm": 0,
                    })
            else:
                for page_idx in range(process_pages):
                    page = doc[page_idx]
                    rect = page.rect
                    # Scale matrix so rendered pixmap is high resolution (~200 DPI)
                    # while keeping max dimension bounded
                    max_side = max(rect.width, rect.height, 1)
                    zoom = min(TARGET_PDF_DPI_ZOOM, MAX_IMAGE_DIM / max_side)
                    mat = pymupdf.Matrix(zoom, zoom)

                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    pil_page = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    # Normalize rendered page image
                    norm_img, norm_warn = normalize_pil_image(pil_page)
                    warnings.extend([f"Page {page_idx+1}: {w}" for w in norm_warn])

                    # OCR page
                    ocr_res, ocr_warn = ocr_single_pil_image(norm_img)
                    warnings.extend([f"Page {page_idx+1}: {w}" for w in ocr_warn])

                    page_texts.append(ocr_res.text)
                    if ocr_res.word_count > 0:
                        page_confs.append(ocr_res.confidence)

                    pages_meta.append({
                        "page": page_idx + 1,
                        "confidence": ocr_res.confidence,
                        "wordCount": ocr_res.word_count,
                        "variant": ocr_res.variant_name,
                        "psm": ocr_res.psm_mode,
                    })
                    chosen_configs.append({
                        "variant": ocr_res.variant_name,
                        "psm": ocr_res.psm_mode,
                    })

            doc.close()

            # Assemble full document text with clear page markers
            if process_pages > 1:
                combined_text = "\n\n".join(
                    f"--- Page {i+1} ---\n{txt.strip()}" for i, txt in enumerate(page_texts) if txt.strip()
                )
            else:
                combined_text = page_texts[0] if page_texts else ""

            overall_conf = (
                round(sum(page_confs) / len(page_confs), 4) if page_confs else 0.0
            )
            ocr_status = determine_ocr_status(overall_conf, combined_text)

            return {
                "extractedText": combined_text[:25000],
                "ocrConfidence": overall_conf,
                "ocrStatus": ocr_status,
                "pageCount": total_pages,
                "ocrEngine": "CLOUD_API",
                "ocrConfig": chosen_configs[0] if chosen_configs else {"mode": "pdf"},
                "processingWarnings": warnings,
                "pages": pages_meta,
                "error": None if ocr_status != "FAILED" else "Assurley could not reliably read this document.",
                "textSource": text_source,
            }

        # ==========================
        # Case 2: Multi-Page TIFF
        # ==========================
        if mime == "image/tiff" or p.suffix.lower() in (".tif", ".tiff"):
            with Image.open(file_path) as tiff_img:
                total_pages = getattr(tiff_img, "n_frames", 1)
                process_pages = min(total_pages, MAX_PDF_PAGES)
                if total_pages > MAX_PDF_PAGES:
                    warnings.append(
                        f"TIFF has {total_pages} frames; processing limited to first {MAX_PDF_PAGES} frames."
                    )

                page_texts = []
                page_confs = []
                pages_meta = []
                chosen_configs = []

                for frame_idx in range(process_pages):
                    tiff_img.seek(frame_idx)
                    frame_copy = tiff_img.copy()
                    norm_img, norm_warn = normalize_pil_image(frame_copy)
                    warnings.extend([f"Frame {frame_idx+1}: {w}" for w in norm_warn])

                    ocr_res, ocr_warn = ocr_single_pil_image(norm_img)
                    warnings.extend([f"Frame {frame_idx+1}: {w}" for w in ocr_warn])

                    page_texts.append(ocr_res.text)
                    if ocr_res.word_count > 0:
                        page_confs.append(ocr_res.confidence)

                    pages_meta.append({
                        "page": frame_idx + 1,
                        "confidence": ocr_res.confidence,
                        "wordCount": ocr_res.word_count,
                        "variant": ocr_res.variant_name,
                        "psm": ocr_res.psm_mode,
                    })
                    chosen_configs.append({
                        "variant": ocr_res.variant_name,
                        "psm": ocr_res.psm_mode,
                    })

                if process_pages > 1:
                    combined_text = "\n\n".join(
                        f"--- Page {i+1} ---\n{txt.strip()}" for i, txt in enumerate(page_texts) if txt.strip()
                    )
                else:
                    combined_text = page_texts[0] if page_texts else ""

                overall_conf = (
                    round(sum(page_confs) / len(page_confs), 4) if page_confs else 0.0
                )
                ocr_status = determine_ocr_status(overall_conf, combined_text)

                return {
                    "extractedText": combined_text[:25000],
                    "ocrConfidence": overall_conf,
                    "ocrStatus": ocr_status,
                    "pageCount": total_pages,
                    "ocrEngine": "CLOUD_API",
                    "ocrConfig": chosen_configs[0] if chosen_configs else {},
                    "processingWarnings": warnings,
                    "pages": pages_meta,
                    "error": None if ocr_status != "FAILED" else "Assurley could not reliably read this document.",
                    "textSource": "ocr",
                }

        # ==========================
        # Case 3: Standard Single Image (PNG, JPG, WEBP)
        # ==========================
        with Image.open(file_path) as raw_img:
            norm_img, norm_warn = normalize_pil_image(raw_img)
            warnings.extend(norm_warn)

            ocr_res, ocr_warn = ocr_single_pil_image(norm_img)
            warnings.extend(ocr_warn)

            ocr_status = determine_ocr_status(ocr_res.confidence, ocr_res.text)

            return {
                "extractedText": ocr_res.text[:25000],
                "ocrConfidence": ocr_res.confidence,
                "ocrStatus": ocr_status,
                "pageCount": 1,
                "ocrEngine": "CLOUD_API",
                "ocrConfig": {
                    "variant": ocr_res.variant_name,
                    "psm": ocr_res.psm_mode,
                },
                "processingWarnings": warnings,
                "pages": [
                    {
                        "page": 1,
                        "confidence": ocr_res.confidence,
                        "wordCount": ocr_res.word_count,
                        "variant": ocr_res.variant_name,
                        "psm": ocr_res.psm_mode,
                    }
                ],
                "error": None if ocr_status != "FAILED" else "Assurley could not reliably read this document.",
                "textSource": "ocr",
            }

    except Exception as e:
        return {
            "extractedText": "",
            "ocrConfidence": 0.0,
            "ocrStatus": "FAILED",
            "pageCount": 0,
            "ocrEngine": "CLOUD_API",
            "ocrConfig": {},
            "processingWarnings": warnings + [f"Processing exception: {str(e)[:180]}"],
            "pages": [],
            "error": "Assurley could not reliably read this document.",
            "textSource": "ocr",
        }


# ---------------------------------------------------------------------------
# Structured Extraction & Field Normalization
# ---------------------------------------------------------------------------

def normalize_text_for_extraction(text: str) -> str:
    """
    Normalizes common OCR punctuation and character confusions before regex,
    while leaving the original text untouched.
    """
    t = text

    # Standardize whitespace and linebreaks
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)

    # Standardize unicode quotes and hyphens
    t = re.sub(r"[—–―−]", "-", t)
    t = re.sub(r"[`'‘’]", "'", t)
    t = re.sub(r'["“”]', '"', t)

    # Common OCR typo normalization for invoice labels:
    # 1nv -> Inv, 1nvoice -> Invoice
    t = re.sub(r"\b1nvoice\b", "Invoice", t, flags=re.IGNORECASE)
    t = re.sub(r"\b1nv\b", "Inv", t, flags=re.IGNORECASE)
    # N0. or No; or No- -> No:
    t = re.sub(r"\bNo[\.;\-]", "No:", t, flags=re.IGNORECASE)
    # Cust0mer -> Customer
    t = re.sub(r"\bCust0mer\b", "Customer", t, flags=re.IGNORECASE)
    # Vehic1e -> Vehicle, Regn -> Reg No
    t = re.sub(r"\bVehic1e\b", "Vehicle", t, flags=re.IGNORECASE)
    t = re.sub(r"\bRegn\b", "Reg", t, flags=re.IGNORECASE)
    # Common OCR misread of 'No:' -> 'Nar' or 'Na:' or 'Na'
    t = re.sub(r"\bInvoice\s+Na[r:]?\b", "Invoice No:", t, flags=re.IGNORECASE)
    t = re.sub(r"\bVehicle\s+Na[r:]?\b", "Vehicle No:", t, flags=re.IGNORECASE)

    # Standardize currency markers: Rs., Rs:, Rs/-, INR, ₹
    t = re.sub(r"(?:Rs[\.:/]?\s*|INR\s*|₹\s*)", "Rs. ", t, flags=re.IGNORECASE)

    return t


def normalize_vehicle_number(v: Optional[str]) -> Optional[str]:
    """
    Normalizes vehicle registration numbers for comparison:
    Removes spaces, hyphens, and standardizes 0/O and 1/I in standard Indian pattern.
    """
    if not v:
        return None
    raw = re.sub(r"[\s\-]", "", v).upper()
    # If it looks like Indian plate: 2 letters, 2 digits, 1-3 letters, 4 digits
    m = re.match(r"^([A-Z]{2})([0-9O]{2})([A-Z0-9]{1,3})([0-9O]{4})$", raw)
    if m:
        state = m.group(1)
        dist = m.group(2).replace("O", "0")
        series = m.group(3)
        num = m.group(4).replace("O", "0")
        return f"{state}{dist}{series}{num}"
    return raw


def parse_indian_date(d_str: Optional[str]) -> Optional[str]:
    """
    Parses common Indian date formats into a canonical string:
    - DD/MM/YYYY or DD-MM-YYYY
    - DD Mon YYYY (e.g. 15 Aug 2024, 15-Aug-2024)
    - DD Month YYYY (e.g. 15 August 2024)
    """
    if not d_str:
        return None
    clean = d_str.strip()
    patterns = [
        ("%d/%m/%Y", r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
        ("%d-%m-%Y", r"\b\d{1,2}-\d{1,2}-\d{4}\b"),
        ("%d.%m.%Y", r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"),
        ("%d %b %Y", r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b"),
        ("%d-%b-%Y", r"\b\d{1,2}-[A-Za-z]{3}-\d{4}\b"),
        ("%d %B %Y", r"\b\d{1,2}\s+[A-Za-z]{4,9}\s+\d{4}\b"),
    ]
    for fmt, regex in patterns:
        m = re.search(regex, clean, re.IGNORECASE)
        if m:
            val = m.group(0).strip()
            try:
                # Handle title-cased month names
                dt = datetime.strptime(val.title(), fmt)
                return dt.strftime("%d/%m/%Y")
            except Exception:
                return val
    return clean


def extract_structured_invoice_fields(raw_text: str) -> dict[str, Any]:
    """
    Deterministic regex-based extraction of insurance invoice fields
    from pre-normalized OCR text. Values that cannot be extracted are None.
    All present values carry source='regex'.
    """
    def field(value: Optional[str]) -> dict[str, Any]:
        if value:
            return {"value": value, "source": "regex"}
        return {"value": None, "source": "regex"}

    norm_text = normalize_text_for_extraction(raw_text)

    # Helper search
    def _find(patterns: list[str]) -> Optional[str]:
        for pat in patterns:
            m = re.search(pat, norm_text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        return None

    # Invoice No - require colon/hash or explicit 'no/number/#' token
    invoice_no = _find([
        r"(?:invoice|inv|bill)\s*(?:no|number|#|num)\s*[:\s#.-]*\s*([A-Z0-9][\w\-/]{2,30})",
        r"(?:invoice|inv|bill)\s*[:#]\s*([A-Z0-9][\w\-/]{2,30})",
    ])

    # Invoice Date (supporting Indian formats)
    invoice_date_raw = _find([
        r"(?:invoice\s*)?date[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:invoice\s*)?date[:\s]+(\d{1,2}(?:st|nd|rd|th)?[\s\/\-][A-Za-z]{3,9}[\s\/\-]\d{2,4})",
        r"date\s*of\s*invoice[:\s]+(\d{1,2}[\/\-\.][A-Za-z0-9]{1,9}[\/\-\.]\d{2,4})",
        r"billing\s*date[:\s]+(\d{1,2}[\/\-\.][A-Za-z0-9]{1,9}[\/\-\.]\d{2,4})",
        r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b",
    ])
    invoice_date = parse_indian_date(invoice_date_raw) if invoice_date_raw else None

    # Vehicle Registration Number (Indian patterns with optional spaces or hyphens)
    vehicle_no_raw = _find([
        r"(?:vehicle|reg(?:istration)?|reg\.?\s*no|veh\s*no|car\s*no)[:\s]+([A-Z]{2}[\s\-]*[0-9O]{1,2}[\s\-]*[A-Z0-9]{1,3}[\s\-]*[0-9O]{4})",
        r"\b([A-Z]{2}[\s\-]*[0-9O]{2}[\s\-]*[A-Z]{1,3}[\s\-]*[0-9O]{4})\b",
    ])
    vehicle_no = normalize_vehicle_number(vehicle_no_raw)

    # Customer / Claimant Name
    claimant_name = _find([
        r"(?:customer(?:\s*name)?|claimant|billed?\s*to|bill\s*to|insured\s*name)[:\s]+([A-Za-z][A-Za-z\s\.]{2,55}?)(?:\n|,|\bPhone\b|\bMob\b|\bGST\b|\bVehicle\b|\d)",
        r"(?:to\s*:|dear)[:\s]+([A-Za-z][A-Za-z\s\.]{2,55}?)(?:\n|,|\bPhone\b|\bMob\b|\bVehicle\b|\d)",
    ])
    if claimant_name:
        claimant_name = claimant_name.strip(" .,:-")
        # Ensure it's not a generic label
        if claimant_name.lower() in ("sir", "madam", "vehicle", "customer", "invoice"):
            claimant_name = None

    # Garage / Service Center
    garage = _find([
        r"(?:garage|service\s*cent(?:er|re)|workshop|authorized\s*dealership|dealer)[:\s]+([A-Za-z0-9][A-Za-z0-9\s&,\.\-]{2,75}?)(?:\n|$)",
        r"(?:workshop\s*name|dealer\s*name)[:\s]+([A-Za-z0-9][A-Za-z0-9\s&,\.\-]{2,75}?)(?:\n|$)",
        r"(?:from\s*:|sold\s*by)[:\s]+([A-Za-z0-9][A-Za-z0-9\s&,\.\-]{2,75}?)(?:\n|$)",
    ])
    if garage:
        garage = garage.strip(" .,:-")

    # Subtotal
    subtotal_raw = _find([
        r"sub[\s\-]?total[:\s]*(?:Rs\.\s*)?([\d,]+\.?\d*)",
        r"taxable\s*(?:value|amount)[:\s]*(?:Rs\.\s*)?([\d,]+\.?\d*)",
        r"sub\s*amount[:\s]*(?:Rs\.\s*)?([\d,]+\.?\d*)",
    ])

    # Tax (GST / CGST / SGST)
    tax_raw = _find([
        r"(?:total\s*)?(?:gst|igst|sgst|cgst|tax(?:\s*amount)?)(?:\s*\(\d+%\))?[:\s]*(?:Rs\.\s*)?([\d,]+\.?\d*)",
        r"(?:vat|service\s*tax)[:\s]*(?:Rs\.\s*)?([\d,]+\.?\d*)",
    ])

    # Grand Total
    total_raw = _find([
        r"(?:grand\s*total|net\s*payable|total\s*payable|amount\s*payable|total\s*invoice\s*amount|total\s*amount|balance\s*due)[:\s]*(?:Rs\.\s*)?([\d,]+\.?\d*)",
        r"\btotal[:\s]*(?:Rs\.\s*)?([\d,]+\.?\d*)",
    ])

    return {
        "invoiceNo": field(invoice_no),
        "invoiceDate": field(invoice_date),
        "vehicleNo": field(vehicle_no),
        "claimantName": field(claimant_name),
        "garage": field(garage),
        "subtotal": field(subtotal_raw),
        "tax": field(tax_raw),
        "grandTotal": field(total_raw),
    }


def classify_document(text: str) -> dict:
    """
    Classifies the document text into one of the supported document types using weighted keyword heuristics.
    """
    import re
    # 1. Normalizes the OCR text (lowercase, collapse whitespace)
    norm_text = re.sub(r'\s+', ' ', text).lower()
    
    types = {
        "REPAIR_INVOICE": {
            "keywords": {
                "invoice": 3, "bill": 2, "estimate": 2, "garage": 2, "service centre": 2, 
                "service center": 2, "workshop": 2, "subtotal": 2, "sub total": 2, "grand total": 3, 
                "gst": 2, "cgst": 2, "sgst": 2, "labour": 1, "labor": 1, "parts": 1, "spare": 1, 
                "painting": 1, "denting": 1, "repair": 1, "taxable": 1
            }
        },
        "VEHICLE_RC": {
            "keywords": {
                "registration certificate": 3, "registering authority": 3, "chassis": 2, "engine no": 2, 
                "rto": 2, "form 23": 2, "form no 23": 2, "date of registration": 2, "body type": 1, 
                "fuel": 1, "owner name": 1, "class of vehicle": 2, "seating capacity": 1, "manufacturer": 1
            }
        },
        "DRIVING_LICENCE": {
            "keywords": {
                "driving licence": 3, "driving license": 3, "dl no": 3, "transport authority": 2, 
                "lmv": 2, "mcwg": 2, "non-transport": 1, "date of issue": 1, "valid till": 1, 
                "blood group": 1, "badge": 1
            }
        },
        "INSURANCE_POLICY": {
            "keywords": {
                "policy schedule": 3, "sum insured": 3, "premium": 2, "idv": 3, "insurer": 2, 
                "comprehensive": 2, "third party": 2, "insured declared value": 3, "policy period": 2, 
                "policy number": 1, "deductible": 1, "endorsement": 1
            }
        },
        "POLICE_FIR": {
            "keywords": {
                "fir": 3, "first information report": 3, "police station": 2, "complainant": 2, 
                "ipc": 2, "cognizable": 2, "under section": 1, "investigating officer": 1, "offence": 1
            }
        }
    }
    
    best_type = "UNKNOWN"
    best_score = 0.0
    best_conf = 0.0
    best_matches = []
    
    for doc_type, data in types.items():
        score = 0
        matches = []
        max_possible_score = sum(data["keywords"].values())
        
        for kw, weight in data["keywords"].items():
            if kw in norm_text:
                score += weight
                matches.append(kw)
        
        confidence = min(1.0, score / max_possible_score) if max_possible_score > 0 else 0.0
        
        if score > best_score:
            best_score = score
            best_conf = confidence
            best_type = doc_type
            best_matches = matches

    if best_conf >= 0.15:
        return {
            "type": best_type,
            "heuristicScore": round(best_conf, 4),
            "method": "KEYWORD_HEURISTIC",
            "matchedPatterns": best_matches
        }
        
    return {
        "type": "UNKNOWN",
        "heuristicScore": 0.0,
        "method": "KEYWORD_HEURISTIC",
        "matchedPatterns": []
    }

def extract_rc_fields(raw_text: str) -> dict:
    from typing import Any, Optional
    def field(value: Optional[str]) -> dict:
        return {"value": value, "source": "regex", "page": None}

    norm_text = normalize_text_for_extraction(raw_text)

    def _find(patterns: list[str]) -> Optional[str]:
        for pat in patterns:
            m = re.search(pat, norm_text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        return None

    owner_name = _find([r"(?:owner|registered\s*owner)\s*name[:\s]*([A-Za-z\s\.]{2,50})(?:\n|,)"])
    reg_no_raw = _find([r"(?:registration|reg|regn)\s*(?:no|number)[\s:]*([A-Z0-9\s\-]{8,15})"])
    reg_no = normalize_vehicle_number(reg_no_raw)
    chassis_no = _find([r"(?:chassis|ch)\s*(?:no|number)[\s:]*([A-Z0-9]{5,20})"])
    engine_no = _find([r"engine\s*(?:no|number)[\s:]*([A-Z0-9]{5,20})"])
    vehicle_class = _find([r"(?:class\s*of\s*vehicle|vehicle\s*class|cov)[\s:]*([A-Za-z0-9\s\/\-]{2,20})(?:\n|,)"])
    fuel_type = _find([r"fuel\s*(?:type)?[\s:]*(Petrol|Diesel|CNG|Electric|LPG)"])
    maker_model = _find([r"(?:maker|model|make(?:\s*&\s*model)?)[\s:]*([A-Za-z0-9\s\.\-]{2,50})(?:\n|,)"])
    reg_date_raw = _find([r"date\s*of\s*registration[\s:]*(\d{1,2}[\/\-\.][A-Za-z0-9]{1,9}[\/\-\.]\d{2,4})"])
    reg_date = parse_indian_date(reg_date_raw) if reg_date_raw else None
    validity_raw = _find([r"valid\s*(?:upto|till)[\s:]*(\d{1,2}[\/\-\.][A-Za-z0-9]{1,9}[\/\-\.]\d{2,4})"])
    validity = parse_indian_date(validity_raw) if validity_raw else None
    rto = _find([r"(?:registering\s*authority|rto)[\s:]*([A-Za-z0-9\s\,\-]{2,50})(?:\n|,)"])

    return {
        "ownerName": field(owner_name),
        "registrationNumber": field(reg_no),
        "chassisNumber": field(chassis_no),
        "engineNumber": field(engine_no),
        "vehicleClass": field(vehicle_class),
        "fuelType": field(fuel_type),
        "makerModel": field(maker_model),
        "registrationDate": field(reg_date),
        "registrationValidity": field(validity),
        "rto": field(rto),
    }

def extract_dl_fields(raw_text: str) -> dict[str, Any]:
    def field(value: Optional[str]) -> dict[str, Any]:
        return {"value": value, "source": "regex", "page": None}

    norm_text = normalize_text_for_extraction(raw_text)

    def _find(patterns: list[str]) -> Optional[str]:
        for pat in patterns:
            m = re.search(pat, norm_text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        return None

    holder_name = _find([r"(?:name|holder\s*name)[\s:]*([A-Za-z\s\.]{2,50})(?:\n|,)"])
    dl_no = _find([r"(?:dl|licence)\s*(?:no|number)[\s:]*([A-Z0-9\s\-\/]{8,20})"])
    dob_raw = _find([r"(?:dob|date\s*of\s*birth)[\s:]*(\d{1,2}[\/\-\.][A-Za-z0-9]{1,9}[\/\-\.]\d{2,4})"])
    dob = parse_indian_date(dob_raw) if dob_raw else None
    issue_date_raw = _find([r"date\s*of\s*issue[\s:]*(\d{1,2}[\/\-\.][A-Za-z0-9]{1,9}[\/\-\.]\d{2,4})"])
    issue_date = parse_indian_date(issue_date_raw) if issue_date_raw else None
    valid_till_raw = _find([r"valid\s*(?:till|upto)[\s:]*(\d{1,2}[\/\-\.][A-Za-z0-9]{1,9}[\/\-\.]\d{2,4})"])
    valid_till = parse_indian_date(valid_till_raw) if valid_till_raw else None
    vehicle_class = _find([r"(LMV|MCWG|HMV)"])
    issuing_auth = _find([r"(?:issuing\s*authority|rto)[\s:]*([A-Za-z0-9\s\,\-]{2,50})(?:\n|,)"])
    blood_group = _find([r"blood\s*group[\s:]*([ABO][\+\-])"])

    return {
        "holderName": field(holder_name),
        "dlNumber": field(dl_no),
        "dateOfBirth": field(dob),
        "dateOfIssue": field(issue_date),
        "validTill": field(valid_till),
        "vehicleClass": field(vehicle_class),
        "issuingAuthority": field(issuing_auth),
        "bloodGroup": field(blood_group),
    }

def extract_policy_fields(raw_text: str) -> dict[str, Any]:
    def field(value: Optional[str]) -> dict[str, Any]:
        return {"value": value, "source": "regex", "page": None}

    norm_text = normalize_text_for_extraction(raw_text)

    def _find(patterns: list[str]) -> Optional[str]:
        for pat in patterns:
            m = re.search(pat, norm_text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        return None

    policy_no = _find([r"policy\s*(?:no|number)[\s:]*([A-Z0-9\-\/]{5,25})"])
    insured_name = _find([r"(?:name\s*of\s*insured|policyholder|insured\s*name)[\s:]*([A-Za-z\s\.]{2,50})(?:\n|,)"])
    vehicle_no_raw = _find([r"(?:vehicle|registration)\s*(?:no|number)[\s:]*([A-Z0-9\s\-]{8,15})"])
    vehicle_no = normalize_vehicle_number(vehicle_no_raw)
    idv = _find([r"(?:idv|insured\s*declared\s*value)[\s:]*(?:rs\.?\s*)?([\d,]+\.?\d*)"])
    premium = _find([r"premium(?: amount)?[\s:]*(?:rs\.?\s*)?([\d,]+\.?\d*)"])
    policy_period = _find([r"policy\s*period[\s:]*(.*?)(?:\n)"])
    insurer = _find([r"(?:insurance\s*company|insurer)[\s:]*([A-Za-z\s\.]{2,50})(?:\n|,)"])
    cover_type = _find([r"(Comprehensive|Third\s*Party|Own\s*Damage)"])

    return {
        "policyNumber": field(policy_no),
        "insuredName": field(insured_name),
        "vehicleNumber": field(vehicle_no),
        "idv": field(idv),
        "premium": field(premium),
        "policyPeriod": field(policy_period),
        "insurer": field(insurer),
        "coverType": field(cover_type),
    }

def extract_fir_fields(raw_text: str) -> dict[str, Any]:
    def field(value: Optional[str]) -> dict[str, Any]:
        return {"value": value, "source": "regex", "page": None}

    norm_text = normalize_text_for_extraction(raw_text)

    def _find(patterns: list[str]) -> Optional[str]:
        for pat in patterns:
            m = re.search(pat, norm_text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        return None

    fir_no = _find([r"fir\s*(?:no|number)[\s:]*([A-Z0-9\-\/]{3,20})"])
    police_station = _find([r"police\s*station[\s:]*([A-Za-z0-9\s\.]{2,50})(?:\n|,)"])
    fir_date_raw = _find([r"date\s*of\s*fir[\s:]*(\d{1,2}[\/\-\.][A-Za-z0-9]{1,9}[\/\-\.]\d{2,4})"])
    fir_date = parse_indian_date(fir_date_raw) if fir_date_raw else None
    complainant_name = _find([r"complainant\s*(?:name)?[\s:]*([A-Za-z\s\.]{2,50})(?:\n|,)"])
    sections = _find([r"(?:section|ipc\s*sections?)[\s:]*([A-Z0-9\s\,\-]{2,50})(?:\n|,)"])
    description = _find([r"(?:brief\s*description|gist)[\s:]*(.*?)(?:\n|$)"])

    return {
        "firNumber": field(fir_no),
        "policeStation": field(police_station),
        "firDate": field(fir_date),
        "complainantName": field(complainant_name),
        "sections": field(sections),
        "description": field(description),
    }

def extract_fields_by_type(raw_text: str, doc_type: str) -> dict[str, Any]:
    if doc_type == "REPAIR_INVOICE":
        return extract_structured_invoice_fields(raw_text)
    elif doc_type == "VEHICLE_RC":
        return extract_rc_fields(raw_text)
    elif doc_type == "DRIVING_LICENCE":
        return extract_dl_fields(raw_text)
    elif doc_type == "INSURANCE_POLICY":
        return extract_policy_fields(raw_text)
    elif doc_type == "POLICE_FIR":
        return extract_fir_fields(raw_text)
    else:
        return {}
