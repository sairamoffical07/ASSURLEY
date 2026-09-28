"""
Comprehensive test suite verifying Assurley's enhanced OCR pipeline:
1. Clear JPG invoice
2. Photographed JPG invoice (lighting/noise simulation)
3. PNG screenshot
4. One-page scanned PDF
5. Multi-page PDF (2 pages)
6. Rotated image (deskew test)
7. Low-resolution image (upscale test)
8. Blank image (empty text handling)
9. Corrupt & unsupported files (400 validation rejection)
10. Customer isolation & Admin drawer verification
"""

import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import pymupdf

BASE = "http://localhost:8000"
KEY = "test-admin-key-123"

PASS = []
FAIL = []


def report(name: str, cond: bool, extra: str = ""):
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name} {extra}", flush=True)
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name} {extra}", flush=True)


def post_json(url: str, data: dict, headers: dict = None) -> dict:
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, json.dumps(data).encode("utf-8"), headers=h, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, headers: dict = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_file(claim_id: str, email: str, filename: str, content: bytes, content_type: str) -> dict:
    boundary = "---AssurleyBoundary98765"
    cdisp = f'Content-Disposition: form-data; name="file"; filename="{filename}"'
    ctype = f"Content-Type: {content_type}"
    body = (
        f"--{boundary}\r\n{cdisp}\r\n{ctype}\r\n\r\n".encode("utf-8")
        + content
        + f"\r\n--{boundary}--\r\n".encode("utf-8")
    )
    req = urllib.request.Request(
        f"{BASE}/api/claims/{claim_id}/documents?email={email}",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for_document_ocr(claim_id: str, doc_id: str, max_seconds: int = 40) -> dict:
    start = time.time()
    while time.time() - start < max_seconds:
        claims = get_json(f"{BASE}/api/claims", {"X-Admin-Key": KEY})
        c = next((x for x in claims if x["id"] == claim_id), None)
        if c:
            d = next((x for x in c["documents"] if x["id"] == doc_id), None)
            if d and d.get("status") in ("processed", "failed", "low_confidence", "review_required"):
                return d
        time.sleep(1.5)
    claims = get_json(f"{BASE}/api/claims", {"X-Admin-Key": KEY})
    c = next((x for x in claims if x["id"] == claim_id), None)
    return next((x for x in c["documents"] if x["id"] == doc_id), {})


# ---------------------------------------------------------------------------
# Test Image & PDF Generators
# ---------------------------------------------------------------------------

def create_invoice_image(
    w=1200, h=900,
    inv_no="INV-2024-8841",
    date="18/08/2024",
    veh="TS09AB1234",
    cust="Ravi Kumar",
    garage="Hyderabad Auto Care",
    total="Rs. 18,200.00"
) -> Image.Image:
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
        font_head = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 26)
    except Exception:
        font = None
        font_head = None

    # Draw border and header bar
    draw.rectangle([(20, 20), (w - 20, h - 20)], outline=(180, 180, 180), width=2)
    draw.rectangle([(30, 30), (w - 30, 90)], fill=(240, 245, 243))
    draw.text((50, 42), "ESTIMATE & REPAIR INVOICE", font=font_head, fill=(10, 40, 35))

    lines = [
        f"Invoice No: {inv_no}",
        f"Date: {date}",
        f"Vehicle No: {veh}",
        f"Customer Name: {cust}",
        f"Service Workshop: {garage}",
        "--------------------------------------------------",
        "Part Replacement - Front Bumper Assembly:  Rs. 11,500.00",
        "Labor Charges - Painting & Fitting:        Rs. 4,000.00",
        "Subtotal:                                  Rs. 15,500.00",
        "GST (18%):                                 Rs. 2,700.00",
        f"Grand Total:                               {total}",
    ]
    y = 120
    for l in lines:
        draw.text((50, y), l, font=font, fill=(20, 20, 20))
        y += 48

    return img


def main():
    print("=" * 60)
    print("ASSURLEY ENHANCED OCR PIPELINE TEST SUITE")
    print("=" * 60)

    # Health check
    h = get_json(f"{BASE}/health/ready")
    report("Backend health endpoint", h.get("status") == "ok")

    # Create base claim
    claim = post_json(
        f"{BASE}/api/claims",
        {
            "claimantName": "Ravi Kumar",
            "email": "ravi.suite@example.com",
            "policyNumber": "POL-OCR-2024-001",
            "vehicleNumber": "TS09AB1234",
            "vehicleModel": "Maruti Baleno",
            "incidentDate": "2024-08-18",
            "incidentLocation": "Hyderabad",
            "incidentType": "Collision",
            "description": "Front collision at intersection resulting in cracked bumper and radiator grill damage.",
            "estimatedAmount": 18000.0,
        },
    )
    cid = claim["id"]
    email = "ravi.suite@example.com"
    report("Create Claim for OCR testing", claim.get("status") == "submitted", f"Claim ID: {cid}")

    # -----------------------------------------------------------------------
    # TEST 1: Clear JPG Invoice
    # -----------------------------------------------------------------------
    print("\n--- Test 1: Clear JPG Invoice ---")
    img1 = create_invoice_image(inv_no="INV-JPG-101", veh="TS09AB1234", total="Rs. 18,200.00")
    b1 = io.BytesIO()
    img1.save(b1, format="JPEG", quality=95)
    u1 = upload_file(cid, email, "clear_invoice.jpg", b1.getvalue(), "image/jpeg")
    doc1_id = u1["documents"][-1]["id"]
    res1 = wait_for_document_ocr(cid, doc1_id)
    report("Clear JPG processed", res1.get("ocrStatus") in ("PROCESSED", "LOW_CONFIDENCE"), f"Status: {res1.get('ocrStatus')}")
    report("Clear JPG confidence recorded", res1.get("ocrConfidence", 0) > 0.60, f"Conf: {res1.get('ocrConfidence')}")
    ef1 = res1.get("extractedFields", {})
    report("Clear JPG invoiceNo extracted", ef1.get("invoiceNo", {}).get("value") is not None, f"Val: {ef1.get('invoiceNo', {}).get('value')}")
    report("Clear JPG vehicleNo extracted", ef1.get("vehicleNo", {}).get("value") == "TS09AB1234", f"Val: {ef1.get('vehicleNo', {}).get('value')}")

    # -----------------------------------------------------------------------
    # TEST 2: Photographed JPG Invoice (Lighting / noise simulation)
    # -----------------------------------------------------------------------
    print("\n--- Test 2: Photographed JPG Invoice ---")
    img2 = create_invoice_image(inv_no="INV-PHOTO-202", veh="TS09AB1234")
    # Simulate phone photo: slight gradient illumination & compression
    arr2 = np.array(img2).astype(np.float32)
    h, w, _ = arr2.shape
    grad = np.tile(np.linspace(0.85, 1.05, w), (h, 1))[:, :, np.newaxis]
    arr2 = np.clip(arr2 * grad, 0, 255).astype(np.uint8)
    img2_photo = Image.fromarray(arr2)
    b2 = io.BytesIO()
    img2_photo.save(b2, format="JPEG", quality=75)
    u2 = upload_file(cid, email, "photo_invoice.jpg", b2.getvalue(), "image/jpeg")
    doc2_id = u2["documents"][-1]["id"]
    res2 = wait_for_document_ocr(cid, doc2_id)
    report("Photo JPG handled without failure", res2.get("ocrStatus") in ("PROCESSED", "LOW_CONFIDENCE", "REVIEW_REQUIRED"))
    report("Photo JPG extracted text present", len(res2.get("extractedText", "")) > 20)

    # -----------------------------------------------------------------------
    # TEST 3: PNG Screenshot
    # -----------------------------------------------------------------------
    print("\n--- Test 3: PNG Screenshot ---")
    img3 = create_invoice_image(inv_no="INV-PNG-303", veh="TS09AB1234", total="Rs. 17,800.00")
    b3 = io.BytesIO()
    img3.save(b3, format="PNG")
    u3 = upload_file(cid, email, "screenshot_bill.png", b3.getvalue(), "image/png")
    doc3_id = u3["documents"][-1]["id"]
    res3 = wait_for_document_ocr(cid, doc3_id)
    report("PNG screenshot processed", res3.get("ocrStatus") in ("PROCESSED", "LOW_CONFIDENCE"), f"Status: {res3.get('ocrStatus')}")
    report("PNG screenshot confidence >= 60%", res3.get("ocrConfidence", 0) >= 0.60, f"Conf: {res3.get('ocrConfidence')}")

    # -----------------------------------------------------------------------
    # TEST 4: One-Page Scanned PDF
    # -----------------------------------------------------------------------
    print("\n--- Test 4: One-Page Scanned PDF ---")
    pdf1 = pymupdf.open()
    page1 = pdf1.new_page(width=595, height=842)  # A4
    img4 = create_invoice_image(w=1100, h=800, inv_no="INV-PDF-404", veh="TS09AB1234")
    b4_img = io.BytesIO()
    img4.save(b4_img, format="PNG")
    page1.insert_image(pymupdf.Rect(40, 40, 555, 410), stream=b4_img.getvalue())
    b4_pdf = pdf1.write()
    pdf1.close()

    u4 = upload_file(cid, email, "scanned_invoice.pdf", b4_pdf, "application/pdf")
    doc4_id = u4["documents"][-1]["id"]
    res4 = wait_for_document_ocr(cid, doc4_id)
    report("1-page PDF processed via PyMuPDF", res4.get("ocrStatus") in ("PROCESSED", "LOW_CONFIDENCE"), f"Status: {res4.get('ocrStatus')}")
    report("1-page PDF pageCount is 1", res4.get("pageCount") == 1, f"Count: {res4.get('pageCount')}")
    report("1-page PDF extractedText present", len(res4.get("extractedText", "")) > 30)

    # -----------------------------------------------------------------------
    # TEST 5: Multi-Page PDF (2 Pages)
    # -----------------------------------------------------------------------
    print("\n--- Test 5: Multi-Page PDF ---")
    pdf2 = pymupdf.open()
    p1 = pdf2.new_page(width=595, height=842)
    img5_p1 = create_invoice_image(w=1100, h=800, inv_no="INV-MULTI-505", veh="TS09AB1234")
    b5_p1 = io.BytesIO()
    img5_p1.save(b5_p1, format="PNG")
    p1.insert_image(pymupdf.Rect(40, 40, 555, 410), stream=b5_p1.getvalue())

    p2 = pdf2.new_page(width=595, height=842)
    img5_p2 = Image.new("RGB", (1000, 600), (255, 255, 255))
    d2 = ImageDraw.Draw(img5_p2)
    d2.text((50, 50), "ANNEXURE - REPLACED SPARE PARTS BREAKDOWN", fill=(20, 20, 20))
    d2.text((50, 120), "1. Front Bumper Bumper Bracket - OEM Part #88210: Rs. 4,500.00", fill=(20, 20, 20))
    d2.text((50, 180), "2. Headlight RH Assembly - OEM Part #88211:       Rs. 7,000.00", fill=(20, 20, 20))
    d2.text((50, 260), "Certified by Authorized Surveyor: K. Srinivasan", fill=(20, 20, 20))
    b5_p2 = io.BytesIO()
    img5_p2.save(b5_p2, format="PNG")
    p2.insert_image(pymupdf.Rect(40, 40, 555, 370), stream=b5_p2.getvalue())

    b5_pdf = pdf2.write()
    pdf2.close()

    u5 = upload_file(cid, email, "two_page_invoice.pdf", b5_pdf, "application/pdf")
    doc5_id = u5["documents"][-1]["id"]
    res5 = wait_for_document_ocr(cid, doc5_id)
    report("Multi-page PDF processed", res5.get("ocrStatus") in ("PROCESSED", "LOW_CONFIDENCE"), f"Status: {res5.get('ocrStatus')}")
    report("Multi-page PDF pageCount == 2", res5.get("pageCount") == 2, f"Count: {res5.get('pageCount')}")
    report("Multi-page markers present in text", "--- Page 1 ---" in res5.get("extractedText", "") and "--- Page 2 ---" in res5.get("extractedText", ""))

    # -----------------------------------------------------------------------
    # TEST 6: Rotated Image (Deskew test)
    # -----------------------------------------------------------------------
    print("\n--- Test 6: Rotated Image (Deskew test) ---")
    img6 = create_invoice_image(inv_no="INV-ROT-606", veh="TS09AB1234")
    # Rotate by 4 degrees clockwise
    img6_rot = img6.rotate(-4.0, expand=True, fillcolor=(255, 255, 255))
    b6 = io.BytesIO()
    img6_rot.save(b6, format="PNG")
    u6 = upload_file(cid, email, "rotated_doc.png", b6.getvalue(), "image/png")
    doc6_id = u6["documents"][-1]["id"]
    res6 = wait_for_document_ocr(cid, doc6_id)
    report("Rotated image processed", res6.get("ocrStatus") in ("PROCESSED", "LOW_CONFIDENCE", "REVIEW_REQUIRED"))
    report("Rotated image warnings recorded deskew", any("deskew" in str(w).lower() for w in res6.get("processingWarnings", [])))

    # -----------------------------------------------------------------------
    # TEST 7: Low-Resolution Image (Upscale test)
    # -----------------------------------------------------------------------
    print("\n--- Test 7: Low-Resolution Image ---")
    img7_small = create_invoice_image(w=450, h=320, inv_no="INV-LR-707", veh="TS09AB1234")
    b7 = io.BytesIO()
    img7_small.save(b7, format="PNG")
    u7 = upload_file(cid, email, "lowres_invoice.png", b7.getvalue(), "image/png")
    doc7_id = u7["documents"][-1]["id"]
    res7 = wait_for_document_ocr(cid, doc7_id)
    report("Low-res image handled without crash", res7.get("ocrStatus") is not None)
    report("Low-res image upscale warning recorded", any("upscale" in str(w).lower() for w in res7.get("processingWarnings", [])))

    # -----------------------------------------------------------------------
    # TEST 8: Blank Image (Empty OCR handling)
    # -----------------------------------------------------------------------
    print("\n--- Test 8: Blank Image ---")
    img8 = Image.new("RGB", (600, 600), (255, 255, 255))
    b8 = io.BytesIO()
    img8.save(b8, format="PNG")
    u8 = upload_file(cid, email, "blank_page.png", b8.getvalue(), "image/png")
    doc8_id = u8["documents"][-1]["id"]
    res8 = wait_for_document_ocr(cid, doc8_id)
    report("Blank image marked FAILED cleanly", res8.get("ocrStatus") == "FAILED", f"Status: {res8.get('ocrStatus')}")
    report("Blank image error message present", res8.get("error") is not None, f"Error: {res8.get('error')}")

    # -----------------------------------------------------------------------
    # TEST 9: Corrupt / Unsupported File Upload (HTTP 400 Rejection)
    # -----------------------------------------------------------------------
    print("\n--- Test 9: Corrupt & Unsupported Files ---")
    # Corrupt PDF (junk bytes)
    corrupt_pdf_rejected = False
    try:
        upload_file(cid, email, "corrupt.pdf", b"NOT_A_REAL_PDF_JUST_RANDOM_GARBAGE_BYTES_12345", "application/pdf")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            corrupt_pdf_rejected = True
    report("Corrupt PDF rejected with HTTP 400", corrupt_pdf_rejected)

    # Executable file / unsupported MIME
    unsupported_rejected = False
    try:
        upload_file(cid, email, "malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/x-msdownload")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            unsupported_rejected = True
    report("Unsupported .exe rejected with HTTP 400", unsupported_rejected)

    # Fake extension (text file named invoice.png)
    fake_ext_rejected = False
    try:
        upload_file(cid, email, "invoice.png", b"Hello this is just a plain text file pretending to be PNG", "image/png")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            fake_ext_rejected = True
    report("Fake PNG extension rejected with HTTP 400", fake_ext_rejected)

    # -----------------------------------------------------------------------
    # TEST 10: Customer Isolation & Admin Document Viewing
    # -----------------------------------------------------------------------
    print("\n--- Test 10: Customer Isolation & Admin Document Retrieval ---")
    # Customer view
    cust_view = get_json(f"{BASE}/api/claims/{cid}?email={email}")
    report("riskAnalysis hidden from customer", "riskAnalysis" not in cust_view)
    all_cust_docs = cust_view.get("documents", [])
    report("raw OCR text hidden from customer", all("extractedText" not in d for d in all_cust_docs))
    report("extractedFields hidden from customer", all("extractedFields" not in d for d in all_cust_docs))
    report("storedName hidden from customer", all("storedName" not in d for d in all_cust_docs))

    # Admin retrieval with X-Admin-Key
    req_file = urllib.request.Request(
        f"{BASE}/api/claims/{cid}/documents/{doc1_id}/file",
        headers={"X-Admin-Key": KEY},
    )
    with urllib.request.urlopen(req_file) as f_resp:
        doc_bytes = f_resp.read()
        report("Admin can securely download document", len(doc_bytes) > 0, f"Bytes: {len(doc_bytes)}")
        report("Correct Content-Type returned", "image/jpeg" in f_resp.headers.get("Content-Type", ""))

    # Admin retrieval without key must return 401
    no_key_rejected = False
    try:
        urllib.request.urlopen(f"{BASE}/api/claims/{cid}/documents/{doc1_id}/file")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            no_key_rejected = True
    report("Unauthenticated document access rejected with 401", no_key_rejected)

    # -----------------------------------------------------------------------
    # TEST 11: Claim Verification & Rule-Based Risk Analysis
    # -----------------------------------------------------------------------
    print("\n--- Test 11: Verification & Rule-Based Risk ---")
    admin_claims = get_json(f"{BASE}/api/claims", {"X-Admin-Key": KEY})
    target_claim = next((c for c in admin_claims if c["id"] == cid), None)
    risk = target_claim.get("riskAnalysis")
    report("Risk analysis computed on claim", risk is not None)
    report("Risk method is explicitly RULE_BASED", risk.get("method") == "RULE_BASED", f"Method: {risk.get('method')}")
    report("Risk score in valid range 0-100", 0 <= risk.get("score", -1) <= 100, f"Score: {risk.get('score')}")
    report("Risk level is valid category", risk.get("level") in ("low", "medium", "high"), f"Level: {risk.get('level')}")

    print("\n" + "=" * 60)
    print(f"FINAL RESULT: {len(PASS)} PASSED, {len(FAIL)} FAILED")
    print("=" * 60)
    if FAIL:
        print("FAILED TESTS:")
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
