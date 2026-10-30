"""
ZuZan - Invoices, Expenses, Employees, Companies Routers
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from database import (
    get_db, Invoice, Expense, Employee, Company, Payslip, InvoiceStatus,
    CompanyMembership, CompanyAccount, ServiceItem,
    # clear-data endpoint
    Customer, Supplier, PurchaseOrder, PurchaseOrderItem,
    Quote, CreditNote, RecurringInvoice, Payment,
    JournalEntry, JournalLine, InventoryItem, Budget,
    FixedAsset, DepreciationEntry, LeaveRequest, LeaveBalance,
    EmployeeGarnishee, ClockEvent, CompanyDocument,
    StitchConnection, StitchBankAccount, StitchTransaction,
    SaltEdgeConnection, SaltEdgeBankAccount, SaltEdgeTransaction,
    AbsaConnection, AbsaBankAccount, AbsaTransaction,
    NedbankConnection, NedbankBankAccount, NedbankTransaction,
    InvestecConnection, InvestecBankAccount, InvestecTransaction,
    StandardBankConnection, StandardBankBankAccount, StandardBankTransaction,
)
from auth import get_current_user, require_role, log_action, User
from crypto import encrypt_field, decrypt_field
from passlib.context import CryptContext
import logging
import os
import json
import journal as journal_engine

_pin_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

logger = logging.getLogger("zuzan.routers")

def clean(value, max_len=500):
    """Strip whitespace and enforce max length on text inputs."""
    if value is None: return value
    return str(value).strip()[:max_len]


# ── COMPANIES ─────────────────────────────────────────────────────────────────
router = APIRouter()

class CompanyUpdate(BaseModel):
    name:                   Optional[str] = None
    reg_number:             Optional[str] = None
    vat_number:             Optional[str] = None
    vat_registered:         Optional[bool] = None
    industry:               Optional[str] = None
    address:                Optional[str] = None
    phone:                  Optional[str] = None
    email:                  Optional[str] = None
    bank_name:              Optional[str] = None
    bank_account:           Optional[str] = None
    bank_branch:            Optional[str] = None
    logo_url:               Optional[str] = None
    invoice_header_url:     Optional[str] = None
    invoice_template_html:  Optional[str] = None
    billing_exempt:         Optional[bool] = None
    cipc_registration_date: Optional[str] = None  # ISO date — company incorporation anniversary
    financial_year_end:     Optional[str] = None  # "MM-DD" e.g. "02-28"
    afs_enabled:            Optional[bool] = None
    payroll_enabled:        Optional[bool] = None
    payroll_employees:      Optional[int]  = None
    payfast_merchant_id:    Optional[str] = None
    payfast_merchant_key:   Optional[str] = None
    payfast_passphrase:     Optional[str] = None
    # Plan / billing cycle — user can switch plan at any time; takes effect on
    # next PayFast subscription charge or immediately for trial users.
    plan:                   Optional[str] = None
    billing_cycle:          Optional[str] = None
    # User-initiated subscription transitions only — guarded in update_company.
    # "cancelled" (cancel / auto-renew off) or "active" (undo a cancellation).
    subscription_status:    Optional[str] = None
    # SARS e@syFile fields
    paye_ref:               Optional[str] = None
    sdl_ref:                Optional[str] = None
    uif_ref:                Optional[str] = None
    sic7_code:              Optional[str] = None
    contact_name:           Optional[str] = None


_MASK = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"


def _masked(v):
    """Secrets are never sent back in full: the form shows a mask and the server ignores a mask that comes back unchanged."""
    return (_MASK + v[-2:]) if v and len(v) > 4 else (_MASK if v else "")


def _clean_html(html: str) -> str:
    """Strip active content (scripts, frames, event handlers, javascript: links) from an owner-supplied invoice template."""
    import re as _re
    if not html:
        return html
    html = _re.sub(r"(?is)<\s*(script|iframe|object|embed|applet|meta|link|base|form)\b.*?(<\s*/\s*\1\s*>|$)", "", html)
    html = _re.sub(r"(?is)<\s*(script|iframe|object|embed|applet|meta|link|base|form)\b[^>]*>", "", html)
    html = _re.sub(r"(?is)\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html)
    html = _re.sub(r"(?is)(href|src|xlink:href|action|formaction)\s*=\s*([\"']?)\s*(javascript|vbscript|data:text/html)[^\"'>\s]*", r"\1=\2#", html)
    return html


_SECRET_ROLES = ("owner", "admin", "accountant")


def _company_dict(c: Company, role: str = "owner") -> dict:
    """Return company as dict with bank fields decrypted (secrets masked; bank details only for roles that manage the books)."""
    _full = role in _SECRET_ROLES
    return {
        "id": c.id, "name": c.name, "reg_number": c.reg_number,
        "vat_number": c.vat_number, "vat_registered": c.vat_registered is not False, "industry": c.industry,
        "address": c.address, "phone": c.phone, "email": c.email,
        "bank_name":    decrypt_field(c.bank_name)    if _full else "",
        "bank_account": decrypt_field(c.bank_account) if _full else "",
        "bank_branch":  decrypt_field(c.bank_branch)  if _full else "",
        "logo_url": c.logo_url, "invoice_header_url": c.invoice_header_url,
        "invoice_template_html": c.invoice_template_html or "",
        "billing_exempt": bool(c.billing_exempt),
        "plan": c.plan, "billing_cycle": c.billing_cycle,
        "subscription_status": c.subscription_status.value if hasattr(c.subscription_status, "value") else (c.subscription_status or "trial"),
        "trial_ends": c.trial_ends.isoformat() if c.trial_ends else None,
        "payroll_enabled": c.payroll_enabled, "payroll_employees": c.payroll_employees,
        "afs_enabled": c.afs_enabled,
        "payfast_merchant_id":  _masked(decrypt_field(c.payfast_merchant_id))  if (_full and c.payfast_merchant_id)  else "",
        "payfast_merchant_key": _masked(decrypt_field(c.payfast_merchant_key)) if (_full and c.payfast_merchant_key) else "",
        "payfast_passphrase":   _masked(decrypt_field(c.payfast_passphrase))   if (_full and c.payfast_passphrase)   else "",
        "cipc_registration_date": c.cipc_registration_date.isoformat() if c.cipc_registration_date else None,
        "financial_year_end":     c.financial_year_end or None,
        "paye_ref": c.paye_ref or "",
        "sdl_ref":  c.sdl_ref  or "",
        "uif_ref":  c.uif_ref  or "",
        "sic7_code":     c.sic7_code     or "",
        "contact_name":  c.contact_name  or "",
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/me")
async def get_company(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return _company_dict(company, current_user.role)


@router.put("/me")
async def update_company(data: CompanyUpdate, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    for field, value in data.dict(exclude_none=True).items():
        # Only ZuZan itself (admin console / PayFast confirmation) may grant partner status or paid add-ons.
        # These used to be writable here, so any owner could send {"billing_exempt": true} and stop paying.
        if field in ("billing_exempt", "afs_enabled"):
            continue
        if isinstance(value, str) and value.startswith(_MASK):
            continue                                   # an unchanged masked secret coming back from the form
        if field in ("logo_url", "invoice_header_url") and value and not (value.startswith(("http://", "https://", "data:image/"))):
            raise HTTPException(status_code=400, detail=f"{field} must be an http(s) link or an image.")
        if field == "invoice_template_html":
            value = _clean_html(value)
        if field in ("bank_name", "bank_account", "bank_branch",
                     "payfast_merchant_id", "payfast_merchant_key", "payfast_passphrase"):
            setattr(company, field, encrypt_field(value))
        elif field == "cipc_registration_date":
            setattr(company, field, datetime.fromisoformat(value) if value else None)
        elif field == "plan":
            valid_plans = {"starter", "professional", "business"}
            if value not in valid_plans:
                raise HTTPException(status_code=400, detail=f"Invalid plan '{value}'. Must be one of: {', '.join(sorted(valid_plans))}")
            company.plan = value
        elif field == "billing_cycle":
            if value not in ("monthly", "annual"):
                raise HTTPException(status_code=400, detail="billing_cycle must be 'monthly' or 'annual'")
            company.billing_cycle = value
        elif field == "subscription_status":
            # Launch fix 2026-07-14: this field was previously ignored (not in
            # CompanyUpdate), so "Cancel subscription" silently no-oped while the
            # UI showed success. Only user-initiated transitions are allowed here;
            # activation from trial/expired must come through the PayFast ITN
            # handler (billing.payfast_notify) after real payment.
            from database import SubscriptionStatus, SubscriptionPayment
            cur = company.subscription_status.value if hasattr(company.subscription_status, "value") else str(company.subscription_status)
            if value == cur:
                pass  # idempotent
            elif value == "cancelled" and cur in ("trial", "active"):
                company.subscription_status = SubscriptionStatus.cancelled
            elif value == "active" and cur == "cancelled":
                # Undo cancellation — restore what the company is entitled to:
                # active if a successful PayFast payment covers the current
                # period (billing.payfast_notify logs these), otherwise back to
                # trial if the trial hasn't lapsed, otherwise expired.
                has_paid = db.query(SubscriptionPayment).filter(
                    SubscriptionPayment.company_id == company.id,
                    SubscriptionPayment.status == "success",
                    SubscriptionPayment.period_end > datetime.utcnow(),
                ).count() > 0
                if has_paid:
                    company.subscription_status = SubscriptionStatus.active
                elif company.trial_ends and company.trial_ends > datetime.utcnow():
                    company.subscription_status = SubscriptionStatus.trial
                else:
                    company.subscription_status = SubscriptionStatus.expired
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot change subscription from '{cur}' to '{value}'. Use the Subscribe flow to activate.",
                )
        else:
            setattr(company, field, value)
    db.commit()
    return _company_dict(company, current_user.role)


from security import Throttle as _Throttle
_pin_fail = _Throttle(5, 900)          # 5 wrong payroll PINs per user, then 15 minutes locked


class PayrollPinSet(BaseModel):
    pin: str  # 4–8 digit PIN

class PayrollPinVerify(BaseModel):
    pin: str

@router.put("/payroll-pin")
async def set_payroll_pin(data: PayrollPinSet, current_user: User = Depends(require_role("owner")), db: Session = Depends(get_db)):
    if not data.pin.isdigit() or not (4 <= len(data.pin) <= 8):
        raise HTTPException(status_code=400, detail="PIN must be 4–8 digits.")
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company.payroll_pin_hash = _pin_ctx.hash(data.pin)
    db.commit()
    return {"status": "ok", "message": "Payroll PIN updated."}

@router.post("/verify-payroll-pin")
async def verify_payroll_pin(data: PayrollPinVerify, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company.payroll_pin_hash:
        return {"valid": True, "pin_set": False}  # No PIN configured — allow access
    _k = f"pin|{company.id}|{current_user.id}"
    if _pin_fail.blocked(_k):
        raise HTTPException(status_code=429, detail="Too many wrong PINs. Try again in 15 minutes.")
    valid = _pin_ctx.verify(data.pin, company.payroll_pin_hash)
    if valid:
        _pin_fail.clear(_k)
    else:
        _pin_fail.hit(_k)
    return {"valid": valid, "pin_set": True}

@router.get("/payroll-pin-status")
async def payroll_pin_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    return {"pin_set": bool(company.payroll_pin_hash)}


# ── CLEAR TRIAL DATA ──────────────────────────────────────────────────────────

_CLEARABLE = {"sales", "expenses", "customers", "suppliers", "employees",
              "inventory", "banking", "budgets_assets", "documents"}

class ClearDataRequest(BaseModel):
    categories: List[str]
    confirm: bool = False  # must be True to proceed (safety gate)

def _del(db: Session, Model, company_id: int):
    """Delete all rows for company_id in one bulk query (synchronize_session=False)."""
    db.query(Model).filter(Model.company_id == company_id).delete(synchronize_session=False)

# Journal `source` values each category posts under (see journal.py's
# post_invoice_raised/post_invoice_paid/post_invoice_cogs, post_expense/
# post_expense_paid, post_payroll, journal.post_bank_income,
# post_po_received/post_po_paid, post_asset_acquisition/post_depreciation/
# post_asset_disposal, post_stock_adjustment). A reversal of a source-X entry
# is posted as "X_reversal" (journal.reverse_journal_entries), so both are
# cleared together. Every category whose records can post to the journal
# must be listed here — omitting one leaves an orphaned journal balance
# with no supporting sub-ledger rows once that category is cleared (audit
# finding, reports_debtors_creditors_2026-09-27.md action item 1).
_CATEGORY_JOURNAL_SOURCES = {
    "sales":          ["invoice", "invoice_payment", "invoice_cogs", "credit_note"],
    "expenses":       ["expense", "expense_payment"],
    "employees":      ["payroll"],
    "banking":        ["bank_import_income"],
    "suppliers":      ["purchase_order", "po_payment"],
    "budgets_assets": ["fixed_asset", "depreciation", "asset_disposal"],
    "inventory":      ["stock_adjustment"],
    # "customers" and "documents" own no journal source — nothing to clear.
}

def _journal_sources_for_categories(cats) -> set:
    """Journal sources to purge for the selected clear-data categories.
    CSV-imported journal lines (source="import") are shared between invoice,
    expense and journal (equity/opening-balance) imports, so they are only
    purged when BOTH "sales" and "expenses" are cleared — otherwise clearing
    one category would silently erase the other's imported balances."""
    cats = set(cats)
    sources = set()
    for cat in cats:
        sources.update(_CATEGORY_JOURNAL_SOURCES.get(cat, []))
    if {"sales", "expenses"} <= cats:
        sources.add("import")
    return sources

def _clear_journal_for_sources(db: Session, company_id: int, sources: set):
    """Delete JournalLines then JournalEntries for exactly these `source`
    values (plus each one's "<source>_reversal" counterpart) — scoped by
    source, never a blanket company-wide wipe, so clearing one category can
    never erase another category's journal postings."""
    if not sources:
        return
    all_sources = set(sources) | {f"{s}_reversal" for s in sources}
    entry_ids = [r[0] for r in db.query(JournalEntry.id).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source.in_(all_sources),
    ).all()]
    if entry_ids:
        db.query(JournalLine).filter(
            JournalLine.entry_id.in_(entry_ids)
        ).delete(synchronize_session=False)
        db.query(JournalEntry).filter(
            JournalEntry.id.in_(entry_ids)
        ).delete(synchronize_session=False)

@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    """Cancel the company's PayFast subscription and mark as cancelled in DB."""
    from billing import cancel_payfast_subscription
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    cur = company.subscription_status.value if hasattr(company.subscription_status, "value") else str(company.subscription_status)
    if cur not in ("trial", "active"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel a subscription with status '{cur}'.")
    try:
        result = cancel_payfast_subscription(company, db)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True, "message": "Subscription cancelled. You retain access until the end of your current billing period."}


@router.post("/clear-data")
async def clear_company_data(
    req: ClearDataRequest,
    current_user: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    """Selectively wipe company data — typically used before going live from trial.

    Pass {"categories": [...], "confirm": true} to proceed.
    Valid categories: sales, expenses, customers, suppliers, employees,
                      inventory, banking, budgets_assets, documents.
    Each category's own journal postings (invoices, expenses, payroll, bank
    income, purchase orders, fixed-asset/depreciation, stock adjustments) are
    cleared alongside it — see _CATEGORY_JOURNAL_SOURCES.
    """
    invalid = set(req.categories) - _CLEARABLE
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown categories: {sorted(invalid)}")
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true — this action is irreversible.")
    if not req.categories:
        return {"cleared": [], "message": "Nothing to clear."}

    cid = current_user.company_id
    cats = set(req.categories)

    # ── Journals: clear exactly the postings owned by the selected categories ──
    # (never a blanket company-wide wipe — see _clear_journal_for_sources)
    journal_sources = _journal_sources_for_categories(cats)
    _clear_journal_for_sources(db, cid, journal_sources)

    # ── Sales ─────────────────────────────────────────────────────────────────
    if "sales" in cats:
        _del(db, CreditNote,        cid)   # FK → invoices — delete before invoices
        _del(db, RecurringInvoice,  cid)
        _del(db, Quote,             cid)
        _del(db, Invoice,           cid)

    # ── Expenses ──────────────────────────────────────────────────────────────
    if "expenses" in cats:
        _del(db, Expense, cid)

    # ── Customers ─────────────────────────────────────────────────────────────
    if "customers" in cats:
        _del(db, Customer, cid)

    # ── Suppliers & Purchase Orders ───────────────────────────────────────────
    if "suppliers" in cats:
        # PurchaseOrderItems → PurchaseOrders → Suppliers
        po_ids = [r[0] for r in db.query(PurchaseOrder.id).filter(
            PurchaseOrder.company_id == cid
        ).all()]
        if po_ids:
            db.query(PurchaseOrderItem).filter(
                PurchaseOrderItem.purchase_order_id.in_(po_ids)
            ).delete(synchronize_session=False)
        _del(db, PurchaseOrder, cid)
        _del(db, Supplier,      cid)

    # ── Employees & Payroll ───────────────────────────────────────────────────
    if "employees" in cats:
        emp_ids = [r[0] for r in db.query(Employee.id).filter(
            Employee.company_id == cid
        ).all()]
        if emp_ids:
            db.query(EmployeeGarnishee).filter(
                EmployeeGarnishee.employee_id.in_(emp_ids)
            ).delete(synchronize_session=False)
            db.query(LeaveRequest).filter(
                LeaveRequest.employee_id.in_(emp_ids)
            ).delete(synchronize_session=False)
            db.query(LeaveBalance).filter(
                LeaveBalance.employee_id.in_(emp_ids)
            ).delete(synchronize_session=False)
            db.query(ClockEvent).filter(
                ClockEvent.employee_id.in_(emp_ids)
            ).delete(synchronize_session=False)
        _del(db, Payslip,  cid)
        _del(db, Employee, cid)

    # ── Inventory ─────────────────────────────────────────────────────────────
    if "inventory" in cats:
        _del(db, InventoryItem, cid)

    # ── Banking (transactions + accounts + connections for all providers) ──────
    if "banking" in cats:
        for TxModel, AccModel, ConnModel in [
            (StitchTransaction,       StitchBankAccount,       StitchConnection),
            (SaltEdgeTransaction,     SaltEdgeBankAccount,     SaltEdgeConnection),
            (AbsaTransaction,         AbsaBankAccount,         AbsaConnection),
            (NedbankTransaction,      NedbankBankAccount,      NedbankConnection),
            (InvestecTransaction,     InvestecBankAccount,     InvestecConnection),
            (StandardBankTransaction, StandardBankBankAccount, StandardBankConnection),
        ]:
            _del(db, TxModel,   cid)
            _del(db, AccModel,  cid)
            _del(db, ConnModel, cid)

    # ── Budgets & Fixed Assets ────────────────────────────────────────────────
    if "budgets_assets" in cats:
        asset_ids = [r[0] for r in db.query(FixedAsset.id).filter(
            FixedAsset.company_id == cid
        ).all()]
        if asset_ids:
            db.query(DepreciationEntry).filter(
                DepreciationEntry.asset_id.in_(asset_ids)
            ).delete(synchronize_session=False)
        _del(db, FixedAsset, cid)
        _del(db, Budget,     cid)

    # ── Documents ─────────────────────────────────────────────────────────────
    if "documents" in cats:
        _del(db, CompanyDocument, cid)

    db.commit()
    logger.info("clear-data: company_id=%s cleared categories=%s by user_id=%s",
                cid, sorted(cats), current_user.id)
    return {
        "cleared":  sorted(cats),
        "message":  f"Cleared: {', '.join(sorted(cats))}.",
    }


class NewCompanyRequest(BaseModel):
    name: str
    plan: Optional[str] = "starter"
    billing_cycle: Optional[str] = "monthly"

@router.post("/create-new")
async def create_new_company(
    body: NewCompanyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import PlanType, BillingCycle, SubscriptionStatus
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required")
    # Resolve the accountant's home company to use as parent
    parent_company_id = current_user.company_id
    try:
        plan_enum = PlanType(body.plan or "starter")
    except ValueError:
        plan_enum = PlanType.starter
    try:
        cycle_enum = BillingCycle(body.billing_cycle or "monthly")
    except ValueError:
        cycle_enum = BillingCycle.monthly
    company = Company(
        name=name,
        plan=plan_enum,
        billing_cycle=cycle_enum,
        subscription_status=SubscriptionStatus.active,  # covered by accountant's billing
        parent_company_id=parent_company_id,
    )
    db.add(company)
    db.flush()
    membership = CompanyMembership(user_id=current_user.id, company_id=company.id, role="owner")
    db.add(membership)
    db.commit()
    db.refresh(company)
    return {"id": company.id, "name": company.name, "role": "owner", "plan": body.plan or "starter"}

@router.get("/my-clients")
async def my_clients(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all client companies with pricing, volume discount, and own-plan discount info."""
    from billing import (
        PLAN_PRICES, accountant_client_discount, accountant_own_plan_cost,
        ACCOUNTANT_PLAN_DISCOUNT_PER_CLIENT,
    )

    clients = db.query(Company).filter(Company.parent_company_id == current_user.company_id).all()
    num_clients = len(clients)
    discount_rate = accountant_client_discount(num_clients)

    # Own company plan
    own_company = db.query(Company).filter(Company.id == current_user.company_id).first()
    own_plan  = own_company.plan.value          if own_company and own_company.plan          else "starter"
    own_cycle = own_company.billing_cycle.value if own_company and own_company.billing_cycle else "monthly"
    own_base  = PLAN_PRICES.get(own_plan, PLAN_PRICES["starter"])[own_cycle]
    own_discounted = accountant_own_plan_cost(own_base, num_clients)

    result = []
    for c in clients:
        plan  = c.plan.value          if c.plan          else "starter"
        cycle = c.billing_cycle.value if c.billing_cycle else "monthly"
        base  = PLAN_PRICES.get(plan, PLAN_PRICES["starter"])[cycle]
        discounted = round(base * (1 - discount_rate), 2)
        result.append({
            "id": c.id, "name": c.name, "plan": plan, "billing_cycle": cycle,
            "monthly_cost": base,
            "discounted_cost": discounted,
            "discount_pct": int(discount_rate * 100),
        })

    return {
        "clients": result,
        "num_clients": num_clients,
        "discount_pct": int(discount_rate * 100),
        "own_plan": own_plan,
        "own_cycle": own_cycle,
        "own_base_cost": own_base,
        "own_discounted_cost": own_discounted,
        "own_plan_saving": own_base - own_discounted,
        "discount_per_client": ACCOUNTANT_PLAN_DISCOUNT_PER_CLIENT,
    }

# Keep router as companies_router
companies_router = router


# ── INVOICES ──────────────────────────────────────────────────────────────────
invoices_router = APIRouter()

from payroll import VAT_RATE  # single source of truth for the SA standard VAT rate (15%)

class InvoiceCreate(BaseModel):
    client_name:     str
    supply_type:     Optional[str] = None   # "standard" | "zero_rated" | "exempt"
    client_email:    Optional[str] = None
    description:     str
    amount:          float           # Always excl. VAT
    vat_applicable:  bool = True     # Apply 15% VAT
    due_date:        Optional[str] = None
    notes:           Optional[str] = None
    currency:            Optional[str] = "ZAR"
    exchange_rate:       Optional[float] = 1.0
    vat_amount_override: Optional[float] = None  # Manual VAT for non-ZAR invoices
    cogs_amount:         Optional[float] = None  # If set, post DR Cost of Sales / CR Inventory for this amount
    # Multi-line items (JSON string: [{code,description,quantity,unit_price,vat_amount,total}])
    items_json:      Optional[str] = None
    # Travel / reference fields
    tour_ref:        Optional[str] = None
    quote_ref:       Optional[str] = None
    tax_ref:         Optional[str] = None
    travel_date:     Optional[str] = None
    pax_count:       Optional[int] = None
    passenger_name:  Optional[str] = None

class InvoiceUpdate(BaseModel):
    client_name:     Optional[str]   = None
    description:     Optional[str]   = None
    amount:          Optional[float] = None   # excl. VAT
    due_date:        Optional[str]   = None
    status:          Optional[str]   = None
    paid_date:       Optional[str]   = None
    notes:           Optional[str]   = None
    paid_amount_zar: Optional[float] = None  # ZAR actually received on payment (cumulative)
    final_payment:   Optional[bool]  = None  # foreign-currency invoices: send false when this is only a part payment
    # Multi-line items + reference fields
    items_json:      Optional[str] = None
    tour_ref:        Optional[str] = None
    quote_ref:       Optional[str] = None
    tax_ref:         Optional[str] = None
    travel_date:     Optional[str] = None
    pax_count:       Optional[int] = None
    passenger_name:  Optional[str] = None


def _strip_line_vat(items_json: Optional[str]) -> Optional[str]:
    """Zero the VAT on every line (not VAT-registered, or zero-rated / exempt supply) so the stored lines,
    the printed invoice and the invoice totals all agree."""
    if not items_json:
        return items_json
    try:
        items = json.loads(items_json)
    except (ValueError, TypeError):
        return items_json
    if not isinstance(items, list):
        return items_json
    for ln in items:
        if isinstance(ln, dict):
            ln["vat_applicable"] = False
            ln["vat_amount"] = 0
            try:
                ln["total"] = round(float(ln.get("quantity") or 0) * float(ln.get("unit_price") or 0), 2)
            except Exception:
                pass
    return json.dumps(items)


def _vat_from_line_items(items_json: Optional[str]) -> Optional[dict]:
    """Sum per-line VAT/totals from a multi-line-item invoice instead of applying
    a single flat VAT flag to the whole subtotal (audit fix 2026-09-06 — High:
    invoices with mixed VAT-exempt/standard-rated lines previously had their
    backend-recorded vat_amount/total_amount computed off `amount * VAT_RATE`
    for the *entire* subtotal, ignoring each line's own `vat_applicable` flag).

    Each line is expected to look like {code, description, quantity, unit_price,
    vat_applicable, vat_amount, total} (the shape the frontend's line-item editor
    sends). A line's own `vat_amount` is trusted if present (it already reflects
    that line's `vat_applicable` checkbox); otherwise it's derived from
    quantity * unit_price * VAT_RATE when `vat_applicable` isn't explicitly False.

    Returns None (caller should fall back to the flat calculation) if items_json
    is missing, not valid JSON, or not a non-empty list of line objects — so a
    malformed payload can never silently zero out an invoice's amount.
    """
    if not items_json:
        return None
    try:
        items = json.loads(items_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(items, list) or not items:
        return None
    subtotal = 0.0
    vat_total = 0.0
    for line in items:
        if not isinstance(line, dict):
            return None
        qty = float(line.get("quantity") or 0)
        unit_price = float(line.get("unit_price") or 0)
        line_subtotal = qty * unit_price
        subtotal += line_subtotal
        if line.get("vat_amount") is not None:
            vat_total += float(line.get("vat_amount") or 0)
        elif line.get("vat_applicable", True):
            vat_total += round(line_subtotal * VAT_RATE, 2)
    return {
        "amount": round(subtotal, 2),
        "vat_amount": round(vat_total, 2),
        "total_amount": round(subtotal + vat_total, 2),
    }


def next_invoice_number(company_id: int, db: Session) -> str:
    from sqlalchemy import func as _func
    last = db.query(_func.max(Invoice.id)).filter(Invoice.company_id == company_id).scalar() or 0
    # Use MAX(id) + 1 so deletions don't cause collisions
    existing_numbers = {
        row[0] for row in
        db.query(Invoice.invoice_number).filter(Invoice.company_id == company_id).all()
    }
    n = last + 1
    candidate = f"INV-{str(n).zfill(4)}"
    while candidate in existing_numbers:
        n += 1
        candidate = f"INV-{str(n).zfill(4)}"
    return candidate


@invoices_router.get("/payments-this-month")
async def invoice_payments_this_month(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cash received on invoices in the current calendar month, per invoice, from the payment
    journal entries (so a part payment counts in the month it was received, not in the month of
    the invoice's latest payment). Reversed payments net off."""
    from database import JournalEntry, JournalLine, Account
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    end = datetime(now.year + (now.month == 12), (now.month % 12) + 1, 1)
    rows = (db.query(JournalEntry.source_id, JournalEntry.source, JournalLine.debit, JournalLine.credit)
              .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
              .join(Account, JournalLine.account_id == Account.id)
              .filter(JournalEntry.company_id == current_user.company_id, Account.code == "1000",
                      JournalEntry.source.in_(["invoice_payment", "invoice_payment_reversal"]),
                      JournalEntry.date >= start, JournalEntry.date < end).all())
    per = {}
    for sid, _src, d, c in rows:
        per[sid] = round(per.get(sid, 0.0) + (d or 0) - (c or 0), 2)
    per = {k: v for k, v in per.items() if abs(v) >= 0.005}
    return {"by_invoice": per, "total": round(sum(per.values()), 2)}


@invoices_router.get("/")
async def list_invoices(
    limit: Optional[int] = None,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # limit/offset are optional (scale fix 2026-07-03): omitted = return all rows,
    # exactly as before, so existing frontend calls are unaffected.
    try:
        q = db.query(Invoice).filter(Invoice.company_id == current_user.company_id).order_by(Invoice.created_at.desc())
        if offset:
            q = q.offset(offset)
        if limit is not None:
            q = q.limit(limit)
        return q.all()
    except Exception as e:
        # Fallback: column may not exist yet in production DB — query without new columns
        logger.warning(f"Invoice ORM query failed ({e}), falling back to safe column list")
        db.rollback()
        from sqlalchemy import text as _text
        page_sql = ""
        if limit is not None:
            page_sql = f" LIMIT {int(limit)} OFFSET {int(offset or 0)}"
        rows = db.execute(_text(
            "SELECT id, company_id, invoice_number, client_name, client_email, "
            "description, amount, vat_amount, total_amount, currency, exchange_rate, "
            "paid_amount_zar, due_date, notes, status, issue_date, paid_date, created_at, "
            "items_json, tour_ref, quote_ref, tax_ref, travel_date, pax_count, passenger_name "
            "FROM invoices WHERE company_id = :cid ORDER BY created_at DESC" + page_sql
        ), {"cid": current_user.company_id})
        cols = list(rows.keys())
        return [dict(zip(cols, r)) for r in rows]


@invoices_router.post("/")
async def create_invoice(data: InvoiceCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (data.cogs_amount and data.cogs_amount > 0):
        _require_stock(data.items_json, current_user.company_id, db)
    # Check plan invoice limits
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    limits = {"starter": 20, "professional": 50, "business": 999999}
    limit = limits.get(company.plan, 20)

    if not company.billing_exempt:
        # Count this month's invoices
        now = datetime.utcnow()
        monthly_count = db.query(Invoice).filter(
            Invoice.company_id == current_user.company_id,
            Invoice.created_at >= datetime(now.year, now.month, 1)
        ).count()
        if monthly_count >= limit:
            raise HTTPException(status_code=403, detail=f"Monthly invoice limit ({limit}) reached. Upgrade your plan.")

    # Multi-line invoices: sum each line's own VAT instead of applying one flat
    # vat_applicable flag to the whole subtotal (audit fix 2026-09-06 — High).
    from journal import company_vat_registered as _vatreg_early
    _early_supply = (data.supply_type or "").strip().lower()
    if data.items_json and (not _vatreg_early(db, current_user.company_id) or _early_supply in ("zero_rated", "exempt")):
        data.items_json = _strip_line_vat(data.items_json)
    line_totals = _vat_from_line_items(data.items_json)
    if line_totals is not None:
        vat_amount = line_totals["vat_amount"]
        total_amount = line_totals["total_amount"]
    elif data.currency and data.currency != "ZAR" and data.vat_amount_override is not None:
        vat_amount = round(data.vat_amount_override, 2)   # User-specified VAT for foreign currency
        total_amount = round(data.amount + vat_amount, 2)
    else:
        vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0
        total_amount = round(data.amount + vat_amount, 2)

    from journal import company_vat_registered as _vatreg
    if not _vatreg(db, current_user.company_id):
        # Not a VAT vendor: no VAT may be charged
        vat_amount = 0.0
        total_amount = round(line_totals["amount"] if line_totals is not None else data.amount, 2)

    _supply = (data.supply_type or "").strip().lower() or None
    if _supply not in (None, "standard", "zero_rated", "exempt"):
        raise HTTPException(status_code=400, detail="supply_type must be standard, zero_rated or exempt")
    if _supply in ("zero_rated", "exempt"):
        # Zero-rated and exempt supplies carry no output VAT
        vat_amount = 0.0
        total_amount = round(line_totals["amount"] if line_totals is not None else data.amount, 2)

    invoice = Invoice(
        company_id=current_user.company_id,
        invoice_number=next_invoice_number(current_user.company_id, db),
        client_name=clean(data.client_name, 200),
        client_email=clean(data.client_email, 200),
        description=clean(data.description, 1000),
        amount=line_totals["amount"] if line_totals is not None else data.amount,
        vat_amount=vat_amount,
        total_amount=total_amount,
        due_date=datetime.fromisoformat(data.due_date) if data.due_date else None,
        notes=clean(data.notes, 2000),
        status=InvoiceStatus.sent,
        currency=data.currency or "ZAR",
        exchange_rate=data.exchange_rate or 1.0,
        items_json=data.items_json,
        supply_type=_supply,
        tour_ref=clean(data.tour_ref, 200) if data.tour_ref else None,
        quote_ref=clean(data.quote_ref, 200) if data.quote_ref else None,
        tax_ref=clean(data.tax_ref, 200) if data.tax_ref else None,
        travel_date=clean(data.travel_date, 50) if data.travel_date else None,
        pax_count=data.pax_count,
        passenger_name=clean(data.passenger_name, 200) if data.passenger_name else None,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    logger.info(f"Invoice created: {invoice.invoice_number} for {data.client_name}")
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_invoice_raised(invoice, db)
        # Optional COGS entry: DR Cost of Sales (5000) / CR Inventory at Cost (1200)
        if data.cogs_amount and data.cogs_amount > 0:
            journal_engine.post_invoice_cogs(invoice, round(data.cogs_amount, 2), db)
            invoice.stock_cogs_json = "[]"   # manual cost entered - no automatic stock movement
        else:
            _apply_invoice_stock(invoice, db, force=True)
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for invoice {invoice.invoice_number}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Invoice created but journal entry failed: {e}. Invoice has been rolled back — please retry.",
        )
    return invoice


def _stock_shortages(items_json, company_id: int, db: Session) -> list:
    """Lines whose Code is an inventory SKU but whose total quantity exceeds what is on hand."""
    import json as _json
    try:
        lines = _json.loads(items_json) if items_json else []
    except Exception:
        return []
    want = {}
    for ln in (lines if isinstance(lines, list) else []):
        code = (str(ln.get("code") or "")).strip().lower()
        try:
            q = float(ln.get("quantity") or 0)
        except Exception:
            q = 0
        if code and q > 0:
            want[code] = want.get(code, 0) + q
    if not want:
        return []
    short = []
    for i in db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.is_active == True).all():
        k = (i.sku or "").strip().lower()
        if k in want and want[k] > (i.quantity_on_hand or 0) + 1e-6:
            short.append(f"{i.name}: need {want[k]:g}, only {(i.quantity_on_hand or 0):g} on hand")
    return short


def _require_stock(items_json, company_id: int, db: Session):
    short = _stock_shortages(items_json, company_id, db)
    if short:
        raise HTTPException(status_code=400, detail="Not enough stock to invoice this. " + "; ".join(short) + ". Receive stock first (purchase order or stock adjustment).")


def _apply_invoice_stock(invoice, db: Session, force: bool = False):
    """Invoice lines whose Code equals an inventory SKU sell stock: reduce quantity on hand and post
    DR Cost of Sales (5000) / CR Inventory (1200) at the item's cost. Idempotent per invoice."""
    import json as _json
    if not force and invoice.stock_cogs_json != "":
        return   # already applied, or a legacy invoice that must never touch stock
    _require_stock(invoice.items_json, invoice.company_id, db)   # never sell stock that is not there (keeps Inventory 1200 >= 0)
    moves, cogs = [], 0.0
    try:
        lines = _json.loads(invoice.items_json) if invoice.items_json else []
    except Exception:
        lines = []
    for ln in (lines if isinstance(lines, list) else []):
        code = (str(ln.get("code") or "")).strip().lower()
        if not code:
            continue
        item = next((i for i in db.query(InventoryItem).filter(
                        InventoryItem.company_id == invoice.company_id,
                        InventoryItem.is_active == True).all()
                     if (i.sku or "").strip().lower() == code), None)
        if not item:
            continue
        try:
            qty = float(ln.get("quantity") or 0)
        except Exception:
            qty = 0
        if qty <= 0:
            continue
        cost = round(qty * (item.unit_cost or 0), 2)
        item.quantity_on_hand = round((item.quantity_on_hand or 0) - qty, 4)
        cogs += cost
        moves.append({"item_id": item.id, "qty": qty, "cost": cost})
    invoice.stock_cogs_json = _json.dumps(moves)
    if cogs > 0:
        journal_engine.post_invoice_cogs(invoice, round(cogs, 2), db)


def _reverse_invoice_stock(invoice, db: Session):
    """Undo _apply_invoice_stock: put the quantities back and reverse the cost-of-sales entry."""
    import json as _json
    if not invoice.stock_cogs_json:
        return
    try:
        moves = _json.loads(invoice.stock_cogs_json)
    except Exception:
        moves = []
    for m in moves:
        item = db.query(InventoryItem).filter(InventoryItem.id == m.get("item_id"), InventoryItem.company_id == invoice.company_id).first()
        if item:
            item.quantity_on_hand = round((item.quantity_on_hand or 0) + (m.get("qty") or 0), 4)
    journal_engine.reverse_journal_entries(invoice.company_id, "invoice_cogs", invoice.id, db,
                                           reason=f"Stock sale reversed - {invoice.invoice_number}")
    invoice.stock_cogs_json = ""


def _has_active_raised_entry(company_id: int, invoice_id: int, db: Session) -> bool:
    """True if an unreversed 'invoice' (raised) journal entry exists for this invoice.
    Used by the draft-transition logic (audit fix 2026-07-08) to decide whether
    issuing a draft needs to (re-)post the raised entry."""
    from database import JournalEntry as _JE
    ids = [r[0] for r in db.query(_JE.id).filter(
        _JE.company_id == company_id,
        _JE.source == "invoice",
        _JE.source_id == invoice_id,
    ).all()]
    if not ids:
        return False
    reversed_ids = {r[0] for r in db.query(_JE.is_reversal_of).filter(
        _JE.is_reversal_of.in_(ids),
    ).all()}
    return any(i not in reversed_ids for i in ids)


class BadDebtWriteOff(BaseModel):
    reason: str
    date:   Optional[str] = None      # ISO date; default today

class BadDebtRecovery(BaseModel):
    amount: Optional[float] = None    # incl VAT; default = the whole invoice total
    date:   Optional[str] = None


@invoices_router.post("/{invoice_id}/write-off")
async def write_off_bad_debt(invoice_id: int, data: BadDebtWriteOff, current_user: User = Depends(require_role("owner", "admin", "accountant")), db: Session = Depends(get_db)):
    """Write an unpaid invoice off as irrecoverable (VAT Act s22): books the bad debt and gives the VAT back on the VAT201."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status not in (InvoiceStatus.sent, InvoiceStatus.overdue, InvoiceStatus.partial):
        raise HTTPException(status_code=400, detail="Only issued invoices with a balance owing can be written off.")
    if not (data.reason or "").strip():
        raise HTTPException(status_code=400, detail="A reason is required - SARS may ask for evidence that the debt is irrecoverable.")
    when = datetime.fromisoformat(data.date) if data.date else datetime.utcnow()
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_bad_debt_writeoff(inv, db, when=when, reason=data.reason.strip())
        inv.status = InvoiceStatus.written_off
        inv.written_off_date = when
        inv.written_off_reason = data.reason.strip()[:1000]
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Write-off failed and nothing was saved: {e}")
    return {"status": "written_off", "invoice_id": inv.id,
            "message": "Invoice written off. The VAT on it is deducted on the VAT201 for the month of the write-off. Keep your evidence of recovery steps."}


@invoices_router.post("/{invoice_id}/bad-debt-recovery")
async def recover_bad_debt(invoice_id: int, data: BadDebtRecovery, current_user: User = Depends(require_role("owner", "admin", "accountant")), db: Session = Depends(get_db)):
    """Money received on a written-off invoice: books it and accounts for output VAT on the recovered part (s22(3))."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status != InvoiceStatus.written_off:
        raise HTTPException(status_code=400, detail="Only written-off invoices can have a bad-debt recovery recorded.")
    rate = float(inv.exchange_rate or 1.0) if (inv.currency and inv.currency != "ZAR") else 1.0
    full_zar  = round((inv.total_amount or 0) * rate, 2)
    total_zar = journal_engine._open_zar_parts(inv)[0]      # the balance that was written off (after any part payment)
    left = round(total_zar - (inv.bad_debt_recovered_zar or 0), 2)
    amt = round(data.amount if data.amount is not None else left, 2)
    if amt <= 0 or amt > left + 0.005:
        raise HTTPException(status_code=400, detail=f"Recovery must be between 0.01 and the amount still written off (R {left:,.2f}).")
    when = datetime.fromisoformat(data.date) if data.date else datetime.utcnow()
    try:
        journal_engine.post_bad_debt_recovery(inv, amt, db, when=when)
        inv.bad_debt_recovered_zar = round((inv.bad_debt_recovered_zar or 0) + amt, 2)
        if inv.bad_debt_recovered_zar >= total_zar - 0.005:
            inv.status = InvoiceStatus.paid
            inv.paid_date = when
            inv.paid_amount_zar = full_zar
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Recovery failed and nothing was saved: {e}")
    return {"status": inv.status.value, "recovered_zar": inv.bad_debt_recovered_zar, "message": "Recovery recorded. Output VAT on it falls in this month's VAT201."}


@invoices_router.put("/{invoice_id}")
async def update_invoice(invoice_id: int, data: InvoiceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.written_off:
        raise HTTPException(status_code=400, detail="This invoice was written off as a bad debt and can no longer be edited. Use 'Record Recovery' if the debtor pays.")
    was_paid     = invoice.status == InvoiceStatus.paid
    was_partial  = invoice.status == InvoiceStatus.partial
    was_settled  = was_paid or was_partial   # some money has been received
    old_paid_amount = invoice.paid_amount_zar or 0.0
    was_draft    = invoice.status == InvoiceStatus.draft
    _items_replaced = data.items_json is not None and data.items_json != invoice.items_json
    if data.status == "written_off":
        raise HTTPException(status_code=400, detail="Use the 'Write off' action to write an invoice off as a bad debt.")
    final_status = InvoiceStatus(data.status) if data.status else invoice.status
    # Part payments. The frontend sends status="paid" with the CUMULATIVE amount received (ZAR);
    # the backend decides paid vs partial from that amount (the request's amount, never the stale
    # stored one). Foreign-currency invoices cannot be told apart from an FX shortfall by amount
    # alone, so a foreign payment settles the invoice unless the caller sends final_payment=false.
    _is_foreign = bool(invoice.currency and invoice.currency != "ZAR")
    _rate       = float(invoice.exchange_rate or 1.0) if _is_foreign else 1.0
    _total_due  = round((invoice.total_amount or 0) * _rate, 2)      # ZAR carried in debtors
    if data.status in ("paid", "partial"):
        if data.paid_amount_zar is None:
            if data.status == "partial":
                raise HTTPException(status_code=400, detail="Enter the amount received for a part payment.")
            if was_partial or not _is_foreign:
                data.paid_amount_zar = _total_due      # plain 'mark as paid' = settle the balance
        if data.paid_amount_zar is not None:
            cum = round(float(data.paid_amount_zar), 2)
            if cum <= 0:
                raise HTTPException(status_code=400, detail="Payment amount must be greater than zero.")
            if not _is_foreign and cum > _total_due + 0.01:
                raise HTTPException(status_code=400, detail=f"Amount received (R{cum:,.2f}) is more than the invoice total (R{_total_due:,.2f}).")
            if was_settled and cum + 0.005 < round(old_paid_amount, 2):
                raise HTTPException(status_code=400, detail=f"R{old_paid_amount:,.2f} has already been recorded. Enter the new cumulative total, or mark the invoice unpaid first to correct it.")
            if _is_foreign:
                _final = data.final_payment is not False or cum + 0.005 >= _total_due   # foreign: settles unless the caller says it is only a part payment
                data.paid_amount_zar = cum
            else:
                _final = cum + 0.005 >= _total_due
                data.paid_amount_zar = min(cum, _total_due)
            final_status = InvoiceStatus.paid if _final else InvoiceStatus.partial
    amount_changed = (
        data.amount is not None
        and round(data.amount, 2) != round(invoice.amount or 0, 2)
    )
    # Multi-line invoices: recompute from each line's own VAT instead of scaling
    # a single flat rate across the whole subtotal (audit fix 2026-09-06 — High).
    # This also catches an edit that only toggles a line's vat_applicable flag
    # without changing the subtotal, which data.amount alone wouldn't detect.
    if data.items_json is not None:
        from journal import company_vat_registered as _vatreg_u
        if (not _vatreg_u(db, current_user.company_id)) or (invoice.supply_type in ("zero_rated", "exempt")):
            data.items_json = _strip_line_vat(data.items_json)
    line_totals = _vat_from_line_items(data.items_json) if data.items_json is not None else None
    if line_totals is not None:
        items_changed = (
            round(line_totals["amount"], 2) != round(invoice.amount or 0, 2)
            or round(line_totals["vat_amount"], 2) != round(invoice.vat_amount or 0, 2)
        )
        amount_changed = amount_changed or items_changed
    # Block amount edits on invoices that remain paid: the payment journal entry
    # carries the old amount and cannot be silently re-stated. Revert the invoice
    # to unpaid first (which reverses the payment entry), then edit the amount.
    if amount_changed and was_settled and final_status in (InvoiceStatus.paid, InvoiceStatus.partial):
        raise HTTPException(
            status_code=400,
            detail="Cannot change the amount of a paid invoice. Mark it as unpaid first, then edit the amount.",
        )
    if data.client_name:
        invoice.client_name = data.client_name
    if data.description:
        invoice.description = data.description
    if amount_changed:
        if line_totals is not None:
            # Line items are present and authoritative — trust their per-line
            # VAT sum over both the flat-rate fallback below and data.amount
            # (which for a line-item invoice is just the frontend-computed
            # subtotal and carries no VAT-exemption information of its own).
            invoice.amount       = line_totals["amount"]
            invoice.vat_amount   = line_totals["vat_amount"]
            invoice.total_amount = line_totals["total_amount"]
        else:
            # Preserve the invoice's original VAT treatment (audit fix 2026-07-07):
            # zero-rated invoices keep 0 VAT, standard invoices keep their effective
            # rate, and foreign-currency VAT overrides scale proportionally — instead
            # of forcing 15% on every edit.
            old_amount = invoice.amount or 0
            vat_rate = (invoice.vat_amount / old_amount) if (old_amount and invoice.vat_amount) else 0.0
            invoice.amount       = data.amount
            invoice.vat_amount   = round(data.amount * vat_rate, 2)
            invoice.total_amount = round(data.amount + invoice.vat_amount, 2)
    if data.due_date is not None:
        invoice.due_date = datetime.fromisoformat(data.due_date) if data.due_date else None
    if data.status:
        invoice.status = final_status
    if data.paid_date:
        invoice.paid_date = datetime.fromisoformat(data.paid_date)
    # If being marked paid/partial with no paid_date, default to now so date-filtered reports include it
    if not was_settled and invoice.status in (InvoiceStatus.paid, InvoiceStatus.partial) and not invoice.paid_date:
        invoice.paid_date = datetime.utcnow()
    if data.notes:
        invoice.notes = data.notes
    if data.paid_amount_zar is not None:
        invoice.paid_amount_zar = data.paid_amount_zar
    # Multi-line items + reference fields
    if data.items_json is not None:
        invoice.items_json = data.items_json
    if data.tour_ref is not None:
        invoice.tour_ref = clean(data.tour_ref, 200) if data.tour_ref else None
    if data.quote_ref is not None:
        invoice.quote_ref = clean(data.quote_ref, 200) if data.quote_ref else None
    if data.tax_ref is not None:
        invoice.tax_ref = clean(data.tax_ref, 200) if data.tax_ref else None
    if data.travel_date is not None:
        invoice.travel_date = clean(data.travel_date, 50) if data.travel_date else None
    if data.pax_count is not None:
        invoice.pax_count = data.pax_count
    if data.passenger_name is not None:
        invoice.passenger_name = clean(data.passenger_name, 200) if data.passenger_name else None

    reverted_to_unpaid = was_settled and invoice.status not in (InvoiceStatus.paid, InvoiceStatus.partial)
    newly_paid         = not was_paid and invoice.status == InvoiceStatus.paid
    newly_partial      = not was_settled and invoice.status == InvoiceStatus.partial
    top_up_to_paid     = was_partial and invoice.status in (InvoiceStatus.paid, InvoiceStatus.partial) and round((invoice.paid_amount_zar or 0) - old_paid_amount, 2) > 0
    # Draft transitions (audit fix 2026-07-08): moving an issued invoice to draft
    # must reverse its raised entry (a draft carries no AR/VAT liability), and
    # issuing a draft must re-post it — previously neither happened, desyncing
    # AR control (1100) with no self-service repair via backfill.
    became_draft = not was_draft and final_status == InvoiceStatus.draft
    left_draft   = was_draft and final_status != InvoiceStatus.draft

    # Journal postings — commit once only AFTER both the field updates and the
    # journal entries succeed, so a journal failure rolls back the edit too.
    try:
        if amount_changed or reverted_to_unpaid or newly_paid or newly_partial or top_up_to_paid or became_draft or left_draft:
            journal_engine.init_accounts(current_user.company_id, db)
        if reverted_to_unpaid:
            # Reverse the payment entry (audit fix 2026-07-07): leaving it in place
            # overstated Bank (1000) and understated AR (1100).
            journal_engine.reverse_journal_entries(
                current_user.company_id, "invoice_payment", invoice.id, db,
                reason=f"Payment reverted — {invoice.invoice_number} ({invoice.client_name})",
            )
            invoice.paid_date = None
            invoice.paid_amount_zar = None
        if became_draft and not amount_changed:
            # Reverse the raised entry — repeat-safe, so an invoice that was
            # already reversed (e.g. by a prior draft-time amount edit) is skipped.
            journal_engine.reverse_journal_entries(
                current_user.company_id, "invoice", invoice.id, db,
                reason=f"Invoice moved to draft — {invoice.invoice_number} ({invoice.client_name})",
            )
        if left_draft and not amount_changed:
            # Re-post the raised entry only if none is currently in force (it was
            # reversed when the invoice was drafted or amount-edited as a draft).
            # Legacy drafts whose raised entry was never reversed are left as-is.
            if not _has_active_raised_entry(current_user.company_id, invoice.id, db):
                journal_engine.post_invoice_raised(invoice, db)
        if amount_changed:
            # Reverse the original "invoice raised" entry and re-post it with the
            # new amounts (audit fix 2026-07-07), mirroring the delete flow — so
            # AR (1100), Sales Revenue (4000) and VAT Output (2100) stay in sync
            # with the invoice table instead of drifting until a backfill.
            journal_engine.reverse_journal_entries(
                current_user.company_id, "invoice", invoice.id, db,
                reason=f"Invoice amended — {invoice.invoice_number} ({invoice.client_name})",
            )
            # Drafts are not re-posted: an unissued invoice carries no AR or VAT
            # liability (consistent with the dashboard's draft exclusion). The
            # raised entry is posted when the invoice is issued/backfilled.
            if invoice.status != InvoiceStatus.draft:
                journal_engine.post_invoice_raised(invoice, db)
        if amount_changed or _items_replaced or became_draft:
            _reverse_invoice_stock(invoice, db)
        if (amount_changed or _items_replaced or left_draft) and invoice.status != InvoiceStatus.draft:
            _apply_invoice_stock(invoice, db)
        if newly_paid or newly_partial or top_up_to_paid:
            # Post only the INCREMENTAL amount received this transaction so the
            # journal doesn't double-count earlier partial payments.
            if _is_foreign and data.paid_amount_zar is None:
                journal_engine.post_invoice_paid(invoice, db)        # legacy single payment (estimated ZAR)
            else:
                payment_delta = round((invoice.paid_amount_zar or 0) - old_paid_amount, 2)
                if payment_delta > 0:
                    _saved_paid = invoice.paid_amount_zar
                    _ar = None
                    if _is_foreign:
                        # settling: clear whatever carried AR is left (the difference is realised FX);
                        # part payment: clear AR by the ZAR received, FX is taken when it is settled
                        _ar = round(_total_due - old_paid_amount, 2) if invoice.status == InvoiceStatus.paid else payment_delta
                    invoice.paid_amount_zar = payment_delta
                    journal_engine.post_invoice_paid(invoice, db, ar_zar=_ar)
                    invoice.paid_amount_zar = _saved_paid
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Journal post failed for invoice update {invoice.invoice_number}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Invoice update failed — journal entry could not be posted: {e}. Please retry.",
        )
    return invoice


@invoices_router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: int, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    # Reverse all journal entries linked to this invoice before deleting, so that
    # AR control account (1100), Sales Revenue (4000), and Bank (1000) remain accurate.
    # Sources to reverse: "invoice" (raised), "invoice_payment" (paid), "invoice_cogs" (COGS).
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        reason = f"Invoice deleted — {invoice.invoice_number} ({invoice.client_name})"
        _reverse_invoice_stock(invoice, db)   # restock + reverse the cost of sales
        for src in ("invoice", "invoice_payment", "invoice_cogs"):
            journal_engine.reverse_journal_entries(
                current_user.company_id, src, invoice.id, db, reason=reason
            )
        db.commit()
    except Exception as e:
        logger.error(f"Journal reversal failed for invoice {invoice.invoice_number}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Invoice deletion aborted — journal reversal failed: {e}. Please retry.",
        )
    db.delete(invoice)
    db.commit()
    return {"status": "deleted"}



@invoices_router.post("/{invoice_id}/send")
async def send_invoice(invoice_id: int, current_user: User = Depends(require_role("owner","admin","accountant")), db: Session = Depends(get_db)):
    """Generate portal token (if needed), mark invoice as sent, and email the client."""
    import uuid as _uuid
    from datetime import datetime as _dt
    from email_service import send_invoice_email

    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.company_id == current_user.company_id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.paid:
        raise HTTPException(status_code=400, detail="Invoice is already paid.")

    # Generate portal token if missing
    if not invoice.portal_token:
        invoice.portal_token = _uuid.uuid4().hex
        invoice.portal_token_created_at = _dt.utcnow()

    # Mark as sent. If this was a draft whose raised journal entry was reversed
    # (draft-time amount edit) or never posted, re-post it now — issuing the
    # invoice is what creates the AR/VAT liability (audit fix 2026-07-08).
    was_draft = invoice.status == InvoiceStatus.draft
    invoice.status = InvoiceStatus.sent
    try:
        if was_draft and not _has_active_raised_entry(current_user.company_id, invoice.id, db):
            journal_engine.init_accounts(current_user.company_id, db)
            journal_engine.post_invoice_raised(invoice, db)
        if was_draft:
            _apply_invoice_stock(invoice, db)
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for invoice send {invoice.invoice_number}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Invoice send failed — journal entry could not be posted: {e}. Please retry.",
        )
    db.refresh(invoice)

    portal_url = f"{os.environ.get('FRONTEND_URL','https://zuzan.co.za')}/portal/{invoice.portal_token}"

    # Send email if client email is known
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    email_sent = False
    client_email = getattr(invoice, "client_email", None) or ""
    if client_email:
        try:
            send_invoice_email(
                client_email=client_email,
                client_name=invoice.client_name or "Client",
                company_name=company.name if company else "ZuZan",
                invoice_number=invoice.invoice_number,
                description=invoice.description or "",
                total_amount=invoice.total_amount or 0,
                currency=invoice.currency or "ZAR",
                due_date=invoice.due_date.strftime("%d %b %Y") if invoice.due_date else "",
                portal_token=invoice.portal_token,
            )
            email_sent = True
        except Exception as e:
            logger.warning(f"Invoice email failed (non-fatal): {e}")

    return {
        "status":       "sent",
        "portal_token": invoice.portal_token,
        "portal_url":   portal_url,
        "email_sent":   email_sent,
    }


# ── EXPENSES ──────────────────────────────────────────────────────────────────
expenses_router = APIRouter()

class ExpenseCreate(BaseModel):
    vendor:          str
    vat_use:         Optional[str] = None   # "taxable" | "exempt" | "denied" (e.g. motor car purchase) | None (shared, apportioned)
    description:     str
    amount:          float           # Always excl. VAT
    vat_applicable:  bool = True     # Apply 15% VAT
    category:        Optional[str] = "General"
    expense_date:    Optional[str] = None
    is_on_credit:    bool = False    # True = purchased on credit; journals to AP (2000) not Bank (1000)

class ExpenseUpdate(BaseModel):
    vendor:          Optional[str] = None
    description:     Optional[str] = None
    amount:          Optional[float] = None   # excl. VAT — vat_amount is recalculated automatically
    vat_applicable:  Optional[bool] = None    # if omitted, inferred from existing vat_amount
    category:        Optional[str] = None
    is_on_credit:    Optional[bool] = None


@expenses_router.get("/")
async def list_expenses(
    limit: Optional[int] = None,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Optional pagination (scale fix 2026-07-03) — omitted params return all rows as before.
    q = db.query(Expense).filter(Expense.company_id == current_user.company_id).order_by(Expense.created_at.desc())
    if offset:
        q = q.offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


@expenses_router.post("/")
async def create_expense(data: ExpenseCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from journal import company_vat_registered as _vatreg
    exp_vat    = round(data.amount * VAT_RATE, 2) if (data.vat_applicable and _vatreg(db, current_user.company_id)) else 0
    exp_total  = round(data.amount + exp_vat, 2)

    expense = Expense(
        company_id=current_user.company_id,
        vendor=clean(data.vendor, 200),
        description=clean(data.description, 1000),
        amount=exp_total,
        vat_amount=exp_vat,
        category=clean(data.category, 200),
        expense_date=datetime.fromisoformat(data.expense_date) if data.expense_date else datetime.utcnow(),
        is_on_credit=data.is_on_credit,
        vat_use=(data.vat_use if data.vat_use in ("taxable", "exempt", "denied") else None),
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_expense(expense, db)
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for expense {expense.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Expense saved but journal entry failed: {e}. Expense has been rolled back — please retry.",
        )
    return expense


@expenses_router.put("/{expense_id}")
async def update_expense(expense_id: int, data: ExpenseUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.company_id == current_user.company_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    # Apply non-amount fields first
    non_amount_fields = {k: v for k, v in data.dict(exclude_none=True).items()
                         if k not in ("amount", "vat_applicable")}
    for field, value in non_amount_fields.items():
        setattr(expense, field, value)

    # If amount is being updated, recalculate vat_amount to keep it consistent.
    # expense.amount is stored VAT-inclusive; data.amount is excl-VAT (matching create convention).
    if data.amount is not None:
        from journal import company_vat_registered as _vatreg
        # Determine whether VAT applies: explicit flag > infer from existing vat_amount
        apply_vat = data.vat_applicable if data.vat_applicable is not None else (
            (expense.vat_amount or 0) > 0
        )
        new_vat = round(data.amount * VAT_RATE, 2) if (apply_vat and _vatreg(db, current_user.company_id)) else 0.0
        new_total = round(data.amount + new_vat, 2)

        # Post a correcting journal entry if the stored amount has changed
        old_total = expense.amount or 0
        if abs(new_total - old_total) > 0.01:
            # Block amount edits on paid on-credit expenses (audit fix 2026-07-08):
            # the AP-clearing payment entry carries the old amount, so re-stating
            # the expense would desync AP (2000) — same rule as paid invoices.
            if expense.is_on_credit and expense.paid_at:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot change the amount of a paid credit expense. Delete it and capture a new expense instead.",
                )
            try:
                journal_engine.init_accounts(current_user.company_id, db)
                # Reverse the current 'expense' entry via tracked reversals, then
                # re-post with the new amounts. (Audit fix 2026-07-08: the old
                # manual loop reversed EVERY 'expense' entry on each edit with no
                # is_reversal_of tracking, so a second amount edit double-reversed
                # the original entry and corrupted the ledger.)
                from database import JournalEntry as _JE
                tracked_reversed = {
                    r[0] for r in db.query(_JE.is_reversal_of).filter(
                        _JE.company_id == current_user.company_id,
                        _JE.is_reversal_of.isnot(None),
                    ).all()
                }
                entries = db.query(_JE).filter(
                    _JE.company_id == current_user.company_id,
                    _JE.source == "expense",
                    _JE.source_id == expense.id,
                ).order_by(_JE.id).all()
                unreversed = [e for e in entries if e.id not in tracked_reversed]
                # Legacy guard: reversals posted by the pre-2026-07-08 code have
                # source 'expense_reversal' but no is_reversal_of link. Pair each
                # one to an unreversed entry of the same total (oldest first) and
                # skip that entry, so it is not reversed a second time.
                legacy_totals = [
                    round(sum(l.debit or 0 for l in r.lines), 2)
                    for r in db.query(_JE).filter(
                        _JE.company_id == current_user.company_id,
                        _JE.source == "expense_reversal",
                        _JE.source_id == expense.id,
                        _JE.is_reversal_of.is_(None),
                    ).all()
                ]
                for entry in unreversed:
                    entry_total = round(sum(l.debit or 0 for l in entry.lines), 2)
                    if entry_total in legacy_totals:
                        legacy_totals.remove(entry_total)
                        continue
                    journal_engine.reverse_entry_by_id(
                        entry.id, db,
                        reason=f"Expense amended — {expense.vendor}: {expense.description or ''}",
                    )
                # Re-post with the new amounts
                expense.amount     = new_total
                expense.vat_amount = new_vat
                journal_engine.post_expense(expense, db)
                db.commit()
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Journal correction failed for expense {expense.id}: {e}")
                db.rollback()
                # Fatal (audit fix 2026-07-08): previously this was swallowed and the
                # field update was saved anyway, silently desyncing the ledger.
                raise HTTPException(
                    status_code=500,
                    detail=f"Expense update failed — journal correction could not be posted: {e}. Please retry.",
                )

        expense.amount     = new_total
        expense.vat_amount = new_vat

    if data.is_on_credit is not None:
        expense.is_on_credit = data.is_on_credit

    db.commit()
    return expense


@expenses_router.post("/{expense_id}/pay")
async def pay_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark an on-credit expense as paid and clear the Accounts Payable balance.
    Posts journal entry: DR Accounts Payable (2000) / CR Bank / Cash (1000).
    Only valid for expenses recorded with is_on_credit=True that have not yet been paid.
    """
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.company_id == current_user.company_id,
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if not expense.is_on_credit:
        raise HTTPException(
            status_code=400,
            detail="This expense was not recorded on credit. Only on-credit expenses can be paid via this endpoint.",
        )
    if expense.paid_at:
        raise HTTPException(status_code=400, detail="Expense has already been marked as paid.")

    expense.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(expense)

    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_expense_paid(expense, db)
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for expense payment {expense.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Payment recording failed — journal entry could not be posted: {e}. Please retry.",
        )
    return expense


@expenses_router.delete("/{expense_id}")
async def delete_expense(expense_id: int, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.company_id == current_user.company_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    # Reverse ALL journal entries for this expense before deleting, so that the
    # Expense account, VAT Input (1300), AP (2000) and Bank (1000) remain accurate.
    # Sources: "expense" (capture) and "expense_payment" (AP settlement) — audit fix
    # 2026-07-08: deleting a paid credit expense previously left the payment entry
    # (DR AP / CR Bank) in the ledger, understating Bank and desyncing Rule 7.
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        reason = f"Expense deleted — {expense.vendor}: {expense.description or ''}"
        for src in ("expense", "expense_payment"):
            journal_engine.reverse_journal_entries(
                current_user.company_id, src, expense.id, db, reason=reason,
            )
        db.commit()
    except Exception as e:
        logger.error(f"Journal reversal failed for expense {expense.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Expense deletion aborted — journal reversal failed: {e}. Please retry.",
        )
    db.delete(expense)
    db.commit()
    return {"status": "deleted"}


# ── CHART OF ACCOUNTS ─────────────────────────────────────────────────────────
coa_router = APIRouter()

class AccountIn(BaseModel):
    code:        str
    name:        str
    type:        str = "Detail"
    group:       str = "Expenses"
    normal:      str = "Debit"
    description: str = ""

@coa_router.get("/")
async def list_coa(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all custom COA rows for this company (the frontend merges with DEFAULT_COA)."""
    rows = (
        db.query(CompanyAccount)
        .filter(CompanyAccount.company_id == current_user.company_id)
        .all()
    )
    return [
        {
            "id":          r.id,
            "code":        r.code,
            "name":        r.name,
            "type":        r.type,
            "group":       r.group,
            "normal":      r.normal,
            "description": r.description or "",
            "is_deleted":  r.is_deleted,
            "custom":      True,
        }
        for r in rows
    ]

@coa_router.post("/")
async def create_account(
    payload: AccountIn,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Add a new custom account (or un-delete a soft-deleted one with the same code)."""
    existing = (
        db.query(CompanyAccount)
        .filter(
            CompanyAccount.company_id == current_user.company_id,
            CompanyAccount.code == payload.code.strip(),
        )
        .first()
    )
    if existing:
        if existing.is_deleted:
            # Resurrect it with new values
            existing.name        = payload.name.strip()
            existing.type        = payload.type
            existing.group       = payload.group
            existing.normal      = payload.normal
            existing.description = payload.description
            existing.is_deleted  = False
            db.commit()
            db.refresh(existing)
            return {"id": existing.id, "code": existing.code, "name": existing.name,
                    "type": existing.type, "group": existing.group, "normal": existing.normal,
                    "description": existing.description, "is_deleted": False, "custom": True}
        raise HTTPException(status_code=400, detail="Account code already exists.")
    acct = CompanyAccount(
        company_id  = current_user.company_id,
        code        = payload.code.strip(),
        name        = payload.name.strip(),
        type        = payload.type,
        group       = payload.group,
        normal      = payload.normal,
        description = payload.description,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return {"id": acct.id, "code": acct.code, "name": acct.name,
            "type": acct.type, "group": acct.group, "normal": acct.normal,
            "description": acct.description, "is_deleted": False, "custom": True}

@coa_router.put("/{code}")
async def update_account(
    code: str,
    payload: AccountIn,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Update an existing custom account."""
    acct = (
        db.query(CompanyAccount)
        .filter(
            CompanyAccount.company_id == current_user.company_id,
            CompanyAccount.code == code,
            CompanyAccount.is_deleted == False,
        )
        .first()
    )
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found.")
    acct.name        = payload.name.strip()
    acct.type        = payload.type
    acct.group       = payload.group
    acct.normal      = payload.normal
    acct.description = payload.description
    db.commit()
    db.refresh(acct)
    return {"id": acct.id, "code": acct.code, "name": acct.name,
            "type": acct.type, "group": acct.group, "normal": acct.normal,
            "description": acct.description, "is_deleted": False, "custom": True}

@coa_router.delete("/{code}")
async def delete_account(
    code: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Soft-delete a custom account (or mark a default account as hidden for this company)."""
    acct = (
        db.query(CompanyAccount)
        .filter(
            CompanyAccount.company_id == current_user.company_id,
            CompanyAccount.code == code,
        )
        .first()
    )
    if acct:
        acct.is_deleted = True
        db.commit()
    else:
        # First time hiding a default account — create a tombstone row
        tombstone = CompanyAccount(
            company_id  = current_user.company_id,
            code        = code,
            name        = "__deleted__",
            type        = "Detail",
            group       = "Expenses",
            normal      = "Debit",
            description = "",
            is_deleted  = True,
        )
        db.add(tombstone)
        db.commit()
    return {"status": "deleted", "code": code}


# ── SERVICE ITEM CATALOGUE ────────────────────────────────────────────────────
service_router = APIRouter()

class ServiceItemIn(BaseModel):
    code:           str
    name:           str
    description:    str = ""
    unit_price:     float = 0.0
    vat_applicable: bool = True
    unit:           str = "each"
    is_active:      bool = True

def _service_dict(s: ServiceItem) -> dict:
    return {
        "id": s.id, "code": s.code, "name": s.name,
        "description": s.description, "unit_price": s.unit_price,
        "vat_applicable": s.vat_applicable, "unit": s.unit, "is_active": s.is_active,
    }

@service_router.get("/")
async def list_service_items(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(ServiceItem)
        .filter(ServiceItem.company_id == current_user.company_id)
        .order_by(ServiceItem.code)
        .all()
    )
    return [_service_dict(s) for s in items]

@service_router.post("/")
async def create_service_item(
    payload: ServiceItemIn,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(ServiceItem)
        .filter(ServiceItem.company_id == current_user.company_id, ServiceItem.code == payload.code)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Service code '{payload.code}' already exists.")
    item = ServiceItem(company_id=current_user.company_id, **payload.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _service_dict(item)

@service_router.put("/{item_id}")
async def update_service_item(
    item_id: int,
    payload: ServiceItemIn,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(ServiceItem)
        .filter(ServiceItem.id == item_id, ServiceItem.company_id == current_user.company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Service item not found.")
    # Check code uniqueness if code changed
    if payload.code != item.code:
        clash = db.query(ServiceItem).filter(
            ServiceItem.company_id == current_user.company_id,
            ServiceItem.code == payload.code,
            ServiceItem.id != item_id,
        ).first()
        if clash:
            raise HTTPException(status_code=400, detail=f"Service code '{payload.code}' already exists.")
    for field, value in payload.dict().items():
        setattr(item, field, value)
    item.updated_at = datetime.utcnow()
    db.commit()
    return _service_dict(item)

@service_router.delete("/{item_id}")
async def delete_service_item(
    item_id: int,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(ServiceItem)
        .filter(ServiceItem.id == item_id, ServiceItem.company_id == current_user.company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Service item not found.")
    db.delete(item)
    db.commit()
    return {"status": "deleted", "id": item_id}


# ── EMPLOYEES ─────────────────────────────────────────────────────────────────
employees_router = APIRouter()

class EmployeeCreate(BaseModel):
    model_config = {"extra": "ignore"}   # Pydantic v2: silently drop unknown fields
    first_name:       str
    last_name:        str
    id_number:        Optional[str] = None
    tax_number:       Optional[str] = None
    date_of_birth:    Optional[str] = None
    appointment_date: Optional[str] = None
    address:          Optional[str] = None
    position:         Optional[str] = None
    department:       Optional[str] = None
    grade:            Optional[str] = None           # e.g. "A", "B2", "Senior"
    employment_type:  Optional[str] = "salaried"    # "salaried" | "hourly"
    hourly_rate:      Optional[float] = None         # explicit rate for hourly employees
    gross_salary:     float
    employee_number:  Optional[str] = None
    bank_name:                 Optional[str] = None
    bank_account:              Optional[str] = None
    account_number:            Optional[str] = None
    branch_code:               Optional[str] = None
    account_type:              Optional[str] = None
    start_date:                Optional[str] = None
    pension_fund_employee_pct: Optional[float] = 0.0
    pension_fund_employer_pct: Optional[float] = 0.0
    pension_employee_fixed:    Optional[float] = 0.0   # voluntary ZAR top-up on top of %-based contribution
    pension_employer_fixed:    Optional[float] = 0.0   # employer ZAR add-on on top of %-based contribution
    medical_aid_employee:      Optional[float] = 0.0
    medical_aid_employer:      Optional[float] = 0.0
    medical_aid_dependants:    Optional[int]   = 0
    # NBCPSS private security fields
    psira_number:              Optional[str]   = None
    security_grade:            Optional[str]   = None  # A, B, C, D, E
    security_area:             Optional[str]   = "1_2" # "1_2" = metro/urban, "3" = rural
    shift_type:                Optional[str]   = "day" # "day", "night", "rotating"
    special_allowance_type:    Optional[str]   = "none"
    # MIBCO Sector 5 fuel station fields
    mibco_role:                Optional[str]   = None  # "forecourt_attendant" | "cashier" | "char"
    mibco_scheme_enrolled:     Optional[bool]  = True  # False = opted out of health scheme
    union_subscription:        Optional[float] = 0.0   # monthly union dues (R) — after-tax deduction
    advance_monthly_deduction: Optional[float] = 0.0   # monthly salary advance repayment deduction
    on_maternity_leave:        Optional[bool]  = False  # True → gross zeroed; employee claims UIF maternity benefit
    sunday_ordinary:           Optional[bool]  = False  # True → Sunday is an ordinary working day: Sunday hours at 1.5x (BCEA s16(2))
    psspf_exempt:              Optional[bool]  = False  # True → NOT a PSSPF member (no automatic provident deduction)
    pay_schedule:              Optional[str]   = "salaried"  # "salaried" | "security"
    employment_category:       Optional[str]   = "permanent"  # "permanent"|"fixed_term"|"temp_labour"|"learnership"|"public_servant"|"foreign_national"

class EmployeeUpdate(BaseModel):
    model_config = {"extra": "ignore"}   # Pydantic v2: silently drop unknown fields
    first_name:                Optional[str] = None
    last_name:                 Optional[str] = None
    position:                  Optional[str] = None
    department:                Optional[str] = None
    grade:                     Optional[str] = None
    employment_type:           Optional[str] = None
    hourly_rate:               Optional[float] = None
    gross_salary:              Optional[float] = None
    tax_number:                Optional[str] = None
    id_number:                 Optional[str] = None
    date_of_birth:             Optional[str] = None
    appointment_date:          Optional[str] = None
    address:                   Optional[str] = None
    bank_name:                 Optional[str] = None
    bank_account:              Optional[str] = None
    account_number:            Optional[str] = None
    branch_code:               Optional[str] = None
    account_type:              Optional[str] = None
    is_active:                 Optional[bool] = None
    pension_fund_employee_pct: Optional[float] = None
    pension_fund_employer_pct: Optional[float] = None
    pension_employee_fixed:    Optional[float] = None
    pension_employer_fixed:    Optional[float] = None
    medical_aid_employee:      Optional[float] = None
    medical_aid_employer:      Optional[float] = None
    medical_aid_dependants:    Optional[int]   = None
    # NBCPSS private security fields
    psira_number:              Optional[str]   = None
    security_grade:            Optional[str]   = None
    security_area:             Optional[str]   = None
    shift_type:                Optional[str]   = None
    special_allowance_type:    Optional[str]   = None
    # MIBCO Sector 5 fuel station fields
    mibco_role:                Optional[str]   = None
    mibco_scheme_enrolled:     Optional[bool]  = None
    union_subscription:        Optional[float] = None  # monthly union dues (R)
    advance_monthly_deduction: Optional[float] = None  # monthly salary advance repayment
    on_maternity_leave:        Optional[bool]  = None  # True → gross zeroed this month
    sunday_ordinary:           Optional[bool]  = None  # True → Sunday hours at 1.5x
    psspf_exempt:              Optional[bool]  = None  # True → NOT a PSSPF member
    pay_schedule:              Optional[str]   = None  # "salaried" | "security"
    employment_category:       Optional[str]   = None  # "permanent"|"fixed_term"|"temp_labour"|"learnership"|"public_servant"|"foreign_national"


def _employee_dict(e: Employee, company_industry: str = None) -> dict:
    """Return employee as dict with bank fields decrypted."""
    from payroll import bcea_hourly_rate
    _is_sec_co = (company_industry or "").lower().replace(" ", "_").replace("-", "_") == "private_security"
    _has_grade  = bool(getattr(e, "security_grade", None))
    _stored_sch = getattr(e, "pay_schedule", None)
    # Derive schedule: explicit "casual" always wins (even at a security company
    # that might have some temp/casual workers alongside its officers).
    # security_grade presence also wins (grade implies officer).
    # Private-security company defaults to "security" for any non-salaried, non-casual employee.
    if _stored_sch == "casual":
        _derived_schedule = "casual"
    elif _has_grade or (_is_sec_co and _stored_sch not in ("salaried", "casual")):
        _derived_schedule = "security"
    else:
        _derived_schedule = _stored_sch or "salaried"
    return {
        "id": e.id, "company_id": e.company_id,
        "employee_number": e.employee_number,
        "first_name": e.first_name, "last_name": e.last_name,
        "id_number": e.id_number, "tax_number": e.tax_number,
        "date_of_birth": e.date_of_birth.isoformat() if e.date_of_birth else None,
        "appointment_date": e.appointment_date.isoformat() if e.appointment_date else None,
        "address": e.address, "position": e.position, "department": e.department,
        "grade": e.grade,
        "employment_type": e.employment_type or "salaried",
        "hourly_rate": e.hourly_rate,
        "hourly_rate_bcea": round(bcea_hourly_rate(e.gross_salary, e.hourly_rate), 4),
        "gross_salary": e.gross_salary,
        "bank_name":      decrypt_field(e.bank_name),
        "bank_account":   decrypt_field(e.bank_account),
        "account_number": decrypt_field(e.account_number),
        "branch_code":    decrypt_field(e.branch_code),
        "account_type": e.account_type,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "is_active": e.is_active,
        "pension_fund_employee_pct": getattr(e, "pension_fund_employee_pct", 0.0) or 0.0,
        "pension_fund_employer_pct": getattr(e, "pension_fund_employer_pct", 0.0) or 0.0,
        "pension_employee_fixed":    getattr(e, "pension_employee_fixed", 0.0) or 0.0,
        "pension_employer_fixed":    getattr(e, "pension_employer_fixed", 0.0) or 0.0,
        "medical_aid_employee":      getattr(e, "medical_aid_employee", 0.0) or 0.0,
        "medical_aid_employer":      getattr(e, "medical_aid_employer", 0.0) or 0.0,
        "medical_aid_dependants":    getattr(e, "medical_aid_dependants", 0) or 0,
        # NBCPSS private security
        "psira_number":           getattr(e, "psira_number", None),
        "security_grade":         getattr(e, "security_grade", None),
        "security_area":          getattr(e, "security_area", None) or "1_2",
        "shift_type":             getattr(e, "shift_type", None) or "day",
        "special_allowance_type": getattr(e, "special_allowance_type", None) or "none",
        # MIBCO Sector 5 fuel station
        "mibco_role":             getattr(e, "mibco_role", None),
        "mibco_scheme_enrolled":  bool(getattr(e, "mibco_scheme_enrolled", True)),
        "union_subscription":     getattr(e, "union_subscription", 0.0) or 0.0,
        "pay_schedule":           _derived_schedule,
        # Employment category + termination
        "employment_category": getattr(e, "employment_category", None) or "permanent",
        "termination_reason":  getattr(e, "termination_reason", None),
        "termination_date":    e.termination_date.isoformat() if getattr(e, "termination_date", None) else None,
        # General payroll adjustments
        "advance_monthly_deduction": getattr(e, "advance_monthly_deduction", 0.0) or 0.0,
        "on_maternity_leave":        bool(getattr(e, "on_maternity_leave", False)),
        "psspf_exempt":              bool(getattr(e, "psspf_exempt", False)),
        "sunday_ordinary":           bool(getattr(e, "sunday_ordinary", False)),
        "garnishee_orders": [
            {"id": g.id, "reference": g.reference, "amount": g.amount, "active": g.active}
            for g in getattr(e, "garnishee_orders", [])
        ],
    }


@employees_router.get("/")
async def list_employees(include_inactive: bool = False, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Employee).filter(Employee.company_id == current_user.company_id)
    if not include_inactive:
        q = q.filter(Employee.is_active == True)
    emps = q.all()
    _co = db.query(Company).filter(Company.id == current_user.company_id).first()
    _industry = _co.industry if _co else None
    return [_employee_dict(e, _industry) for e in emps]


@employees_router.post("/")
async def create_employee(data: EmployeeCreate, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    # Check payroll is enabled
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company.payroll_enabled:
        raise HTTPException(status_code=403, detail="Payroll module not enabled. Add it from Settings.")

    # Max-id seeded with collision check (scale fix 2026-07-03): count()+1
    # produced duplicate employee numbers after any employee was deleted.
    from sqlalchemy import func as _func
    _last = db.query(_func.max(Employee.id)).filter(Employee.company_id == current_user.company_id).scalar() or 0
    _existing = {
        row[0] for row in
        db.query(Employee.employee_number).filter(Employee.company_id == current_user.company_id).all()
    }
    _n = _last + 1
    _candidate = f"EMP-{str(_n).zfill(3)}"
    while _candidate in _existing:
        _n += 1
        _candidate = f"EMP-{str(_n).zfill(3)}"
    emp = Employee(
        company_id=current_user.company_id,
        employee_number=data.employee_number or _candidate,
        first_name=data.first_name,
        last_name=data.last_name,
        id_number=data.id_number,
        tax_number=data.tax_number,
        date_of_birth=datetime.fromisoformat(data.date_of_birth) if data.date_of_birth else None,
        appointment_date=datetime.fromisoformat(data.appointment_date) if data.appointment_date else None,
        address=data.address,
        position=data.position,
        department=data.department,
        grade=data.grade,
        employment_type=data.employment_type or "salaried",
        hourly_rate=data.hourly_rate,
        gross_salary=data.gross_salary,
        bank_name=encrypt_field(data.bank_name),
        bank_account=encrypt_field(data.bank_account),
        account_number=encrypt_field(data.account_number),
        branch_code=encrypt_field(data.branch_code),
        account_type=data.account_type,
        start_date=datetime.fromisoformat(data.start_date) if data.start_date else datetime.utcnow(),
        pension_fund_employee_pct=data.pension_fund_employee_pct or 0.0,
        pension_fund_employer_pct=data.pension_fund_employer_pct or 0.0,
        pension_employee_fixed=data.pension_employee_fixed or 0.0,
        pension_employer_fixed=data.pension_employer_fixed or 0.0,
        medical_aid_employee=data.medical_aid_employee or 0.0,
        medical_aid_employer=data.medical_aid_employer or 0.0,
        medical_aid_dependants=data.medical_aid_dependants or 0,
        psira_number=data.psira_number,
        security_grade=data.security_grade,
        security_area=data.security_area or "1_2",
        shift_type=data.shift_type or "day",
        special_allowance_type=data.special_allowance_type or "none",
        mibco_role=data.mibco_role or None,
        mibco_scheme_enrolled=data.mibco_scheme_enrolled if data.mibco_scheme_enrolled is not None else True,
        union_subscription=data.union_subscription or 0.0,
        advance_monthly_deduction=data.advance_monthly_deduction or 0.0,
        on_maternity_leave=data.on_maternity_leave or False,
        psspf_exempt=data.psspf_exempt or False,
        sunday_ordinary=data.sunday_ordinary or False,
        pay_schedule=data.pay_schedule or ("security" if data.security_grade else "salaried"),
        employment_category=data.employment_category or "permanent",
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _employee_dict(emp, company.industry)


_EMPLOYEE_BANK_FIELDS = {"bank_name", "bank_account", "account_number", "branch_code"}

@employees_router.put("/{employee_id}")
async def update_employee(employee_id: int, data: EmployeeUpdate, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id, Employee.company_id == current_user.company_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    _DATE_FIELDS = {"date_of_birth", "appointment_date"}
    for field, value in data.dict(exclude_none=True).items():
        if field in _DATE_FIELDS:
            setattr(emp, field, datetime.fromisoformat(value) if value else None)
        elif field in _EMPLOYEE_BANK_FIELDS:
            setattr(emp, field, encrypt_field(value))
        else:
            setattr(emp, field, value)
    db.commit()
    _co = db.query(Company).filter(Company.id == current_user.company_id).first()
    return _employee_dict(emp, _co.industry if _co else None)


# ── TERMINATE / REINSTATE ────────────────────────────────────────────────────

class TerminateRequest(BaseModel):
    reason: str      # UIF-standard reason code
    date:   Optional[str] = None  # ISO date string; defaults to today

# SA UIF termination reason codes (UI-19)
UIF_TERMINATION_REASONS = {
    "resignation":            "Resignation",
    "retrenchment":           "Retrenchment",
    "dismissal_misconduct":   "Dismissal — misconduct",
    "dismissal_performance":  "Dismissal — poor performance",
    "dismissal_operational":  "Dismissal — operational requirements",
    "retirement":             "Retirement",
    "death":                  "Death",
    "end_of_contract":        "End of fixed-term contract",
    "mutual_agreement":       "Mutual agreement",
    "ill_health":             "Ill health / incapacity",
}

@employees_router.post("/{employee_id}/terminate")
async def terminate_employee(
    employee_id: int,
    data: TerminateRequest,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == current_user.company_id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    # Validate the date BEFORE mutating the employee so a bad date changes nothing.
    try:
        term_date = datetime.fromisoformat(data.date) if data.date else datetime.utcnow()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date — use YYYY-MM-DD")
    emp.is_active = False
    emp.termination_reason = data.reason
    emp.termination_date = term_date
    db.commit()
    _co = db.query(Company).filter(Company.id == current_user.company_id).first()
    return _employee_dict(emp, _co.industry if _co else None)

@employees_router.post("/{employee_id}/reinstate")
async def reinstate_employee(
    employee_id: int,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == current_user.company_id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.is_active = True
    emp.termination_reason = None
    emp.termination_date = None
    db.commit()
    _co = db.query(Company).filter(Company.id == current_user.company_id).first()
    return _employee_dict(emp, _co.industry if _co else None)

# ── GARNISHEE ORDERS ──────────────────────────────────────────────────────────

class GarnisheeCreate(BaseModel):
    reference: str
    amount:    float

@employees_router.get("/{employee_id}/garnishees")
async def list_garnishees(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == current_user.company_id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    from database import EmployeeGarnishee
    orders = db.query(EmployeeGarnishee).filter(
        EmployeeGarnishee.employee_id == employee_id
    ).order_by(EmployeeGarnishee.id).all()
    return [{"id": g.id, "reference": g.reference, "amount": g.amount, "active": g.active} for g in orders]

@employees_router.post("/{employee_id}/garnishees")
async def add_garnishee(
    employee_id: int,
    data: GarnisheeCreate,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == current_user.company_id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    from database import EmployeeGarnishee
    g = EmployeeGarnishee(employee_id=employee_id, reference=data.reference, amount=data.amount, active=True)
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id, "reference": g.reference, "amount": g.amount, "active": g.active}

@employees_router.delete("/{employee_id}/garnishees/{garnishee_id}")
async def remove_garnishee(
    employee_id: int,
    garnishee_id: int,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == current_user.company_id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    from database import EmployeeGarnishee
    g = db.query(EmployeeGarnishee).filter(
        EmployeeGarnishee.id == garnishee_id,
        EmployeeGarnishee.employee_id == employee_id
    ).first()
    if not g:
        raise HTTPException(status_code=404, detail="Garnishee order not found")
    db.delete(g)
    db.commit()
    return {"deleted": garnishee_id}


# ── BANK STATEMENT IMPORT ─────────────────────────────────────────────────────
bank_router = APIRouter()

class BankTransaction(BaseModel):
    date:           str
    description:    str
    amount:         float           # VAT-inclusive amount as it appears on the bank statement
    type:           str             # debit or credit
    category:       Optional[str] = "Other"
    vat_applicable: bool  = False   # legacy field — kept for backwards compat
    has_vat:        bool  = False   # set True to split out VAT (15%) on import
    vat_amount:     float = 0.0     # pre-calculated VAT amount from frontend

class BankImportRequest(BaseModel):
    bank:         str
    transactions: list[BankTransaction]


def _name_tokens(name):
    import re as _re
    return [w for w in _re.split(r"[^a-z0-9]+", (name or "").lower()) if len(w) >= 4]


def _desc_names_client(desc, client_name):
    d = (desc or "").lower()
    return any(t in d for t in _name_tokens(client_name))

@bank_router.post("/import")
async def import_bank_statement(
    data: BankImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Import bank statement transactions into ZuZan.
    Debits  → saved as Expense records + journal entry (DR Expense / CR Bank).
    Credits → journal entry (DR Bank / CR Revenue) so income flows to P&L.
    """
    expenses_created  = 0
    expenses_skipped  = 0
    credits_recorded  = 0
    credits_skipped   = 0
    credits_matched   = 0
    ignored           = 0
    possible_matches  = []

    journal_engine.init_accounts(current_user.company_id, db)   # once, outside the per-line SAVEPOINTs (it commits)
    failed = []            # lines that could not be posted (rolled back individually via SAVEPOINT)
    for txn in data.transactions:
        try:
          with db.begin_nested():   # SAVEPOINT: one bad line must not discard or corrupt the rest of the import
              if txn.type not in ("debit", "credit") or not (txn.amount and txn.amount > 0):
                  ignored += 1          # zero/negative amounts or unknown type are never posted
                  continue
              if txn.type == "debit":
                  # Check for duplicate — same vendor, amount and date.
                  # Audit fix 2026-07-04: the previous filter compared txn.description against
                  # Expense.description, but imported expenses store the bank narrative in
                  # `vendor` and a fixed "Imported from ..." string in `description` — so the
                  # dedupe never matched and re-importing a statement duplicated every expense.
                  existing = db.query(Expense).filter(
                      Expense.company_id   == current_user.company_id,
                      Expense.vendor       == txn.description[:100],
                      Expense.amount       == txn.amount,
                      Expense.expense_date == datetime.fromisoformat(txn.date),
                  ).first()

                  if existing:
                      expenses_skipped += 1
                      continue

                  # Calculate VAT split if applicable (bank amount is VAT-inclusive).
                  # Audit fix 2026-07-04: the frontend sends `has_vat` + a precomputed
                  # `vat_amount` (never the legacy `vat_applicable`), so checking only
                  # vat_applicable dropped the VAT split on every imported expense —
                  # overstating P&L expenses and understating input VAT. Mirror the
                  # credit branch (journal.post_bank_income): honor either flag, prefer
                  # the provided vat_amount, and fall back to 15/115 back-calculation.
                  from journal import company_vat_registered as _vatreg
                  if (txn.has_vat or txn.vat_applicable) and _vatreg(db, current_user.company_id):
                      imp_vat   = round(float(txn.vat_amount or 0), 2)
                      if imp_vat <= 0:
                          imp_vat = round(txn.amount * 0.15 / 1.15, 2)  # back-calculate from incl-VAT
                      imp_total = txn.amount                            # store as-is (VAT-inclusive)
                  else:
                      imp_vat   = 0.0
                      imp_total = txn.amount

                  expense = Expense(
                      company_id   = current_user.company_id,
                      vendor       = txn.description[:100],
                      description  = f"Imported from {data.bank.upper()} statement",
                      amount       = imp_total,
                      vat_amount   = imp_vat,
                      category     = txn.category,
                      expense_date = datetime.fromisoformat(txn.date),
                  )
                  db.add(expense)
                  db.flush()  # get expense.id before journal post
                  try:
                      journal_engine.post_expense(expense, db)
                  except Exception as je:
                      logger.error(f"Journal post failed for bank import expense: {je}")
                      raise RuntimeError(f"journal entry failed: {je}")
                  expenses_created += 1

              elif txn.type == "credit":
                  # Duplicate check (audit fix 2026-07-04): credits previously had NO dedupe,
                  # so re-importing a statement re-posted the income journal entry and
                  # double-counted revenue in every report. Match on the exact fields
                  # post_bank_income writes: source, date, description, and the bank-debit
                  # line amount. The query autoflushes entries posted earlier in this same
                  # batch, so within-file duplicates are caught too. (Two genuinely identical
                  # credits — same day, description and amount — must be imported manually.)
                  from database import JournalEntry, JournalLine
                  from datetime import date as _date
                  dup_q = db.query(JournalEntry.id).join(
                      JournalLine, JournalLine.entry_id == JournalEntry.id
                  ).filter(
                      JournalEntry.company_id  == current_user.company_id,
                      JournalEntry.source      == "bank_import_income",
                      JournalEntry.description == f"Bank income — {txn.description}",
                      JournalLine.debit        == round(float(txn.amount or 0), 2),
                  )
                  try:
                      dup_q = dup_q.filter(JournalEntry.date == _date.fromisoformat(txn.date))
                  except Exception:
                      pass  # unparseable date — post_bank_income falls back to today; match on description+amount only
                  if dup_q.first():
                      credits_skipped += 1
                      continue

                  # Is this the payment of an invoice already raised in ZuZan? Posting it as new income
                  # would count the revenue twice and leave the invoice unpaid in Accounts Receivable.
                  if (txn.amount or 0) > 0:
                      _amt = round(float(txn.amount), 2)
                      try:
                          _txd = datetime.fromisoformat(txn.date)
                      except Exception:
                          _txd = datetime.utcnow()
                      # (a) already matched on an earlier import of the same statement -> duplicate
                      _paid = db.query(Invoice).filter(
                          Invoice.company_id == current_user.company_id,
                          Invoice.status == InvoiceStatus.paid,
                          Invoice.paid_amount_zar == _amt,
                          Invoice.paid_date >= _txd.replace(hour=0, minute=0, second=0, microsecond=0),
                          Invoice.paid_date <  _txd.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
                      ).all()
                      if any(_desc_names_client(txn.description, i.client_name) for i in _paid):
                          credits_skipped += 1
                          continue
                      # (b) one open ZAR invoice for exactly this total whose client is named in the narrative
                      _open = [i for i in db.query(Invoice).filter(
                                  Invoice.company_id == current_user.company_id,
                                  Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue, InvoiceStatus.partial])).all()
                               if (not i.currency or i.currency == "ZAR")
                               and abs((i.total_amount or 0) - (i.paid_amount_zar or 0 if i.status == InvoiceStatus.partial else 0) - _amt) < 0.005]
                      _named = [i for i in _open if _desc_names_client(txn.description, i.client_name)]
                      if len(_named) == 1:
                          _inv = _named[0]
                          _before = round(_inv.paid_amount_zar or 0, 2) if _inv.status == InvoiceStatus.partial else 0.0
                          _inv.status = InvoiceStatus.paid
                          _inv.paid_date = _txd
                          _inv.paid_amount_zar = round(_before + _amt, 2)
                          try:
                              _full = _inv.paid_amount_zar
                              _inv.paid_amount_zar = _amt            # post only what this deposit paid
                              journal_engine.post_invoice_paid(_inv, db)
                              _inv.paid_amount_zar = _full
                          except Exception as je:
                              logger.error(f"Journal post failed for bank-matched invoice payment: {je}")
                              raise RuntimeError(f"journal entry failed: {je}")
                          credits_matched += 1
                          continue
                      if _open:
                          possible_matches.append({"description": txn.description, "amount": _amt, "date": txn.date,
                                                   "possible_invoices": [i.invoice_number for i in _open]})

                  # Post a journal entry so income flows into P&L and the balance sheet
                  try:
                      journal_engine.post_bank_income(current_user.company_id, txn, db)
                      credits_recorded += 1
                  except Exception as je:
                      logger.error(f"Journal post failed for bank import income: {je}")
                      raise RuntimeError(f"journal entry failed: {je}")
        except Exception as _le:
            logger.error(f"Bank import line failed and was rolled back: {txn.description!r}: {_le}")
            failed.append({"description": txn.description, "amount": txn.amount, "date": txn.date, "error": str(_le)})

    db.commit()

    return {
        "status":           "success",
        "bank":             data.bank,
        "expenses_created": expenses_created,
        "expenses_skipped": expenses_skipped,
        "credits_recorded": credits_recorded,
        "credits_skipped":  credits_skipped,
        "credits_matched_to_invoices": credits_matched,
        "ignored":          ignored,
        "possible_invoice_matches": possible_matches,
        "failed":           failed,
        "total_processed":  len(data.transactions),
        "message":          (f"Imported {expenses_created} expenses and {credits_recorded} income entries; "
                             f"{credits_matched} receipts matched to open invoices and marked paid"
                             + (f"; {len(possible_matches)} receipt(s) have the same amount as an open invoice but the client is not named - check they are not invoice payments recorded twice (they were posted as new income)" if possible_matches else "")
                             + (f"; {ignored} line(s) ignored (zero/negative amount)" if ignored else "")
                             + (f"; {len(failed)} line(s) could NOT be posted and were skipped - nothing partial was saved for them; fix and re-import (duplicates are skipped automatically)" if failed else "") + "."),
    }
