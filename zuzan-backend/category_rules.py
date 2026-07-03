"""
category_rules.py — Learned categorisation rules for bank CSV imports.

Endpoints (all scoped to current_user.company_id):
  GET  /category-rules/          → list all rules for this company
  POST /category-rules/          → upsert a rule (keyword + txn_type is the key)
  DELETE /category-rules/{id}    → delete a specific rule
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, CategoryRule
from auth import get_current_user

router = APIRouter(prefix="/category-rules", tags=["category_rules"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class CategoryRuleOut(BaseModel):
    id: int
    keyword: str
    category: str
    txn_type: str
    match_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CategoryRuleIn(BaseModel):
    keyword: str
    category: str
    txn_type: Optional[str] = "any"   # "credit" | "debit" | "any"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[CategoryRuleOut])
def list_rules(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all category rules for this company, ordered by match_count desc."""
    cid = current_user.company_id
    return (
        db.query(CategoryRule)
        .filter(CategoryRule.company_id == cid)
        .order_by(CategoryRule.match_count.desc(), CategoryRule.keyword)
        .all()
    )


@router.post("/", response_model=CategoryRuleOut)
def upsert_rule(
    body: CategoryRuleIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Upsert a categorisation rule.
    If a rule with the same (company_id, keyword, txn_type) already exists,
    update its category and increment match_count; otherwise create it.
    """
    cid = current_user.company_id
    keyword = body.keyword.lower().strip()[:100]
    txn_type = body.txn_type or "any"

    existing = (
        db.query(CategoryRule)
        .filter(
            CategoryRule.company_id == cid,
            CategoryRule.keyword == keyword,
            CategoryRule.txn_type == txn_type,
        )
        .first()
    )

    if existing:
        existing.category = body.category
        existing.match_count += 1
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    else:
        rule = CategoryRule(
            company_id=cid,
            keyword=keyword,
            category=body.category,
            txn_type=txn_type,
            match_count=1,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a category rule by id (must belong to current company)."""
    cid = current_user.company_id
    rule = (
        db.query(CategoryRule)
        .filter(CategoryRule.id == rule_id, CategoryRule.company_id == cid)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"ok": True}
