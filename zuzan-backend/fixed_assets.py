"""
ZuZan Fixed Asset Module — IAS 16 / IFRS for SMEs Section 17
Supports: cost model, straight-line and diminishing balance depreciation,
          full disposal workflow with gain/loss, auto monthly depreciation.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date as date_type
import logging

from database import get_db, FixedAsset, DepreciationEntry, Company
from auth import get_current_user, User

logger = logging.getLogger("zuzan.fixed_assets")
router = APIRouter()

# ── Asset categories ──────────────────────────────────────────────────────────
ASSET_CATEGORIES = [
    "Land & Buildings",
    "Plant & Machinery",
    "Motor Vehicles",
    "Furniture & Fittings",
    "Computer Equipment",
    "Office Equipment",
    "Leasehold Improvements",
    "Other Fixed Assets",
]

# Default useful lives by category (months) for guidance
DEFAULT_USEFUL_LIVES = {
    "Land & Buildings":        480,   # 40 years
    "Plant & Machinery":       120,   # 10 years
    "Motor Vehicles":           60,   # 5 years
    "Furniture & Fittings":    120,   # 10 years
    "Computer Equipment":       36,   # 3 years
    "Office Equipment":         60,   # 5 years
    "Leasehold Improvements":  120,   # 10 years (or lease term)
    "Other Fixed Assets":       60,
}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AssetCreate(BaseModel):
    asset_name:           str
    category:             str
    description:          Optional[str]   = None
    location:             Optional[str]   = None
    purchase_date:        str             # YYYY-MM-DD
    cost:                 float
    residual_value:       float           = 0.0
    useful_life_months:   int
    depreciation_method:  str             = "straight_line"  # straight_line | diminishing_balance
    depreciation_rate:    Optional[float] = None             # required for diminishing_balance
    post_journal:         bool            = True             # post acquisition journal entry


class AssetUpdate(BaseModel):
    asset_name:           Optional[str]   = None
    description:          Optional[str]   = None
    location:             Optional[str]   = None
    residual_value:       Optional[float] = None
    useful_life_months:   Optional[int]   = None
    depreciation_method:  Optional[str]   = None
    depreciation_rate:    Optional[float] = None


class DisposalData(BaseModel):
    disposal_date:        str             # YYYY-MM-DD
    disposal_proceeds:    float           = 0.0
    disposal_notes:       Optional[str]   = None
    is_write_off:         bool            = False  # True = write-off with no proceeds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_asset_number(company_id: int, db: Session) -> str:
    count = db.query(FixedAsset).filter(FixedAsset.company_id == company_id).count()
    return f"FA-{str(count + 1).zfill(3)}"


def _calc_monthly_depreciation(asset: FixedAsset) -> float:
    """
    Calculate the depreciation amount for one month.
    Straight-line: (cost - residual) / useful_life_months
    Diminishing balance: carrying_value * (rate / 12)
    Returns 0 if asset is fully depreciated down to residual value.
    """
    carrying = asset.cost - asset.accumulated_depreciation
    if carrying <= asset.residual_value:
        return 0.0

    if asset.depreciation_method == "diminishing_balance":
        rate = asset.depreciation_rate or 0.20  # default 20% p.a.
        monthly = carrying * (rate / 12)
    else:  # straight_line (default)
        depreciable = asset.cost - asset.residual_value
        monthly = depreciable / max(1, asset.useful_life_months)

    # Cap at remaining depreciable amount
    remaining = carrying - asset.residual_value
    return round(min(monthly, remaining), 2)


def _asset_to_dict(a: FixedAsset) -> dict:
    carrying = round(max(a.residual_value, a.cost - a.accumulated_depreciation), 2)
    monthly_depr = _calc_monthly_depreciation(a) if a.status == "active" else 0.0
    return {
        "id":                     a.id,
        "asset_number":           a.asset_number,
        "asset_name":             a.asset_name,
        "category":               a.category,
        "description":            a.description,
        "location":               a.location,
        "purchase_date":          a.purchase_date.strftime("%Y-%m-%d"),
        "cost":                   round(a.cost, 2),
        "residual_value":         round(a.residual_value, 2),
        "useful_life_months":     a.useful_life_months,
        "depreciation_method":    a.depreciation_method,
        "depreciation_rate":      a.depreciation_rate,
        "accumulated_depreciation": round(a.accumulated_depreciation, 2),
        "carrying_value":         carrying,
        "monthly_depreciation":   monthly_depr,
        "status":                 a.status,
        "last_depreciation_date": a.last_depreciation_date.strftime("%Y-%m-%d") if a.last_depreciation_date else None,
        "disposal_date":          a.disposal_date.strftime("%Y-%m-%d") if a.disposal_date else None,
        "disposal_proceeds":      a.disposal_proceeds,
        "disposal_gain_loss":     a.disposal_gain_loss,
        "disposal_notes":         a.disposal_notes,
        "created_at":             a.created_at.isoformat() if a.created_at else None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_assets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all assets for the company with computed carrying values."""
    assets = (
        db.query(FixedAsset)
        .filter(FixedAsset.company_id == current_user.company_id)
        .order_by(FixedAsset.purchase_date.desc())
        .all()
    )
    return [_asset_to_dict(a) for a in assets]


@router.post("/")
async def create_asset(
    data: AssetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a new fixed asset to the register."""
    cid = current_user.company_id
    if data.category not in ASSET_CATEGORIES:
        # Allow custom category — just warn in log
        logger.info(f"Non-standard asset category: {data.category}")
    if data.depreciation_method == "diminishing_balance" and not data.depreciation_rate:
        raise HTTPException(400, "depreciation_rate is required for diminishing balance method (e.g. 0.20 = 20% p.a.)")

    asset = FixedAsset(
        company_id          = cid,
        asset_number        = _next_asset_number(cid, db),
        asset_name          = data.asset_name,
        category            = data.category,
        description         = data.description,
        location            = data.location,
        purchase_date       = datetime.strptime(data.purchase_date, "%Y-%m-%d"),
        cost                = data.cost,
        residual_value      = data.residual_value,
        useful_life_months  = data.useful_life_months,
        depreciation_method = data.depreciation_method,
        depreciation_rate   = data.depreciation_rate,
    )
    db.add(asset)
    db.flush()  # get asset.id before journal post

    # Post acquisition journal entry
    if data.post_journal:
        try:
            import journal as journal_engine
            journal_engine.init_accounts(cid, db)
            journal_engine.post_asset_acquisition(asset, db)
        except Exception as je:
            logger.warning(f"Asset acquisition journal failed (non-fatal): {je}")

    db.commit()
    db.refresh(asset)
    return _asset_to_dict(asset)


@router.put("/{asset_id}")
async def update_asset(
    asset_id: int,
    data: AssetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update non-financial details of an active asset."""
    asset = db.query(FixedAsset).filter(
        FixedAsset.id == asset_id,
        FixedAsset.company_id == current_user.company_id,
    ).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    if asset.status != "active":
        raise HTTPException(400, "Only active assets can be edited")

    if data.asset_name          is not None: asset.asset_name          = data.asset_name
    if data.description         is not None: asset.description         = data.description
    if data.location            is not None: asset.location            = data.location
    if data.residual_value      is not None: asset.residual_value      = data.residual_value
    if data.useful_life_months  is not None: asset.useful_life_months  = data.useful_life_months
    if data.depreciation_method is not None: asset.depreciation_method = data.depreciation_method
    if data.depreciation_rate   is not None: asset.depreciation_rate   = data.depreciation_rate

    db.commit()
    db.refresh(asset)
    return _asset_to_dict(asset)


@router.post("/{asset_id}/dispose")
async def dispose_asset(
    asset_id: int,
    data: DisposalData,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dispose of or write off an asset (IAS 16.67-72).
    Calculates gain/loss on disposal and posts the derecognition journal entry.
    """
    asset = db.query(FixedAsset).filter(
        FixedAsset.id == asset_id,
        FixedAsset.company_id == current_user.company_id,
    ).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    if asset.status != "active":
        raise HTTPException(400, "Asset is already disposed or written off")

    proceeds       = 0.0 if data.is_write_off else data.disposal_proceeds
    carrying_value = max(0.0, asset.cost - asset.accumulated_depreciation)
    gain_loss      = round(proceeds - carrying_value, 2)

    asset.status          = "written_off" if data.is_write_off else "disposed"
    asset.disposal_date   = datetime.strptime(data.disposal_date, "%Y-%m-%d")
    asset.disposal_proceeds = proceeds
    asset.disposal_gain_loss = gain_loss
    asset.disposal_notes  = data.disposal_notes

    # Post disposal journal entry
    try:
        import journal as journal_engine
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_asset_disposal(asset, proceeds, db)
    except Exception as je:
        logger.warning(f"Asset disposal journal failed: {je}")

    db.commit()
    db.refresh(asset)
    return {
        **_asset_to_dict(asset),
        "gain_loss":     gain_loss,
        "carrying_value_at_disposal": round(carrying_value, 2),
        "message": f"Asset {'written off' if data.is_write_off else 'disposed'}. {'Gain' if gain_loss >= 0 else 'Loss'} on disposal: R{abs(gain_loss):,.2f}",
    }


@router.get("/schedule")
async def depreciation_schedule(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the full depreciation schedule — monthly entries posted to date."""
    entries = (
        db.query(DepreciationEntry)
        .filter(DepreciationEntry.company_id == current_user.company_id)
        .order_by(DepreciationEntry.period.desc(), DepreciationEntry.posted_at.desc())
        .all()
    )
    # Build asset name lookup
    asset_map = {
        a.id: a.asset_name
        for a in db.query(FixedAsset).filter(FixedAsset.company_id == current_user.company_id).all()
    }
    return [
        {
            "id":         e.id,
            "asset_id":   e.asset_id,
            "asset_name": asset_map.get(e.asset_id, "Unknown"),
            "period":     e.period,
            "amount":     round(e.amount, 2),
            "posted_at":  e.posted_at.isoformat() if e.posted_at else None,
        }
        for e in entries
    ]


@router.post("/run-depreciation")
async def run_depreciation_manual(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger monthly depreciation for all active assets (same as payroll auto-run)."""
    n, total = _run_depreciation_internal(current_user.company_id, db)
    return {
        "assets_depreciated": n,
        "total_depreciation":  round(total, 2),
        "period":             datetime.utcnow().strftime("%Y-%m"),
        "message":            f"Depreciation run complete. {n} asset(s) charged, total R{total:,.2f}.",
    }


@router.get("/categories")
async def get_categories():
    """Return available asset categories with default useful lives."""
    return [
        {"category": cat, "default_useful_life_months": DEFAULT_USEFUL_LIVES.get(cat, 60)}
        for cat in ASSET_CATEGORIES
    ]


# ── Internal — called by payroll engine ──────────────────────────────────────

def _run_depreciation_internal(company_id: int, db: Session):
    """
    Run monthly depreciation for all active assets of a company.
    Idempotent — skips assets already depreciated in the current calendar month.
    Returns (assets_depreciated, total_amount).
    """
    now    = datetime.utcnow()
    period = now.strftime("%Y-%m")

    assets = (
        db.query(FixedAsset)
        .filter(FixedAsset.company_id == company_id, FixedAsset.status == "active")
        .all()
    )

    # Collect already-posted periods for this company this month
    already_posted = {
        e.asset_id
        for e in db.query(DepreciationEntry).filter(
            DepreciationEntry.company_id == company_id,
            DepreciationEntry.period     == period,
        ).all()
    }

    import journal as journal_engine
    journal_engine.init_accounts(company_id, db)

    charged_count = 0
    total_amount  = 0.0

    for asset in assets:
        if asset.id in already_posted:
            continue  # idempotent — already done this month

        # Don't depreciate assets purchased after the current period
        if asset.purchase_date.strftime("%Y-%m") > period:
            continue

        amount = _calc_monthly_depreciation(asset)
        if amount <= 0:
            continue  # fully depreciated

        # Update accumulated depreciation
        asset.accumulated_depreciation = round(asset.accumulated_depreciation + amount, 2)
        asset.last_depreciation_date   = now

        # Record depreciation entry
        entry_rec = DepreciationEntry(
            company_id = company_id,
            asset_id   = asset.id,
            period     = period,
            amount     = amount,
        )
        db.add(entry_rec)
        db.flush()

        # Post to double-entry journal
        try:
            journal_engine.post_depreciation(asset, amount, period, db)
        except Exception as je:
            logger.warning(f"Depreciation journal failed for asset {asset.id}: {je}")

        charged_count += 1
        total_amount  += amount

    db.commit()
    logger.info(f"Depreciation run [{period}]: {charged_count} assets, R{total_amount:.2f} total for company {company_id}")
    return charged_count, total_amount
