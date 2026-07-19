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

# ── SARS IN47 Wear & Tear Table (Section 11(e) of the Income Tax Act) ─────────
# Source: SARS Interpretation Note 47 (IN47) and related practice notes.
# "years" = prescribed write-off period (straight-line, full cost, no residual).
# SARS does NOT allow residual values for tax purposes — full cost is written off.
SARS_WEAR_TEAR = {
    # ── Office & IT ──────────────────────────────────────────────────────────
    "Computers — desktops / laptops":          {"years": 3,  "section": "11(e)"},
    "Smartphones / Tablets":                   {"years": 2,  "section": "11(e)"},
    "Printers / Photocopiers / Scanners":      {"years": 3,  "section": "11(e)"},
    "Fax machines":                            {"years": 3,  "section": "11(e)"},
    "Software — purchased (off-the-shelf)":    {"years": 2,  "section": "11(e)"},
    "Software — custom developed":             {"years": 3,  "section": "11(e)"},
    "Office equipment (general)":              {"years": 5,  "section": "11(e)"},
    "Televisions / Display screens":           {"years": 6,  "section": "11(e)"},
    # ── Furniture & Fittings ─────────────────────────────────────────────────
    "Furniture and fittings":                  {"years": 6,  "section": "11(e)"},
    "Carpets / Floor coverings":               {"years": 6,  "section": "11(e)"},
    "Air conditioners (portable)":             {"years": 5,  "section": "11(e)"},
    # ── Vehicles ─────────────────────────────────────────────────────────────
    "Motor vehicles — passenger":              {"years": 5,  "section": "11(e)"},
    "Motor vehicles — light delivery (≤3.5t)": {"years": 4,  "section": "11(e)"},
    "Trucks / Heavy vehicles (>3.5t)":         {"years": 4,  "section": "11(e)"},
    "Motorcycles":                             {"years": 4,  "section": "11(e)"},
    "Trailers":                                {"years": 5,  "section": "11(e)"},
    "Forklifts":                               {"years": 4,  "section": "11(e)"},
    "Aircraft (light)":                        {"years": 4,  "section": "11(e)"},
    # ── Plant & Machinery ────────────────────────────────────────────────────
    "Machinery — general":                     {"years": 5,  "section": "11(e)"},
    "Manufacturing plant (general)":           {"years": 5,  "section": "11(e)"},
    "Manufacturing plant — new/unused (s12C)": {"years": 4,  "section": "12C",
                                                "note": "40% yr1, 20% yrs 2-4"},
    "Tools — hand tools":                      {"years": 3,  "section": "11(e)"},
    "Tools — power tools":                     {"years": 3,  "section": "11(e)"},
    # ── Buildings ────────────────────────────────────────────────────────────
    "Commercial buildings (s13quin)":          {"years": 25, "section": "13quin",
                                                "note": "Eligible commercial buildings only"},
    "Industrial / Manufacturing buildings":    {"years": 10, "section": "13",
                                                "note": "Used in process of manufacture"},
    "Hotel buildings":                         {"years": 20, "section": "13bis"},
    "Residential rental property":             {"years": 25, "section": "13sex",
                                                "note": "New/unused residential units only"},
    # ── Renewable Energy ─────────────────────────────────────────────────────
    "Solar PV panels (≤1 MW, s12BA)":          {"years": 1,  "section": "12BA",
                                                "note": "125% first-year deduction — energy cost only"},
    "Wind energy equipment":                   {"years": 1,  "section": "12B",
                                                "note": "100% first-year deduction"},
    "Biomass / Small hydro equipment":         {"years": 3,  "section": "12B"},
    # ── Other ────────────────────────────────────────────────────────────────
    "Bicycles":                                {"years": 4,  "section": "11(e)"},
    "Cash registers / POS systems":            {"years": 3,  "section": "11(e)"},
    "Security systems / CCTV":                 {"years": 5,  "section": "11(e)"},
    "Telephone systems (PABX / VoIP)":         {"years": 5,  "section": "11(e)"},
    "Medical / Dental equipment":              {"years": 5,  "section": "11(e)"},
    "Kitchen equipment (commercial)":          {"years": 6,  "section": "11(e)"},
    "Gym / Fitness equipment":                 {"years": 5,  "section": "11(e)"},
}

# SA corporate income tax rate (27% from 1 April 2023)
SA_CIT_RATE = 0.27


def _calc_tax_base(asset, now: datetime = None) -> dict:
    """
    Compute SARS tax base and deferred tax for a fixed asset.

    UNIFIED with the AFS deferred-tax helper (audit fix 2026-07-19): the SARS
    wear-and-tear rate now comes from financial_statements._wt_rate_pct — the
    single rate resolver used by the Annual Financial Statements — with
    priority: explicit wear_and_tear_rate → SARS IN47 category → category-name
    heuristic → None. Previously this register only handled sars_category,
    silently excluding assets with an explicit rate override, and could
    disagree with the AFS Note 9 figures.

    Tax base  = cost − cumulative SARS allowance claimed to date (floored at 0).
    Accounting carrying value is taken from asset.cost - accumulated_depreciation (IAS 16).

    Temporary difference:
      positive (CV > tax base) → Taxable temp diff → Deferred Tax Liability (DTL)
      negative (CV < tax base) → Deductible temp diff → Deferred Tax Asset (DTA)

    Returns None if no wear-and-tear rate is mappable for the asset.
    """
    from financial_statements import _wt_rate_pct  # lazy — avoids import cycle
    rate = _wt_rate_pct(asset)
    if rate is None or rate <= 0:
        return None

    if now is None:
        now = datetime.utcnow()

    cost       = asset.cost
    sars_info  = SARS_WEAR_TEAR.get(asset.sars_category) if asset.sars_category else None
    sars_years = round(100.0 / rate, 2)

    # Rate source disclosure (mirrors _wt_rate_pct priority)
    if asset.wear_and_tear_rate:
        rate_source = "explicit_rate"
    elif sars_info:
        rate_source = "sars_category"
    else:
        rate_source = "category_heuristic"

    monthly_allowance = round(cost * (rate / 100.0) / 12.0, 2)
    months_elapsed    = max(0, (now.year  - asset.purchase_date.year) * 12
                              + (now.month - asset.purchase_date.month))
    accumulated_allowance = round(min(months_elapsed * monthly_allowance, cost), 2)

    tax_base       = round(max(0.0, cost - accumulated_allowance), 2)
    # IAS 16 carrying value (ignoring residual cap — tax base comparison uses gross)
    carrying_value = round(cost - asset.accumulated_depreciation, 2)
    temp_diff      = round(carrying_value - tax_base, 2)
    deferred_tax   = round(temp_diff * SA_CIT_RATE, 2)

    if temp_diff > 0.01:
        dt_type = "DTL"   # taxable — will pay more tax in future
    elif temp_diff < -0.01:
        dt_type = "DTA"   # deductible — will save tax in future
    else:
        dt_type = "Nil"

    return {
        "sars_category":             asset.sars_category,
        "sars_years":                sars_years,
        "wt_rate_pct":               round(rate, 2),
        "rate_source":               rate_source,
        "section":                   sars_info["section"] if sars_info else "11(e)",
        "note":                      sars_info.get("note") if sars_info else None,
        "monthly_tax_allowance":     monthly_allowance,
        "accumulated_allowance":     accumulated_allowance,
        "tax_base":                  tax_base,
        "accounting_carrying_value": carrying_value,
        "temporary_difference":      temp_diff,
        "deferred_tax":              deferred_tax,
        "deferred_tax_type":         dt_type,
        "cit_rate":                  SA_CIT_RATE,
    }


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
    sars_category:        Optional[str]   = None             # SARS IN47 wear & tear category
    post_journal:         bool            = True             # post acquisition journal entry


class AssetUpdate(BaseModel):
    asset_name:           Optional[str]   = None
    description:          Optional[str]   = None
    location:             Optional[str]   = None
    residual_value:       Optional[float] = None
    useful_life_months:   Optional[int]   = None
    depreciation_method:  Optional[str]   = None
    depreciation_rate:    Optional[float] = None
    sars_category:        Optional[str]   = None


class DisposalData(BaseModel):
    disposal_date:        str             # YYYY-MM-DD
    disposal_proceeds:    float           = 0.0
    disposal_notes:       Optional[str]   = None
    is_write_off:         bool            = False  # True = write-off with no proceeds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_asset_number(company_id: int, db: Session) -> str:
    # Max-id seeded with collision check (scale fix 2026-07-03): count()+1
    # produced duplicate numbers after any asset was deleted.
    from sqlalchemy import func as _func
    last = db.query(_func.max(FixedAsset.id)).filter(FixedAsset.company_id == company_id).scalar() or 0
    existing = {
        row[0] for row in
        db.query(FixedAsset.asset_number).filter(FixedAsset.company_id == company_id).all()
    }
    n = last + 1
    candidate = f"FA-{str(n).zfill(3)}"
    while candidate in existing:
        n += 1
        candidate = f"FA-{str(n).zfill(3)}"
    return candidate


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


def _asset_to_dict(a) -> dict:
    carrying     = round(max(a.residual_value, a.cost - a.accumulated_depreciation), 2)
    monthly_depr = _calc_monthly_depreciation(a) if a.status == "active" else 0.0
    tax_info     = _calc_tax_base(a) if a.status == "active" else None
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
        # SARS / deferred tax fields (None if no SARS category assigned)
        "sars_category":          a.sars_category,
        "tax":                    tax_info,
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

    # Validate SARS category if provided
    if data.sars_category and data.sars_category not in SARS_WEAR_TEAR:
        raise HTTPException(400, f"Unknown SARS category: '{data.sars_category}'. Use GET /fixed-assets/wear-tear-table for valid options.")

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
        sars_category       = data.sars_category or None,
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
    if data.sars_category       is not None:
        if data.sars_category not in SARS_WEAR_TEAR and data.sars_category != "":
            raise HTTPException(400, f"Unknown SARS category: '{data.sars_category}'")
        asset.sars_category = data.sars_category or None

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


@router.get("/wear-tear-table")
async def get_wear_tear_table():
    """
    Return the full SARS IN47 wear & tear table.
    No auth required — reference data only.
    """
    return {
        "source":   "SARS Interpretation Note 47 (IN47)",
        "act":      "Income Tax Act No. 58 of 1962",
        "cit_rate": SA_CIT_RATE,
        "note":     "SARS does not allow residual values. Full cost is deducted over the prescribed period. "
                    "This table is for guidance — always confirm with your tax advisor.",
        "categories": [
            {
                "name":          cat,
                "years":         info["years"],
                "section":       info["section"],
                "monthly_rate":  round(1 / (info["years"] * 12), 6) if info["years"] > 0 else 1.0,
                "note":          info.get("note"),
            }
            for cat, info in SARS_WEAR_TEAR.items()
        ],
    }


@router.get("/deferred-tax")
async def get_deferred_tax(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return deferred tax schedule for all active assets with a mappable SARS
    wear-and-tear rate (explicit rate, IN47 category, or category-name
    heuristic — unified with the AFS helper, audit fix 2026-07-19).

    Each row shows:
      - Accounting carrying value (IAS 16)
      - SARS tax base (cost less accumulated wear & tear allowance)
      - Temporary difference
      - Deferred tax at 27%: DTL (liability) or DTA (asset)

    Summary totals are broken out as gross DTL, gross DTA, and net deferred tax position.
    """
    assets = (
        db.query(FixedAsset)
        .filter(
            FixedAsset.company_id == current_user.company_id,
            FixedAsset.status     == "active",
        )
        .all()
    )

    rows         = []
    total_dtl    = 0.0
    total_dta    = 0.0

    for a in assets:
        tax = _calc_tax_base(a)
        if tax is None:
            continue
        row = {
            "asset_id":     a.id,
            "asset_number": a.asset_number,
            "asset_name":   a.asset_name,
            "category":     a.category,
            "cost":         round(a.cost, 2),
            **tax,
        }
        rows.append(row)
        if tax["deferred_tax_type"] == "DTL":
            total_dtl += tax["deferred_tax"]
        elif tax["deferred_tax_type"] == "DTA":
            total_dta += abs(tax["deferred_tax"])

    net = round(total_dtl - total_dta, 2)

    return {
        "as_at":           datetime.utcnow().strftime("%Y-%m-%d"),
        "cit_rate":        SA_CIT_RATE,
        "assets":          rows,
        "summary": {
            "gross_dtl":   round(total_dtl, 2),   # total Deferred Tax Liabilities
            "gross_dta":   round(total_dta, 2),   # total Deferred Tax Assets
            "net_position": net,                   # positive = net DTL; negative = net DTA
            "net_type":    "DTL" if net > 0.01 else ("DTA" if net < -0.01 else "Nil"),
        },
        # Active assets with NO mappable rate at all (excluded from the schedule;
        # their tax base is deemed equal to carrying value → zero difference)
        "unclassified_count": len(assets) - len(rows),
    }


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
