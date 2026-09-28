import pytest
from app.ocr import classify_document

def test_classify_repair_invoice():
    text = "Grand Total Rs. 50,000 for repair at Service Center. Invoice No 1234."
    res = classify_document(text)
    assert res["type"] == "REPAIR_INVOICE"
    assert res["heuristicScore"] > 0
    assert "method" in res

def test_classify_rc():
    text = "Registration Certificate of Vehicle. Chassis No. 12345."
    res = classify_document(text)
    assert res["type"] == "VEHICLE_RC"
    assert res["heuristicScore"] > 0

def test_classify_dl():
    text = "Driving Licence issued by Transport Authority. DL No 4321."
    res = classify_document(text)
    assert res["type"] == "DRIVING_LICENCE"

def test_classify_policy():
    text = "Insurance Policy Schedule. Sum Insured Rs. 500,000. Premium Paid."
    res = classify_document(text)
    assert res["type"] == "INSURANCE_POLICY"

def test_classify_fir():
    text = "First Information Report filed at Police Station for IPC."
    res = classify_document(text)
    assert res["type"] == "POLICE_FIR"

def test_classify_unknown_few_words():
    # Less than 15 words, previously returned ACCIDENT_IMAGE
    text = "mh02ab1234 damage"
    res = classify_document(text)
    assert res["type"] == "UNKNOWN"
    assert res["heuristicScore"] == 0.0

def test_classify_unknown():
    # Lots of words but no keywords
    text = "This is a random document that contains many words but none of them relate to insurance, police, or vehicles. It should just be classified as an unknown type of document because the confidence will be very low."
    res = classify_document(text)
    assert res["type"] == "UNKNOWN"

