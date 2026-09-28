import threading
import time
import pytest
from app.main import SessionLocal, claim_id, ClaimDB
from app.ocr import process_document_pipeline

def test_process_document_concurrency(monkeypatch):
    """
    Tests that two concurrent process_document calls for the SAME claim 
    do not overwrite each other's updates (lost update anomaly).
    
    This validates the SELECT ... FOR UPDATE read-modify-write block.
    """
    # 1. Setup claim
    cid = claim_id()
    with SessionLocal() as db:
        c = ClaimDB(
            id=cid,
            claimant_name="Concurrency Test",
            email="test@example.com",
            policy_number="POL123",
            vehicle_number="ABC1234",
            vehicle_model="Honda",
            incident_date="2026-09-01",
            incident_location="Test",
            incident_type="Test",
            description="Test description that is quite long",
            status="submitted",
            documents_json=[
                {"id": "doc1", "status": "uploaded", "ocrStatus": "UPLOADED"},
                {"id": "doc2", "status": "uploaded", "ocrStatus": "UPLOADED"}
            ]
        )
        db.add(c)
        db.commit()

    # 2. Mock process_document_pipeline to be slow so they overlap
    #    This ensures they hit the read-modify-write block simultaneously
    def mock_pipeline(path, mime):
        time.sleep(1) # simulate slow OCR
        return {
            "ocrStatus": "PROCESSED",
            "ocrConfidence": 0.99,
            "extractedText": f"Dummy text for {path}",
            "pageCount": 1,
            "ocrEngine": "mock",
            "ocrConfig": "",
            "processingWarnings": [],
            "pages": [],
            "error": None
        }
    monkeypatch.setattr("app.main.process_document_pipeline", mock_pipeline)

    # 3. Import process_document AFTER monkeypatching
    from app.main import process_document

    # 4. Launch concurrent threads
    t1 = threading.Thread(target=process_document, args=(cid, "doc1", "path1", "image/jpeg"))
    t2 = threading.Thread(target=process_document, args=(cid, "doc2", "path2", "image/jpeg"))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # 5. Verify results
    with SessionLocal() as db:
        c = db.get(ClaimDB, cid)
        docs = c.documents_json
        assert len(docs) == 2
        assert docs[0]["status"] == "processed"
        assert docs[1]["status"] == "processed"
        assert docs[0]["ocrStatus"] == "PROCESSED"
        assert docs[1]["ocrStatus"] == "PROCESSED"
        
        # Verify the timeline has both events recorded
        timeline = c.timeline_json or []
        process_events = [t for t in timeline if t["title"] == "Document processing completed"]
        assert len(process_events) == 2
