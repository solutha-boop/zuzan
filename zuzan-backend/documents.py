"""
Document Repository — company file vault.
Stores files as base64 in the DB (no filesystem dependency, works on Render free tier).
Max file size: 10 MB.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional
import base64

from database import get_db, CompanyDocument
from auth import require_role

router = APIRouter()

MAX_BYTES = 10 * 1024 * 1024   # 10 MB hard limit

ALLOWED_CATEGORIES = {
    "CIPC & Registration",
    "Tax Documents",
    "Contracts",
    "Annual Financial Statements",
    "Payroll Records",
    "Insurance",
    "Banking",
    "General",
}


# ── LIST ─────────────────────────────────────────────────────────────────────

@router.get("/")
def list_documents(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("owner", "admin", "accountant")),
):
    q = db.query(CompanyDocument).filter(
        CompanyDocument.company_id == current_user.company_id
    )
    if category:
        q = q.filter(CompanyDocument.category == category)
    docs = q.order_by(CompanyDocument.uploaded_at.desc()).all()
    return [
        {
            "id":          d.id,
            "name":        d.name,
            "category":    d.category,
            "description": d.description,
            "file_name":   d.file_name,
            "file_type":   d.file_type,
            "file_size":   d.file_size,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in docs
    ]


# ── UPLOAD ───────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_document(
    name:        str = Form(...),
    category:    str = Form("General"),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_role("owner", "admin", "accountant")),
):
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(400, f"File too large — maximum size is 10 MB")

    if not name.strip():
        name = file.filename or "Untitled"

    if category not in ALLOWED_CATEGORIES:
        category = "General"

    doc = CompanyDocument(
        company_id  = current_user.company_id,
        uploaded_by = current_user.id,
        name        = name.strip(),
        category    = category,
        description = (description or "").strip(),
        file_name   = file.filename or "file",
        file_type   = file.content_type or "application/octet-stream",
        file_size   = len(content),
        file_data   = base64.b64encode(content).decode("ascii"),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {
        "id":      doc.id,
        "name":    doc.name,
        "message": "Document uploaded successfully",
    }


# ── DOWNLOAD ─────────────────────────────────────────────────────────────────

@router.get("/{doc_id}/download")
def download_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("owner", "admin", "accountant")),
):
    doc = db.query(CompanyDocument).filter(
        CompanyDocument.id == doc_id,
        CompanyDocument.company_id == current_user.company_id,
    ).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    data = base64.b64decode(doc.file_data)
    # Encode filename for Content-Disposition
    safe_name = doc.file_name.replace('"', '_')
    return Response(
        content=data,
        media_type=doc.file_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# ── DELETE ───────────────────────────────────────────────────────────────────

@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("owner", "admin")),
):
    doc = db.query(CompanyDocument).filter(
        CompanyDocument.id == doc_id,
        CompanyDocument.company_id == current_user.company_id,
    ).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    db.delete(doc)
    db.commit()
    return {"message": "Document deleted"}
