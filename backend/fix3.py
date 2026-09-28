import re

with open('app/main.py', 'r', encoding='utf-8') as f:
    code = f.read()

new_reprocess_doc = '''def reprocess_document(
    claim_id_value: str,
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(db_session),
):
    """Admin endpoint to re-trigger the OCR pipeline on an existing document."""
    c = db.scalars(select(ClaimDB).where(ClaimDB.id == claim_id_value).with_for_update()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Claim not found.")

    docs = list(c.documents_json or [])
    doc = next((d for d in docs if d.get("id") == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if doc.get("status") == "processing":
        raise HTTPException(status_code=409, detail="Document is already processing.")

    stored_name = doc.get("storedName")
    if not stored_name:
        raise HTTPException(status_code=400, detail="Cannot reprocess document without stored file reference.")

    from pathlib import Path
    target = (Path("data/uploads") / claim_id_value / stored_name).resolve()
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Document file not found on server.")

    doc["status"] = "processing"
    doc["ocrStatus"] = "PROCESSING"
    doc["processingAttempts"] = doc.get("processingAttempts", 0) + 1
    
    from datetime import datetime, timezone
    doc["lastProcessingStartedAt"] = datetime.now(timezone.utc).isoformat()
    
    c.documents_json = docs
    flag_modified(c, "documents_json")

    add_timeline(
        c,
        "Document reprocessing started",
        f"An admin re-triggered processing for {doc.get('name', 'document')}.",
    )
    flag_modified(c, "timeline_json")
    db.commit()

    mime = doc.get("type", "application/octet-stream")
    background_tasks.add_task(process_document, claim_id_value, doc_id, str(target), mime)
    
    return serialize(c)'''

code = re.sub(
    r'def reprocess_document\([^)]+\):.*?return serialize\(c\)',
    new_reprocess_doc,
    code,
    flags=re.DOTALL
)

new_decide_claim = '''def decide_claim(claim_id_value: str, payload: DecisionIn, db: Session = Depends(db_session)):
    c = db.scalars(select(ClaimDB).where(ClaimDB.id == claim_id_value).with_for_update()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if payload.decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Decision must be approved or rejected.")
    
    try:
        transition_claim_state(c, payload.decision)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
        
    if payload.decision == "approved" and payload.approvedAmount is None:
        raise HTTPException(status_code=422, detail="Approved claims require a settlement amount.")
    
    c.decision_note = payload.note.strip()
    c.approved_amount = payload.approvedAmount if payload.decision == "approved" else None
    add_timeline(
        c,
        "Claim approved" if payload.decision == "approved" else "Claim rejected",
        "A human claims officer recorded the decision.",
    )
    flag_modified(c, "timeline_json")
    db.commit()
    db.refresh(c)
    return serialize(c)'''

code = re.sub(
    r'def decide_claim\(.*?return serialize\(c\)',
    new_decide_claim,
    code,
    flags=re.DOTALL
)

new_settle_claim = '''def settle_claim(claim_id_value: str, db: Session = Depends(db_session)):
    c = db.scalars(select(ClaimDB).where(ClaimDB.id == claim_id_value).with_for_update()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Claim not found.")
        
    try:
        transition_claim_state(c, "settled")
    except ValueError as e:
        raise HTTPException(status_code=409, detail="Only approved claims can be settled.")
        
    add_timeline(
        c,
        "Claim settled",
        "The settlement transfer has been recorded.",
    )
    flag_modified(c, "timeline_json")
    db.commit()
    db.refresh(c)
    return serialize(c)'''

code = re.sub(
    r'def settle_claim\(.*?return serialize\(c\)',
    new_settle_claim,
    code,
    flags=re.DOTALL
)

with open('app/main.py', 'w', encoding='utf-8') as f:
    f.write(code)

print('main.py locked endpoints and state machine updated.')
