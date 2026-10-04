from __future__ import annotations

import json
import os
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import JSON, DateTime, Float, String, Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from dotenv import load_dotenv

from app.ocr import (
    SUPPORTED_MIMES,
    classify_document,
    extract_fields_by_type,
    normalize_vehicle_number,
    process_document_pipeline,
    validate_file_content,
)

APP_DIR = Path(__file__).resolve().parent.parent
load_dotenv(APP_DIR / ".env", override=True)
if os.getenv("VERCEL"):
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/assurley.db")
    UPLOAD_DIR = Path("/tmp/uploads")
else:
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{APP_DIR / 'data' / 'assurley.db'}")
    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", APP_DIR / "data" / "uploads"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_KEY = os.getenv("ADMIN_KEY")
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "12"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class ClaimDB(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    claimant_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    policy_number: Mapped[str] = mapped_column(String(80), index=True)
    vehicle_number: Mapped[str] = mapped_column(String(40), index=True)
    vehicle_model: Mapped[str] = mapped_column(String(160))
    incident_date: Mapped[str] = mapped_column(String(20))
    incident_location: Mapped[str] = mapped_column(String(255))
    incident_type: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    estimated_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    risk_level: Mapped[str] = mapped_column(String(30), default="not-evaluated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    documents_json: Mapped[list] = mapped_column(JSON, default=list)
    timeline_json: Mapped[list] = mapped_column(JSON, default=list)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)


# ---------------------------------------------------------------------------
# Schema bootstrap — safe inspection-first migration for SQLite
# ---------------------------------------------------------------------------
Base.metadata.create_all(engine)

if DATABASE_URL.startswith("sqlite"):
    _inspector = inspect(engine)
    _existing_cols = {c["name"] for c in _inspector.get_columns("claims")}
    if "risk_json" not in _existing_cols:
        with engine.connect() as _conn:
            _conn.execute(text("ALTER TABLE claims ADD COLUMN risk_json JSON"))
            _conn.commit()


app = FastAPI(
    title="Assurley API",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)


class ClaimCreate(BaseModel):
    claimantName: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=50)
    policyNumber: str = Field(min_length=2, max_length=80)
    vehicleNumber: str = Field(min_length=2, max_length=40)
    vehicleModel: str = Field(min_length=2, max_length=160)
    incidentDate: str = Field(min_length=8, max_length=20)
    incidentLocation: str = Field(min_length=2, max_length=255)
    incidentType: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=20, max_length=5000)
    estimatedAmount: Optional[float] = Field(default=None, ge=0)


class DecisionIn(BaseModel):
    decision: str
    note: str = Field(min_length=2, max_length=4000)
    approvedAmount: Optional[float] = Field(default=None, ge=0)


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(x_admin_key: Optional[str] = Header(default=None)):
    expected = os.getenv("ADMIN_KEY") or ADMIN_KEY
    if not expected:
        raise HTTPException(status_code=503, detail="Operations access is not configured on the server.")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid operations access key.")


def serialize(c: ClaimDB) -> dict:
    return {
        "id": c.id,
        "claimantName": c.claimant_name,
        "email": c.email,
        "phone": c.phone,
        "policyNumber": c.policy_number,
        "vehicleNumber": c.vehicle_number,
        "vehicleModel": c.vehicle_model,
        "incidentDate": c.incident_date,
        "incidentLocation": c.incident_location,
        "incidentType": c.incident_type,
        "description": c.description,
        "estimatedAmount": c.estimated_amount,
        "status": c.status,
        "riskLevel": c.risk_level,
        "createdAt": c.created_at.isoformat(),
        "documents": c.documents_json or [],
        "timeline": c.timeline_json or [],
        "decisionNote": c.decision_note,
        "approvedAmount": c.approved_amount,
        "riskAnalysis": c.risk_json,
    }


def claim_id() -> str:
    now = datetime.now(timezone.utc)
    return f"ASL-{now:%Y%m%d}-{secrets.token_hex(3).upper()}"


def add_timeline(c: ClaimDB, title: str, detail: Optional[str] = None):
    items = list(c.timeline_json or [])
    items.append({"at": datetime.now(timezone.utc).isoformat(), "title": title, "detail": detail})
    c.timeline_json = items


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------

_STATUS_MATCH = "MATCH"
_STATUS_MISMATCH = "MISMATCH"
_STATUS_REVIEW = "REVIEW"
_STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# Claim status state machine
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"documents", "review"},
    "documents": {"review"},
    "review": {"approved", "rejected"},
    "approved": {"settled"},
    "rejected": set(),
    "settled": set(),
}

def transition_claim_state(c: ClaimDB, new_status: str):
    allowed = ALLOWED_TRANSITIONS.get(c.status, set())
    if new_status not in allowed:
        raise ValueError(f"Invalid state transition: {c.status} -> {new_status}")
    c.status = new_status


def _parse_amount(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _name_norm(n: str) -> str:
    return re.sub(r"\s+", " ", (n or "").lower().strip())


def build_verification(claim: ClaimDB, extracted: dict, doc_type: str = "REPAIR_INVOICE") -> dict:
    """
    Compare extracted fields against claim data based on document type.
    Returns per-check dicts with status, claimValue, invoiceValue.
    A mismatch is a review signal, not proof of fraud.
    """
    checks = {}

    # --- Vehicle number ---
    if doc_type in ("REPAIR_INVOICE", "VEHICLE_RC", "INSURANCE_POLICY"):
        claim_veh = normalize_vehicle_number(claim.vehicle_number) or ""
        field_key = "registrationNumber" if doc_type == "VEHICLE_RC" else "vehicleNo"
        if doc_type == "INSURANCE_POLICY": field_key = "vehicleNumber"
        
        inv_veh_raw = (extracted.get(field_key) or {}).get("value")
        if inv_veh_raw:
            inv_veh = normalize_vehicle_number(inv_veh_raw) or ""
            status = _STATUS_MATCH if claim_veh == inv_veh else _STATUS_MISMATCH
        else:
            inv_veh = None
            status = _STATUS_NOT_AVAILABLE
        checks["vehicleNumber"] = {
            "label": "Vehicle Number",
            "claimValue": claim.vehicle_number,
            "invoiceValue": inv_veh_raw,
            "normalizedClaim": claim_veh,
            "normalizedInvoice": inv_veh,
            "status": status,
        }

    # --- Claimant name ---
    if doc_type in ("REPAIR_INVOICE", "VEHICLE_RC", "DRIVING_LICENCE", "INSURANCE_POLICY"):
        claim_name = _name_norm(claim.claimant_name)
        field_key = "claimantName"
        if doc_type == "VEHICLE_RC": field_key = "ownerName"
        elif doc_type == "DRIVING_LICENCE": field_key = "holderName"
        elif doc_type == "INSURANCE_POLICY": field_key = "insuredName"

        inv_name_raw = (extracted.get(field_key) or {}).get("value")
        if inv_name_raw:
            inv_name = _name_norm(inv_name_raw)
            claim_words = set(claim_name.split())
            inv_words = set(inv_name.split())
            shorter = claim_words if len(claim_words) <= len(inv_words) else inv_words
            if shorter and shorter.issubset(claim_words | inv_words) and len(shorter & (claim_words | inv_words)) >= max(1, len(shorter) - 1):
                name_status = _STATUS_MATCH if claim_name == inv_name else _STATUS_REVIEW
            else:
                name_status = _STATUS_MISMATCH
        else:
            inv_name_raw = None
            inv_name = None
            name_status = _STATUS_NOT_AVAILABLE
        checks["claimantName"] = {
            "label": "Name Match",
            "claimValue": claim.claimant_name,
            "invoiceValue": inv_name_raw,
            "normalizedClaim": claim_name,
            "normalizedInvoice": inv_name,
            "status": name_status,
        }

    # --- Invoice total vs estimated amount ---
    if doc_type == "REPAIR_INVOICE":
        total_raw = (extracted.get("grandTotal") or {}).get("value")
        invoice_total = _parse_amount(total_raw)
        estimated = claim.estimated_amount
        if invoice_total is not None and estimated is not None and estimated > 0:
            ratio = invoice_total / estimated
            if ratio <= 1.20:
                amt_status = _STATUS_MATCH
            elif ratio <= 1.40:
                amt_status = _STATUS_REVIEW
            else:
                amt_status = _STATUS_MISMATCH
        elif invoice_total is not None:
            amt_status = _STATUS_REVIEW
        else:
            amt_status = _STATUS_NOT_AVAILABLE
        checks["claimAmount"] = {
            "label": "Claim Amount",
            "claimValue": f"₹{estimated:,.2f}" if estimated is not None else None,
            "invoiceValue": f"₹{invoice_total:,.2f}" if invoice_total is not None else total_raw,
            "parsedInvoiceTotal": invoice_total,
            "status": amt_status,
        }

    return checks


# ---------------------------------------------------------------------------
# Rule-based risk scoring
# ---------------------------------------------------------------------------

def compute_risk(claim: ClaimDB, docs: list) -> dict:
    """
    Deterministic rule-based risk scoring.
    Method is explicitly RULE_BASED — not ML, not LLM.
    A mismatch is a review signal, not proof of fraud.
    """
    score = 0
    reasons = []

    all_verifications = [d.get("verification") or {} for d in docs if d.get("verification")]
    all_extracted = [d.get("extractedFields") or {} for d in docs if d.get("extractedFields")]

    # --- Vehicle number mismatch ---
    veh_statuses = [v.get("vehicleNumber", {}).get("status") for v in all_verifications]
    if _STATUS_MISMATCH in veh_statuses:
        score += 25
        reasons.append({
            "rule": "vehicle_mismatch",
            "description": "Vehicle number on invoice does not match policy/claim vehicle number.",
            "points": 25,
            "source": "DOCUMENT",
        })

    # --- Claimant name mismatch ---
    name_statuses = [v.get("claimantName", {}).get("status") for v in all_verifications]
    if _STATUS_MISMATCH in name_statuses:
        score += 15
        reasons.append({
            "rule": "claimant_name_mismatch",
            "description": "Claimant name on invoice does not match the name on the claim.",
            "points": 15,
            "source": "DOCUMENT",
        })

    # --- Document processing failure ---
    failed_docs = [
        d for d in docs
        if d.get("status") in ("failed", "FAILED") or d.get("ocrStatus") == "FAILED"
    ]
    if failed_docs:
        score += 15
        reasons.append({
            "rule": "document_processing_failure",
            "description": f"{len(failed_docs)} document(s) could not be processed. Manual review of originals is required.",
            "points": 15,
            "source": "DOCUMENT",
        })

    # --- OCR confidence (pick worst valid document, avoid double-counting) ---
    valid_ocr_confs = [
        d.get("ocrConfidence")
        for d in docs
        if d.get("ocrConfidence") is not None
        and d.get("ocrStatus") != "FAILED"
        and d.get("status") not in ("failed", "uploaded", "processing")
    ]
    if valid_ocr_confs:
        min_conf = min(valid_ocr_confs)
        if min_conf < 0.60:
            score += 15
            reasons.append({
                "rule": "ocr_low_confidence",
                "description": f"OCR confidence is very low ({round(min_conf*100)}%). Extracted text may be unreliable.",
                "points": 15,
                "source": "DOCUMENT",
            })
        elif min_conf < 0.75:
            score += 8
            reasons.append({
                "rule": "ocr_moderate_confidence",
                "description": f"OCR confidence is below 75% ({round(min_conf*100)}%). Review extracted fields carefully.",
                "points": 8,
                "source": "DOCUMENT",
            })

    # --- Missing critical invoice fields ---
    invoices = [d for d in docs if d.get("docType") == "REPAIR_INVOICE"]
    if invoices:
        all_invoice_extracted = [d.get("extractedFields") or {} for d in invoices]
        CRITICAL_FIELDS = ("invoiceNo", "vehicleNo", "grandTotal")
        found_fields = set()
        for ex in all_invoice_extracted:
            for f in CRITICAL_FIELDS:
                if (ex.get(f) or {}).get("value"):
                    found_fields.add(f)
        missing_count = sum(1 for f in CRITICAL_FIELDS if f not in found_fields)
        
        if missing_count >= 2:
            score += 15
            reasons.append({
                "rule": "missing_critical_fields",
                "description": f"{missing_count} of {len(CRITICAL_FIELDS)} critical invoice fields (invoice number, vehicle number, total) could not be extracted from the invoice.",
                "points": 15,
                "source": "DOCUMENT",
            })

    # --- Invoice total vs estimated amount ---
    invoice_totals = []
    for ex in all_extracted:
        total_raw = (ex.get("grandTotal") or {}).get("value")
        t = _parse_amount(total_raw)
        if t is not None:
            invoice_totals.append(t)

    estimated = claim.estimated_amount
    if invoice_totals and estimated and estimated > 0:
        max_ratio = max(t / estimated for t in invoice_totals)
        if max_ratio >= 1.40:
            score += 25
            reasons.append({
                "rule": "invoice_total_high",
                "description": f"Invoice total is {round((max_ratio-1)*100)}% above the estimated claim amount.",
                "points": 25,
                "source": "DOCUMENT",
            })
        elif max_ratio >= 1.20:
            score += 15
            reasons.append({
                "rule": "invoice_total_elevated",
                "description": f"Invoice total is {round((max_ratio-1)*100)}% above the estimated claim amount.",
                "points": 15,
                "source": "DOCUMENT",
            })

    score = min(score, 100)

    if score < 30:
        level = "low"
        recommendation = "No major rule-based concerns detected."
    elif score < 60:
        level = "medium"
        recommendation = "Review supporting evidence before making a decision."
    else:
        level = "high"
        recommendation = "Manual review recommended before proceeding."

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "recommendation": recommendation,
        "method": "RULE_BASED",
        "scoreType": "RULE_RISK_SCORE",
        "ruleVersion": "1.0",
        "scoredAt": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Document processing (background task)
# ---------------------------------------------------------------------------

def process_document(claim_id_value: str, document_id: str, path: str, mime: str):
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

        db.commit()

@app.get("/health/live")
def health_live():
    return {"status": "alive"}

@app.get("/health/ready")
@app.get("/health")
def health_ready():
    checks = {"service": "assurley-api", "version": "1.1.0"}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["db"] = "connected"
    except Exception:
        checks["db"] = "unreachable"
    
    try:
        import shutil
        tess_path = shutil.which("tesseract")
        if tess_path:
            checks["tesseract"] = "available"
        else:
            checks["tesseract"] = "not_in_path"
    except Exception:
        checks["tesseract"] = "unknown"
        
    checks["status"] = "ok" if checks["db"] == "connected" and checks["tesseract"] == "available" else "degraded"
    
    if checks["status"] == "degraded":
        raise HTTPException(status_code=503, detail=checks)
    return checks


@app.post("/api/claims")
def create_claim(payload: ClaimCreate, db: Session = Depends(db_session)):
    cid = claim_id()
    c = ClaimDB(
        id=cid,
        claimant_name=payload.claimantName.strip(),
        email=str(payload.email).lower(),
        phone=payload.phone.strip() if payload.phone else None,
        policy_number=payload.policyNumber.strip().upper(),
        vehicle_number=payload.vehicleNumber.strip().upper(),
        vehicle_model=payload.vehicleModel.strip(),
        incident_date=payload.incidentDate,
        incident_location=payload.incidentLocation.strip(),
        incident_type=payload.incidentType.strip(),
        description=payload.description.strip(),
        estimated_amount=payload.estimatedAmount,
        status="submitted",
        risk_level="not-evaluated",
        documents_json=[],
        timeline_json=[],
        risk_json=None,
    )
    add_timeline(c, "Claim submitted", "Your claim entered the Assurley workflow.")
    db.add(c)
    db.commit()
    db.refresh(c)
    return serialize(c)


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: str, email: str = Query(min_length=3), db: Session = Depends(db_session)):
    c = db.get(ClaimDB, claim_id)
    if not c or c.email.lower() != email.lower():
        raise HTTPException(status_code=404, detail="We could not find a claim matching that ID and email address.")
    # Return customer-safe view: strictly strip internal admin-only fields
    data = serialize(c)
    data.pop("riskAnalysis", None)
    for doc in data.get("documents", []):
        doc.pop("extractedText", None)
        doc.pop("extractedFields", None)
        doc.pop("verification", None)
        doc.pop("storedName", None)
        doc.pop("ocrConfidence", None)
        doc.pop("ocrConfig", None)
        doc.pop("processingWarnings", None)
        doc.pop("pages", None)
        doc.pop("error", None)
    return data


@app.get("/api/claims", dependencies=[Depends(require_admin)])
def list_claims(db: Session = Depends(db_session)):
    claims = db.scalars(select(ClaimDB).order_by(ClaimDB.created_at.desc())).all()
    return [serialize(c) for c in claims]


@app.get(
    "/api/claims/{claim_id_value}/documents/{doc_id}/file",
    dependencies=[Depends(require_admin)],
)
def serve_document(claim_id_value: str, doc_id: str, db: Session = Depends(db_session)):
    """Securely serve an uploaded document to authorized admin users only."""
    c = db.get(ClaimDB, claim_id_value)
    if not c:
        raise HTTPException(status_code=404, detail="Claim not found.")

    docs = c.documents_json or []
    doc = next((d for d in docs if d.get("id") == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    stored_name = doc.get("storedName")
    if not stored_name:
        raise HTTPException(
            status_code=404,
            detail="Document file reference is not available.",
        )

    upload_root = UPLOAD_DIR.resolve()
    target = (UPLOAD_DIR / claim_id_value / stored_name).resolve()

    if not target.is_relative_to(upload_root):
        raise HTTPException(status_code=403, detail="Access denied.")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Document file not found on server.")

    mime = doc.get("type", "application/octet-stream")
    original_name = doc.get("name", stored_name)

    return FileResponse(
        path=str(target),
        media_type=mime,
        filename=original_name,
        headers={"Content-Disposition": f'inline; filename="{original_name}"'},
    )


@app.post(
    "/api/claims/{claim_id_value}/documents/{doc_id}/reprocess",
    dependencies=[Depends(require_admin)],
)
def reprocess_document(
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

    target = (UPLOAD_DIR / claim_id_value / stored_name).resolve()
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Document file not found on server.")

    doc["status"] = "processing"
    doc["ocrStatus"] = "PROCESSING"
    doc["processingAttempts"] = doc.get("processingAttempts", 0) + 1
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
    
    return serialize(c)


@app.post("/api/claims/{claim_id_value}/documents")
def upload_document(
    claim_id_value: str,
    background_tasks: BackgroundTasks,
    email: str = Query(min_length=3),
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
):
    c = db.get(ClaimDB, claim_id_value)
    if not c or c.email.lower() != email.lower():
        raise HTTPException(status_code=404, detail="Claim not found.")

    content = file.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_MB} MB upload limit.")
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    # Validate file content and readability (reject unsupported/corrupted files with clear 400 response)
    try:
        canonical_mime, detected_format, validation_warnings = validate_file_content(content, file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ext = Path(file.filename or "file").suffix.lower()
    if not ext or ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"):
        ext_map = {
            "application/pdf": ".pdf",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/tiff": ".tiff",
        }
        ext = ext_map.get(canonical_mime, ".bin")

    safe_name = f"{secrets.token_hex(12)}{ext}"
    claim_dir = UPLOAD_DIR / claim_id_value
    claim_dir.mkdir(parents=True, exist_ok=True)
    dest = claim_dir / safe_name
    dest.write_bytes(content)

    did = f"DOC-{secrets.token_hex(5).upper()}"
    docs = list(c.documents_json or [])
    docs.append({
        "id": did,
        "name": Path(file.filename or "document").name[:180],
        "storedName": safe_name,
        "type": canonical_mime,
        "size": len(content),
        "status": "uploaded",
        "ocrStatus": "UPLOADED",
        "pageCount": 1,
    })
    c.documents_json = docs
    flag_modified(c, "documents_json")
    add_timeline(c, "Document uploaded", Path(file.filename or "document").name[:180])
    flag_modified(c, "timeline_json")
    db.commit()
    db.refresh(c)
    background_tasks.add_task(process_document, claim_id_value, did, str(dest), canonical_mime)
    return serialize(c)


@app.post("/api/claims/{claim_id_value}/decision", dependencies=[Depends(require_admin)])
def decide_claim(claim_id_value: str, payload: DecisionIn, db: Session = Depends(db_session)):
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
    return serialize(c)


@app.post("/api/claims/{claim_id_value}/settle", dependencies=[Depends(require_admin)])
def settle_claim(claim_id_value: str, db: Session = Depends(db_session)):
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
    return serialize(c)
