import pytest
from app.main import compute_risk, ClaimDB

def test_compute_risk_versioning():
    # Setup mock claim
    claim = ClaimDB(
        id="CLAIM-123",
        estimated_amount=1000.0
    )
    
    docs = [
        {
            "docType": "REPAIR_INVOICE",
            "ocrConfidence": 0.95,
            "extractedFields": {
                "invoiceNo": {"value": "INV-1"},
                "vehicleNo": {"value": "MH02AB1234"},
                "grandTotal": {"value": "1100.00"}
            }
        }
    ]
    
    risk = compute_risk(claim, docs)
    assert "ruleVersion" in risk
    assert risk["ruleVersion"] == "1.0"
    assert risk["scoreType"] == "RULE_RISK_SCORE"
    assert "scoredAt" in risk
    assert risk["level"] in ("low", "medium", "high")
