import re

with open('app/main.py', 'r', encoding='utf-8') as f:
    code = f.read()

# We want to replace everything from `def process_document(claim_id_value: str, document_id: str, path: str, mime: str):`
# up to the start of the next top-level definition, e.g., `@app.get("/health/live")` or whatever is next.

# Let's find what is next:
# Looking at the code, after process_document comes `@app.get("/health/live")` or something similar? No, health checks were moved up. Let's find the exact string.

new_process_doc = '''def process_document(claim_id_value: str, document_id: str, path: str, mime: str):
    """
    Robust OCR + structured extraction + verification + risk analysis pipeline.
    Handles PDF, TIFF, PNG, JPEG, and WEBP.
    Never crashes the server or corrupts state.
    """
    # 1. Update status to processing using lock
    with SessionLocal() as db:
        c = db.scalars(select(ClaimDB).where(ClaimDB.id == claim_id_value).with_for_update()).first()
        if not c:
            return
        docs = list(c.documents_json or [])
        idx = next((i for i, d in enumerate(docs) if d.get("id") == document_id), None)
        if idx is None:
            return
        docs[idx]["status"] = "processing"
        docs[idx]["ocrStatus"] = "PROCESSING"
        c.documents_json = docs
        flag_modified(c, "documents_json")
        db.commit()

    # 2. Run OCR OUTSIDE the transaction lock
    try:
        ocr_res = process_document_pipeline(path, mime)
    except Exception as e:
        ocr_res = {
            "ocrStatus": "FAILED",
            "ocrConfidence": 0.0,
            "extractedText": "",
            "pageCount": 0,
            "ocrEngine": "error",
            "ocrConfig": "",
            "processingWarnings": [f"Pipeline exception: {str(e)}"],
            "pages": [],
            "error": str(e)
        }

    # 3. Apply OCR results inside a new locked transaction
    with SessionLocal() as db:
        c = db.scalars(select(ClaimDB).where(ClaimDB.id == claim_id_value).with_for_update()).first()
        if not c:
            return
            
        docs = list(c.documents_json or [])
        idx = next((i for i, d in enumerate(docs) if d.get("id") == document_id), None)
        if idx is None:
            return

        status_str = ocr_res["ocrStatus"]
        docs[idx]["status"] = status_str.lower()
        docs[idx]["ocrStatus"] = status_str
        docs[idx]["ocrConfidence"] = ocr_res["ocrConfidence"]
        docs[idx]["extractedText"] = ocr_res["extractedText"]
        docs[idx]["pageCount"] = ocr_res["pageCount"]
        docs[idx]["ocrEngine"] = ocr_res["ocrEngine"]
        docs[idx]["ocrConfig"] = ocr_res["ocrConfig"]
        docs[idx]["processingWarnings"] = ocr_res["processingWarnings"]
        docs[idx]["pages"] = ocr_res["pages"]
        if ocr_res.get("error"):
            docs[idx]["error"] = ocr_res["error"]

        # Structured field extraction and verification
        if ocr_res["extractedText"]:
            classification = classify_document(ocr_res["extractedText"])
            doc_type = classification.get("type", "UNKNOWN")
            
            docs[idx]["docType"] = doc_type
            docs[idx]["classification"] = classification

            extracted = extract_fields_by_type(ocr_res["extractedText"], doc_type)
            docs[idx]["extractedFields"] = extracted
            
            verification = build_verification(c, extracted, doc_type)
            docs[idx]["verification"] = verification

        c.documents_json = docs
        flag_modified(c, "documents_json")

        if status_str != "FAILED":
            if c.status == "submitted":
                transition_claim_state(c, "documents")
            pages_desc = f"{ocr_res['pageCount']} page(s)" if ocr_res['pageCount'] > 1 else "Document"
            add_timeline(
                c,
                "Document processing completed",
                f"{pages_desc} read ({status_str.replace('_', ' ').title()}).",
            )
            flag_modified(c, "timeline_json")
        else:
            add_timeline(c, "Document processing failed", "Assurley could not reliably read this document.")
            flag_modified(c, "timeline_json")

        # Compute and persist risk score
        risk = compute_risk(c, docs)
        c.risk_json = risk
        c.risk_level = risk["level"]
        flag_modified(c, "risk_json")

        db.commit()'''

# Use regex to replace the old function block which is followed by `@app.get("/health/live")` or similar.
code = re.sub(
    r'def process_document\(claim_id_value: str, document_id: str, path: str, mime: str\):.*?(?=\n@app\.get\("/health/live"\))',
    new_process_doc + "\n",
    code,
    flags=re.DOTALL
)

with open('app/main.py', 'w', encoding='utf-8') as f:
    f.write(code)

print('process_document replaced successfully without duplicates.')
