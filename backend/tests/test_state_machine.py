import pytest
from app.main import ALLOWED_TRANSITIONS

def test_allowed_transitions():
    assert "documents" in ALLOWED_TRANSITIONS["submitted"]
    assert "approved" in ALLOWED_TRANSITIONS["review"]
    assert len(ALLOWED_TRANSITIONS["settled"]) == 0
    assert len(ALLOWED_TRANSITIONS["rejected"]) == 0

def test_decide_claim_guard():
    from app.main import transition_claim_state, ClaimDB
    
    # Valid transition
    c = ClaimDB(status="submitted")
    transition_claim_state(c, "documents")
    assert c.status == "documents"
    
    # Another valid transition
    transition_claim_state(c, "review")
    assert c.status == "review"
    
    # Invalid transition
    with pytest.raises(ValueError, match="Invalid state transition"):
        transition_claim_state(c, "settled")
        
    c.status = "approved"
    transition_claim_state(c, "settled")
    assert c.status == "settled"
