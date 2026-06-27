"""
ZuZan — Double-Entry Journal Engine
Every financial event produces balanced debit/credit pairs.
Posting functions are called by invoice, expense, payroll and PO endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import (
    get_db, Account, AccountType, JournalEntry, JournalLine,
    Invoice, Expense, Payslip, Employee, PurchaseOrder, Company, InvoiceStatus,
    FixedAsset, DepreciationEntry,
)
from auth import get_current_user, User

router = APIRouter()

# ── DEFAULT CHART OF ACCOUNTS ─────────────────────────────────────────────────
# SA-standard account codes. Created once per company on first use.
DEFAULT_ACCOUNTS = [
    # Assets
    {"code": "1000", "name": "Bank / Cash",                  "type": AccountType.asset},
    {"code": "1100", "name": "Accounts Receivable",          "type": AccountType.asset},
    {"code": "1200", "name": "Inventory at Cost",            "type": AccountType.asset},
    {"code": "1300", "name": "VAT Input (Recoverable)",      "type": AccountType.asset},
    # Liabilities
    {"code": "2000", "name": "Accounts Payable",             "type": AccountType.liability},
    {"code": "2100", "name": "VAT Output (Payable to SARS)", "type": AccountType.liability},
    {"code": "2200", "name": "PAYE Payable",                 "type": AccountType.liability},
    {"code": "2210", "name": "UIF Payable",                  "type": AccountType.liability},
    {"code": "2220", "name": "SDL Payable",                  "type": AccountType.liability},
    # Equity
    {"code": "3000", "name": "Retained Income",              "type": AccountType.equity},
    # Revenue
    {"code": "4000", "name": "Sales Revenue",                "type": AccountType.revenue},
    # Expenses
    {"code": "5000", "name": "Cost of Sales",                "type": AccountType.expense},
    {"code": "5100", "name": "Salaries (Gross)",             "type": AccountType.expense},
    {"code": "5110", "name": "Payroll Levies (UIF/SDL)",     "type": AccountType.expense},
    {"code": "5200", "name": "Utilities",                    "type": AccountType.expense},
    {"code": "5210", "name": "Telecoms",                     "type": AccountType.expense},
    {"code": "5220", "name": "Office Expenses",              "type": AccountType.expense},
    {"code": "5230", "name": "Banking Charges",              "type": AccountType.expense},
    {"code": "5240", "name": "Insurance",                    "type": AccountType.expense},
    {"code": "5250", "name": "Tax",                          "type": AccountType.expense},
    {"code": "5260", "name": "Equipment",                    "type": AccountType.expense},
    {"code": "5270", "name": "Travel",                       "type": AccountType.expense},
    {"code": "5280", "name": "Rent",                         "type": AccountType.expense},
    {"code": "5290", "name": "Marketing",                    "type": AccountType.expense},
    {"code": "5300", "name": "Professional Fees",            "type": AccountType.expense},
    {"code": "5900", "name": "General Expenses",             "type": AccountType.expense},
    {"code": "5950", "name": "Stock Adjustments",            "type": AccountType.expense},
    # Fixed Assets (IAS 16)
    {"code": "1500", "name": "Fixed Assets at Cost",         "type": AccountType.asset},
    {"code": "1510", "name": "Accumulated Depreciation",     "type": AccountType.asset},   # contra-asset (credit normal balance)
    {"code": "5800", "name": "Depreciation Expense",         "type": AccountType.expense},
    {"code": "4900", "name": "Gain on Disposal of Assets",   "type": AccountType.revenue},
    {"code": "6800", "name": "Loss on Disposal of Assets",   "type": AccountType.expense},
]

# Maps expense categories to account codes
CATEGORY_TO_CODE = {
    "Cost of Sales":    "5000",
    "Salaries":         "5100",
    "Utilities":        "5200",
    "Telecoms":         "5210",
    "Office":           "5220",
    "Banking":          "5230",
    "Insurance":        "5240",
    "Tax":              "5250",
    "Equipment":        "5260",
    "Travel":           "5270",
    "Rent":             "5280",
    "Marketing":        "5290",
    "Professional Fees":"5300",
}


# ── HELPERS ───────────────────────────────────────────────────────────────────

def init_accounts(company_id: int, db: Session) -> None:
    """
    Upsert the default chart of accounts for a company.
    Checks per account code so new accounts added to DEFAULT_ACCOUNTS
    are created for existing companies on the next transaction.
    """
    existing_codes = {
        row[0] for row in
        db.query(Account.code).filter(Account.company_id == company_id).all()
    }
    for acct in DEFAULT_ACCOUNTS:
        if acct["code"] not in existing_codes:
            db.add(Account(
                company_id=company_id,
                code=acct["code"],
                name=acct["name"],
                type=acct["type"],
                is_system=True,
            ))
    db.commit()


def get_account(company_id: int, code: str, db: Session) -> Account:
    """Fetch account by code; raises if missing."""
    acct = db.query(Account).filter(
        Account.company_id == company_id,
        Account.code == code,
        Account.is_active == True,
    ).first()
    if not acct:
        raise ValueError(f"Account {code} not found for company {company_id}. Run /journal/init-accounts first.")
    return acct


def expense_account(company_id: int, category: str, db: Session) -> Account:
    """Resolve expense category → account, falling back to General Expenses."""
    code = CATEGORY_TO_CODE.get(category or "", "5900")
    acct = db.query(Account).filter(Account.company_id==company_id, Account.code==code).first()
    if not acct:
        acct = get_account(company_id, "5900", db)
    return acct


def _make_entry(company_id, date, description, reference, source, source_id, db) -> JournalEntry:
    entry = JournalEntry(
        company_id=company_id,
        date=date,
        description=description,
        reference=reference,
        source=source,
        source_id=source_id,
    )
    db.add(entry)
    db.flush()   # get entry.id
    return entry


def _line(entry_id, account: Account, debit=0, credit=0, description=None):
    return JournalLine(
        entry_id=entry_id,
        account_id=account.id,
        debit=round(debit, 2),
        credit=round(credit, 2),
        description=description,
    )


def _assert_balanced(lines):
    total_dr = round(sum(l.debit  for l in lines), 2)
    total_cr = round(sum(l.credit for l in lines), 2)
    if abs(total_dr - total_cr) > 0.01:
        raise ValueError(f"Journal entry is unbalanced: DR {total_dr} ≠ CR {total_cr}")


# ── POSTING FUNCTIONS ─────────────────────────────────────────────────────────

def post_invoice_raised(invoice, db: Session) -> JournalEntry:
    """
    Invoice sent to client:
      DR Accounts Receivable   (total incl VAT, ZAR equivalent)
      CR Sales Revenue         (amount excl VAT, ZAR equivalent)
      CR VAT Output Payable    (vat_amount, ZAR equivalent)

    All amounts are converted to ZAR before posting so that the AR control
    account (1100) is always denominated in ZAR.  For non-ZAR invoices the
    exchange_rate stored on the invoice is used; this is the same rate that
    _to_zar() applies in the reports layer, ensuring consistency.
    """
    cid = invoice.company_id
    lines = []
    entry = _make_entry(cid, invoice.issue_date or datetime.utcnow(),
        f"Invoice raised — {invoice.client_name}",
        invoice.invoice_number, "invoice", invoice.id, db)

    ar  = get_account(cid, "1100", db)
    rev = get_account(cid, "4000", db)
    vat = get_account(cid, "2100", db)

    # Convert to ZAR — foreign-currency invoices multiply by exchange_rate so
    # that account 1100 (AR) is always in ZAR.  ZAR invoices are used as-is.
    is_foreign = bool(invoice.currency and invoice.currency != "ZAR")
    rate        = float(invoice.exchange_rate or 1.0) if is_foreign else 1.0
    total_zar   = round((invoice.total_amount or 0) * rate, 2)
    amount_zar  = round((invoice.amount       or 0) * rate, 2)
    vat_zar     = round((invoice.vat_amount   or 0) * rate, 2)

    lines.append(_line(entry.id, ar,  debit=total_zar,  description=invoice.invoice_number))
    lines.append(_line(entry.id, rev, credit=amount_zar, description="Revenue excl VAT"))
    if vat_zar:
        lines.append(_line(entry.id, vat, credit=vat_zar, description="VAT output"))

    _assert_balanced(lines)
    for l in lines: db.add(l)
    return entry


def post_invoice_paid(invoice, db: Session) -> JournalEntry:
    """
    Invoice paid by client:
      DR Bank / Cash           (total incl VAT)
      CR Accounts Receivable   (total incl VAT)
    """
    cid = invoice.company_id
    entry = _make_entry(cid, invoice.paid_date or datetime.utcnow(),
        f"Payment received — {invoice.client_name}",
        invoice.invoice_number, "invoice_payment", invoice.id, db)

    bank = get_account(cid, "1000", db)
    ar   = get_account(cid, "1100", db)

    # For foreign-currency invoices use the ZAR amount actually received.
    # Fall back chain (both sides must use the same value to stay balanced):
    #   1. paid_amount_zar  — exact ZAR received, set by the mark-as-paid UI
    #   2. total_amount × exchange_rate — estimated ZAR for non-ZAR invoices
    #   3. total_amount — ZAR invoices (exchange_rate == 1)
    if invoice.paid_amount_zar:
        zar_received = invoice.paid_amount_zar
    elif invoice.currency and invoice.currency != "ZAR":
        zar_received = round((invoice.total_amount or 0) * float(invoice.exchange_rate or 1.0), 2)
    else:
        zar_received = invoice.total_amount or 0
    lines = [
        _line(entry.id, bank, debit=zar_received,  description="Cash received"),
        _line(entry.id, ar,   credit=zar_received, description=invoice.invoice_number),
    ]
    _assert_balanced(lines)
    for l in lines: db.add(l)
    return entry


def post_invoice_cogs(invoice, cogs_amount: float, db: Session) -> JournalEntry:
    """
    Record Cost of Goods Sold when an invoice is raised for inventory items:
      DR Cost of Sales (5000)      (cogs_amount)
      CR Inventory at Cost (1200)  (cogs_amount)
    Call after post_invoice_raised. cogs_amount should be the total cost price of goods sold.
    """
    cid = invoice.company_id
    cogs_amount = round(cogs_amount, 2)
    entry = _make_entry(cid, invoice.issue_date or datetime.utcnow(),
        f"COGS — {invoice.client_name} ({invoice.invoice_number})",
        invoice.invoice_number, "invoice_cogs", invoice.id, db)

    cogs_acct = get_account(cid, "5000", db)
    inventory  = get_account(cid, "1200", db)

    lines = [
        _line(entry.id, cogs_acct, debit=cogs_amount,  description="Cost of goods sold"),
        _line(entry.id, inventory, credit=cogs_amount, description=invoice.invoice_number),
    ]
    _assert_balanced(lines)
    for l in lines: db.add(l)
    return entry


def post_expense(expense, db: Session) -> JournalEntry:
    """
    Expense incurred:
      DR Expense Account       (amount excl VAT)
      DR VAT Input Recoverable (vat_amount)
      CR Bank / Cash           (total)   — when expense.is_on_credit is False (default)
      CR Accounts Payable      (total)   — when expense.is_on_credit is True
                                            (purchase on credit, not yet cash-paid)
    """
    cid   = expense.company_id
    total = round((expense.amount or 0), 2)
    vat   = round((expense.vat_amount or 0), 2)
    net   = round(total - vat, 2)

    on_credit = getattr(expense, "is_on_credit", False) or False

    entry = _make_entry(cid, expense.expense_date or datetime.utcnow(),
        f"Expense — {expense.vendor}: {expense.description or ''}",
        f"EXP-{expense.id}", "expense", expense.id, db)

    exp_acct    = expense_account(cid, expense.category, db)
    vat_in      = get_account(cid, "1300", db)
    credit_acct = get_account(cid, "2000" if on_credit else "1000", db)
    credit_desc = "On credit (AP)" if on_credit else "Cash paid"

    lines = [_line(entry.id, exp_acct, debit=net, description=expense.category)]
    if vat > 0:
        lines.append(_line(entry.id, vat_in, debit=vat, description="VAT input"))
    lines.append(_line(entry.id, credit_acct, credit=total, description=credit_desc))

    _assert_balanced(lines)
    for l in lines: db.add(l)
    return entry


def post_payroll(payslip, employee, db: Session) -> JournalEntry:
    """
    Payroll run for one employee:
      DR Salaries (Gross)      (gross_salary)
      DR Payroll Levies        (uif_employer + sdl)
      CR PAYE Payable          (paye)
      CR UIF Payable           (uif_employee + uif_employer)
      CR SDL Payable           (sdl)
      CR Bank / Cash           (net_pay)
    """
    cid = employee.company_id
    entry = _make_entry(cid, payslip.generated_at or datetime.utcnow(),
        f"Payroll — {employee.first_name} {employee.last_name} {payslip.period}",
        f"PAY-{payslip.id}", "payroll", payslip.id, db)

    sal   = get_account(cid, "5100", db)
    levy  = get_account(cid, "5110", db)
    paye_acct = get_account(cid, "2200", db)
    uif_acct  = get_account(cid, "2210", db)
    sdl_acct  = get_account(cid, "2220", db)
    bank  = get_account(cid, "1000", db)

    employer_contrib = round((payslip.uif_employer or 0) + (payslip.sdl or 0), 2)

    lines = [
        _line(entry.id, sal,  debit=payslip.gross_salary,                        description="Gross salary"),
        _line(entry.id, levy, debit=employer_contrib,                             description="Employer UIF + SDL"),
        _line(entry.id, paye_acct, credit=round(payslip.paye or 0, 2),           description="PAYE to SARS"),
        _line(entry.id, uif_acct,  credit=round((payslip.uif_employee or 0) + (payslip.uif_employer or 0), 2), description="UIF"),
        _line(entry.id, sdl_acct,  credit=round(payslip.sdl or 0, 2),            description="SDL"),
        _line(entry.id, bank,      credit=round(payslip.net_pay or 0, 2),        description="Net pay"),
    ]
    _assert_balanced(lines)
    for l in lines: db.add(l)
    return entry


def post_po_received(po, db: Session) -> JournalEntry:
    """
    Purchase order received (goods/services delivered, not yet paid):
      DR Cost of Sales (5000)      (amount excl VAT)
      DR VAT Input Recoverable     (vat_amount)
      CR Accounts Payable          (total_amount)

    Design note: PO costs are expensed immediately on receipt (matching the
    direct-query P&L in /reports/dashboard) rather than routed through
    Inventory (1200). Physical stock levels are tracked separately via the
    InventoryItem table. This keeps the journal P&L consistent with the
    dashboard figures shown to users.
    """
    cid = po.company_id
    total = round(po.total_amount or 0, 2)
    vat   = round(po.vat_amount   or 0, 2)
    net   = round(total - vat, 2)

    entry = _make_entry(cid, po.received_date or datetime.utcnow(),
        f"PO received — {po.supplier_name or 'Supplier'}",
        po.po_number, "purchase_order", po.id, db)

    cogs   = get_account(cid, "5000", db)
    vat_in = get_account(cid, "1300", db)
    ap     = get_account(cid, "2000", db)

    lines = [_line(entry.id, cogs, debit=net,      description="Goods/services received")]
    if vat > 0:
        lines.append(_line(entry.id, vat_in, debit=vat, description="VAT input"))
    lines.append(_line(entry.id, ap, credit=total, description=po.po_number))

    _assert_balanced(lines)
    for l in lines: db.add(l)
    return entry


def post_po_paid(po, db: Session) -> JournalEntry:
    """
    Supplier invoice paid:
      DR Accounts Payable   (total_amount)
      CR Bank / Cash        (total_amount)
    """
    cid = po.company_id
    total = round(po.total_amount or 0, 2)
    entry = _make_entry(cid, datetime.utcnow(),
        f"Supplier payment — {po.supplier_name or 'Supplier'}",
        po.po_number, "po_payment", po.id, db)

    ap   = get_account(cid, "2000", db)
    bank = get_account(cid, "1000", db)

    lines = [
        _line(entry.id, ap,   debit=total,  description=po.po_number),
        _line(entry.id, bank, credit=total, description="Cash paid"),
    ]
    _assert_balanced(lines)
    for l in lines: db.add(l)
    return entry


def post_stock_adjustment(item, quantity: float, db: Session, reason: str = None) -> JournalEntry:
    """
    Direct stock adjustment:
      Positive (stock in):  DR Inventory at Cost (1200) / CR Stock Adjustments (5950)
      Negative (stock out): DR Stock Adjustments (5950)  / CR Inventory at Cost (1200)
    No entry is posted if unit_cost is zero (no financial impact).
    """
    cid = item.company_id
    amount = round(abs(quantity) * (item.unit_cost or 0), 2)
    if amount == 0:
        return None  # Zero-cost item — no ledger entry needed

    entry = _make_entry(
        cid, datetime.utcnow(),
        f"Stock adjustment — {item.name} ({'+'  if quantity > 0 else ''}{quantity} {item.unit_of_measure or 'units'})",
        f"ADJ-{item.id}", "stock_adjustment", item.id, db,
    )

    inventory = get_account(cid, "1200", db)
    adj_acct  = get_account(cid, "5950", db)
    desc = reason or ("Stock in" if quantity > 0 else "Stock write-off")

    if quantity > 0:
        lines = [
            _line(entry.id, inventory, debit=amount,  description=desc),
            _line(entry.id, adj_acct,  credit=amount, description=desc),
        ]
    else:
        lines = [
            _line(entry.id, adj_acct,  debit=amount,  description=desc),
            _line(entry.id, inventory, credit=amount, description=desc),
        ]

    _assert_balanced(lines)
    for l in lines:
        db.add(l)
    return entry


# ── FIXED ASSET POSTING FUNCTIONS (IAS 16) ───────────────────────────────────

def post_asset_acquisition(asset, db: Session) -> JournalEntry:
    """
    Record purchase of a fixed asset (cost model, IAS 16.15):
      DR Fixed Assets at Cost  (1500)   full cost
      CR Bank / Cash           (1000)   full cost
    """
    cid = asset.company_id
    init_accounts(cid, db)
    cost = round(asset.cost, 2)
    entry = _make_entry(
        cid, asset.purchase_date,
        f"Asset acquisition — {asset.asset_name}",
        asset.asset_number or f"FA-{asset.id}", "fixed_asset", asset.id, db,
    )
    fa_acct   = get_account(cid, "1500", db)
    bank_acct = get_account(cid, "1000", db)
    lines = [
        _line(entry.id, fa_acct,   debit=cost,  description=asset.asset_name),
        _line(entry.id, bank_acct, credit=cost, description=asset.asset_name),
    ]
    _assert_balanced(lines)
    for l in lines:
        db.add(l)
    return entry


def post_depreciation(asset, amount: float, period: str, db: Session) -> JournalEntry:
    """
    Monthly depreciation charge (IAS 16.48):
      DR Depreciation Expense   (5800)   amount
      CR Accumulated Depreciation (1510) amount
    """
    cid = asset.company_id
    init_accounts(cid, db)
    amount = round(amount, 2)
    entry = _make_entry(
        cid, datetime.utcnow(),
        f"Depreciation — {asset.asset_name} [{period}]",
        f"DEP-{asset.id}-{period}", "depreciation", asset.id, db,
    )
    depr_exp  = get_account(cid, "5800", db)
    accum_dep = get_account(cid, "1510", db)
    # Accumulated depreciation is a contra-asset: credit increases it
    lines = [
        _line(entry.id, depr_exp,  debit=amount,  description=f"Depreciation {period}"),
        _line(entry.id, accum_dep, credit=amount, description=asset.asset_name),
    ]
    _assert_balanced(lines)
    for l in lines:
        db.add(l)
    return entry


def post_asset_disposal(asset, proceeds: float, db: Session) -> JournalEntry:
    """
    Derecognise a fixed asset on disposal or write-off (IAS 16.67-72):
      DR Accumulated Depreciation  (1510)  accumulated_depreciation
      DR Bank / Cash               (1000)  proceeds (0 if write-off)
      DR Loss on Disposal          (6800)  if carrying_value > proceeds
      CR Fixed Assets at Cost      (1500)  original cost
      CR Gain on Disposal          (4900)  if proceeds > carrying_value
    """
    cid            = asset.company_id
    init_accounts(cid, db)
    cost           = round(asset.cost, 2)
    accum_depr     = round(asset.accumulated_depreciation, 2)
    carrying_value = round(max(0, cost - accum_depr), 2)
    proceeds       = round(proceeds or 0, 2)
    gain_loss      = round(proceeds - carrying_value, 2)  # positive = gain, negative = loss

    entry = _make_entry(
        cid, datetime.utcnow(),
        f"Asset disposal — {asset.asset_name}",
        asset.asset_number or f"FA-{asset.id}", "asset_disposal", asset.id, db,
    )

    fa_acct   = get_account(cid, "1500", db)
    accum_acc = get_account(cid, "1510", db)
    bank_acct = get_account(cid, "1000", db)

    lines = [
        # Remove accumulated depreciation (debit contra-asset to close it)
        _line(entry.id, accum_acc, debit=accum_depr, description="Remove accumulated depreciation"),
        # Remove asset at cost (credit to close the asset account)
        _line(entry.id, fa_acct,   credit=cost,      description="Remove asset at cost"),
    ]

    if proceeds > 0:
        lines.append(_line(entry.id, bank_acct, debit=proceeds, description="Disposal proceeds"))

    if gain_loss > 0:
        gain_acc = get_account(cid, "4900", db)
        lines.append(_line(entry.id, gain_acc, credit=gain_loss, description="Gain on disposal"))
    elif gain_loss < 0:
        loss_acc = get_account(cid, "6800", db)
        lines.append(_line(entry.id, loss_acc, debit=abs(gain_loss), description="Loss on disposal"))

    _assert_balanced(lines)
    for l in lines:
        db.add(l)
    return entry


# ── BACKFILL ──────────────────────────────────────────────────────────────────

def backfill_company(company_id: int, db: Session) -> dict:
    """
    Convert all existing transactions for a company into journal entries.
    Safe to run multiple times — skips records that already have a journal entry.
    """
    init_accounts(company_id, db)

    posted   = {"invoices": 0, "invoice_payments": 0, "expenses": 0, "payroll": 0, "purchase_orders": 0, "errors": []}
    existing = {(e.source, e.source_id) for e in
                db.query(JournalEntry.source, JournalEntry.source_id)
                  .filter(JournalEntry.company_id == company_id).all()}

    # Invoices raised
    for inv in db.query(Invoice).filter(Invoice.company_id == company_id).all():
        if ("invoice", inv.id) not in existing:
            try:
                post_invoice_raised(inv, db)
                posted["invoices"] += 1
            except Exception as e:
                posted["errors"].append(f"Invoice {inv.invoice_number}: {e}")

    # Invoice payments
    for inv in db.query(Invoice).filter(Invoice.company_id == company_id, Invoice.status == InvoiceStatus.paid).all():
        if ("invoice_payment", inv.id) not in existing:
            try:
                post_invoice_paid(inv, db)
                posted["invoice_payments"] += 1
            except Exception as e:
                posted["errors"].append(f"Invoice payment {inv.invoice_number}: {e}")

    # Expenses
    for exp in db.query(Expense).filter(Expense.company_id == company_id).all():
        if ("expense", exp.id) not in existing:
            try:
                post_expense(exp, db)
                posted["expenses"] += 1
            except Exception as e:
                posted["errors"].append(f"Expense {exp.id}: {e}")

    # Payroll
    for ps in db.query(Payslip).join(Employee).filter(Employee.company_id == company_id).all():
        if ("payroll", ps.id) not in existing:
            try:
                emp = db.query(Employee).filter(Employee.id == ps.employee_id).first()
                post_payroll(ps, emp, db)
                posted["payroll"] += 1
            except Exception as e:
                posted["errors"].append(f"Payslip {ps.id}: {e}")

    # Purchase orders received (received, partial, and paid — all had goods delivered)
    for po in db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id == company_id,
        PurchaseOrder.status.in_(["received", "partial", "paid"])
    ).all():
        if ("purchase_order", po.id) not in existing:
            try:
                post_po_received(po, db)
                posted["purchase_orders"] += 1
            except Exception as e:
                posted["errors"].append(f"PO {po.po_number} receive: {e}")

    # Purchase orders paid — post the AP clearance entry for fully paid POs
    for po in db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id == company_id,
        PurchaseOrder.status == "paid"
    ).all():
        if ("po_payment", po.id) not in existing:
            try:
                post_po_paid(po, db)
                posted["purchase_orders"] += 1
            except Exception as e:
                posted["errors"].append(f"PO {po.po_number} payment: {e}")

    # Fixed asset acquisitions — one journal entry per asset (DR Fixed Assets / CR Bank)
    posted["fixed_assets"] = 0
    # Build a set of already-posted depreciation references once for the whole company
    # (avoids re-querying inside the per-asset loop).
    existing_depr_refs = {
        row.reference for row in
        db.query(JournalEntry.reference).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.source == "depreciation",
        ).all()
    }
    for asset in db.query(FixedAsset).filter(FixedAsset.company_id == company_id).all():
        if ("fixed_asset", asset.id) not in existing:
            try:
                post_asset_acquisition(asset, db)
                posted["fixed_assets"] += 1
            except Exception as e:
                posted["errors"].append(f"Asset {asset.asset_number or asset.id} acquisition: {e}")
        # Depreciation entries — deduplicate by reference "DEP-{asset_id}-{period}" since
        # multiple periods share the same source_id (asset.id)
        existing_refs = existing_depr_refs  # use company-wide set; updated in-place below
        for depr in asset.depreciation_entries:
            ref = f"DEP-{asset.id}-{depr.period}"
            if ref not in existing_refs:
                try:
                    post_depreciation(asset, depr.amount, depr.period, db)
                    existing_depr_refs.add(ref)   # prevent double-post within this backfill run
                    posted["fixed_assets"] += 1
                except Exception as e:
                    posted["errors"].append(f"Depreciation {ref}: {e}")
        # Asset disposals
        if asset.status in ("disposed", "written_off") and ("asset_disposal", asset.id) not in existing:
            try:
                post_asset_disposal(asset, asset.disposal_proceeds or 0, db)
                posted["fixed_assets"] += 1
            except Exception as e:
                posted["errors"].append(f"Asset {asset.asset_number or asset.id} disposal: {e}")

    db.commit()
    return posted


# ── REVERSAL HELPER ──────────────────────────────────────────────────────────

def _post_reversal_for_entry(entry: JournalEntry, db: Session, reason: str = None) -> JournalEntry:
    """
    Post a single reversal entry that mirrors `entry` with debits/credits swapped.
    Sets `is_reversal_of` on the new entry so the pair can be linked in the UI.
    Internal helper — callers commit after this returns.
    """
    rev = JournalEntry(
        company_id    = entry.company_id,
        date          = datetime.utcnow(),
        description   = reason or f"Reversal — {entry.description}",
        reference     = f"REV-{entry.reference or entry.id}",
        source        = f"{entry.source}_reversal",
        source_id     = entry.source_id,
        is_reversal_of= entry.id,
    )
    db.add(rev)
    db.flush()
    for line in entry.lines:
        db.add(JournalLine(
            entry_id    = rev.id,
            account_id  = line.account_id,
            debit       = line.credit,   # swap
            credit      = line.debit,    # swap
            description = f"Reversal of line {line.id}",
        ))
    return rev


def reverse_journal_entries(
    company_id: int,
    source: str,
    source_id: int,
    db: Session,
    reason: str = None,
) -> int:
    """
    Post reversal entries for every JournalEntry matching (company_id, source, source_id).
    Skips entries that have already been reversed (is_reversal_of pointing at them exists).
    Returns the count of entries reversed.
    """
    entries = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source     == source,
        JournalEntry.source_id  == source_id,
    ).all()

    already_reversed = {
        row.is_reversal_of for row in
        db.query(JournalEntry.is_reversal_of).filter(
            JournalEntry.company_id    == company_id,
            JournalEntry.is_reversal_of.isnot(None),
        ).all()
    }

    count = 0
    for entry in entries:
        if entry.id in already_reversed:
            continue
        _post_reversal_for_entry(entry, db, reason=reason)
        count += 1
    return count


def reverse_entry_by_id(entry_id: int, db: Session, reason: str = None) -> JournalEntry:
    """
    Post a reversal for a single JournalEntry identified by its primary key.
    Raises ValueError if the entry is not found or has already been reversed.
    """
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if not entry:
        raise ValueError(f"JournalEntry {entry_id} not found")
    already = db.query(JournalEntry).filter(
        JournalEntry.is_reversal_of == entry_id
    ).first()
    if already:
        raise ValueError(f"JournalEntry {entry_id} has already been reversed (reversal entry: {already.id})")
    return _post_reversal_for_entry(entry, db, reason=reason)


def process_pending_reversals(company_id: int, db: Session) -> list[int]:
    """
    Find all journal entries for `company_id` where:
      - auto_reverse is True
      - reversal_date <= now (due to be reversed)
      - no reversal entry exists yet (is_reversal_of not yet posted)

    Posts the reversal for each and returns a list of the original entry IDs processed.
    Safe to call repeatedly — already-reversed entries are skipped.
    """
    now = datetime.utcnow()

    due = db.query(JournalEntry).filter(
        JournalEntry.company_id   == company_id,
        JournalEntry.auto_reverse == True,          # noqa: E712
        JournalEntry.reversal_date.isnot(None),
        JournalEntry.reversal_date <= now,
    ).all()

    already_reversed = {
        row.is_reversal_of for row in
        db.query(JournalEntry.is_reversal_of).filter(
            JournalEntry.company_id    == company_id,
            JournalEntry.is_reversal_of.isnot(None),
        ).all()
    }

    processed = []
    for entry in due:
        if entry.id in already_reversed:
            continue
        _post_reversal_for_entry(
            entry, db,
            reason=f"Auto-reversal — {entry.description}",
        )
        processed.append(entry.id)

    if processed:
        db.commit()

    return processed


# ── ACCOUNT BALANCE HELPER ────────────────────────────────────────────────────

def account_balance(account: Account, db: Session) -> float:
    """
    Normal balance convention:
      Assets & Expenses:           balance = debits − credits  (debit-normal)
      Liabilities, Equity, Revenue: balance = credits − debits  (credit-normal)
    """
    lines = db.query(JournalLine).filter(JournalLine.account_id == account.id).all()
    total_dr = sum(l.debit  for l in lines)
    total_cr = sum(l.credit for l in lines)
    if account.type in (AccountType.asset, AccountType.expense):
        return round(total_dr - total_cr, 2)
    else:
        return round(total_cr - total_dr, 2)


# ── API ENDPOINTS ─────────────────────────────────────────────────────────────

@router.post("/init-accounts")
async def init_accounts_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create default chart of accounts for the current company."""
    init_accounts(current_user.company_id, db)
    accounts = db.query(Account).filter(Account.company_id == current_user.company_id).count()
    return {"message": f"Chart of accounts ready ({accounts} accounts)"}


@router.post("/backfill")
async def backfill_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Backfill all existing transactions into the journal. Safe to re-run."""
    result = backfill_company(current_user.company_id, db)
    return {"status": "ok", "posted": result}


@router.get("/")
async def list_journal(
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(JournalEntry).filter(JournalEntry.company_id == current_user.company_id)
    if source:
        q = q.filter(JournalEntry.source == source)
    entries = q.order_by(JournalEntry.date.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id":            e.id,
            "date":          e.date.strftime("%Y-%m-%d"),
            "description":   e.description,
            "reference":     e.reference,
            "source":        e.source,
            "is_reconciled": e.is_reconciled,
            "auto_reverse":  getattr(e, "auto_reverse", False) or False,
            "reversal_date": e.reversal_date.strftime("%Y-%m-%d") if getattr(e, "reversal_date", None) else None,
            "is_reversal_of":getattr(e, "is_reversal_of", None),
            "lines": [
                {
                    "account_code": l.account.code,
                    "account_name": l.account.name,
                    "debit":        l.debit,
                    "credit":       l.credit,
                    "description":  l.description,
                }
                for l in e.lines
            ],
        }
        for e in entries
    ]


@router.get("/trial-balance")
async def trial_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accounts = db.query(Account).filter(
        Account.company_id == current_user.company_id,
        Account.is_active == True,
    ).order_by(Account.code).all()

    rows = []
    total_dr = 0
    total_cr = 0
    for acct in accounts:
        lines = db.query(JournalLine).filter(JournalLine.account_id == acct.id).all()
        dr = round(sum(l.debit  for l in lines), 2)
        cr = round(sum(l.credit for l in lines), 2)
        bal = account_balance(acct, db)
        if dr == 0 and cr == 0:
            continue   # skip empty accounts
        rows.append({
            "code":    acct.code,
            "name":    acct.name,
            "type":    acct.type.value,
            "total_debits":  dr,
            "total_credits": cr,
            "balance": bal,
        })
        total_dr += dr
        total_cr += cr

    balanced = abs(total_dr - total_cr) < 0.02
    return {
        "accounts":     rows,
        "total_debits":  round(total_dr, 2),
        "total_credits": round(total_cr, 2),
        "balanced":      balanced,
        "imbalance":     round(total_dr - total_cr, 2),
    }


@router.get("/accounts")
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accounts = db.query(Account).filter(
        Account.company_id == current_user.company_id,
        Account.is_active == True,
    ).order_by(Account.code).all()
    return [
        {"id": a.id, "code": a.code, "name": a.name, "type": a.type.value, "is_system": a.is_system}
        for a in accounts
    ]


class ManualEntryLine(BaseModel):
    account_id: int
    debit:  float = 0
    credit: float = 0
    description: Optional[str] = None

class ManualEntry(BaseModel):
    date:          str
    description:   str
    reference:     Optional[str] = None
    lines:         List[ManualEntryLine]
    # Auto-reversal — set auto_reverse=True and provide reversal_date to have the
    # system automatically post the mirror entry on that date (e.g. month-end accruals).
    auto_reverse:  bool = False
    reversal_date: Optional[str] = None   # ISO date string "YYYY-MM-DD"

@router.post("/manual")
async def create_manual_entry(
    data: ManualEntry,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_dr = round(sum(l.debit  for l in data.lines), 2)
    total_cr = round(sum(l.credit for l in data.lines), 2)
    if abs(total_dr - total_cr) > 0.01:
        raise HTTPException(400, f"Entry is unbalanced: DR {total_dr} ≠ CR {total_cr}")

    if data.auto_reverse and not data.reversal_date:
        raise HTTPException(400, "reversal_date is required when auto_reverse is true")

    reversal_dt = None
    if data.auto_reverse and data.reversal_date:
        try:
            reversal_dt = datetime.fromisoformat(data.reversal_date)
        except ValueError:
            raise HTTPException(400, f"Invalid reversal_date format: {data.reversal_date}. Use YYYY-MM-DD.")

    entry = JournalEntry(
        company_id    = current_user.company_id,
        date          = datetime.fromisoformat(data.date),
        description   = data.description,
        reference     = data.reference,
        source        = "manual",
        source_id     = None,
        auto_reverse  = data.auto_reverse,
        reversal_date = reversal_dt,
    )
    db.add(entry)
    db.flush()

    for l in data.lines:
        acct = db.query(Account).filter(
            Account.id == l.account_id,
            Account.company_id == current_user.company_id,
        ).first()
        if not acct:
            raise HTTPException(404, f"Account {l.account_id} not found")
        db.add(_line(entry.id, acct, l.debit, l.credit, l.description))

    db.commit()
    return {
        "id":            entry.id,
        "message":       "Journal entry created",
        "auto_reverse":  entry.auto_reverse,
        "reversal_date": entry.reversal_date.strftime("%Y-%m-%d") if entry.reversal_date else None,
    }


@router.post("/process-reversals")
async def process_reversals_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually trigger processing of all pending auto-reversals for the current company.
    This is also called automatically on server startup for all companies.
    Returns the list of original entry IDs that were reversed.
    """
    processed = process_pending_reversals(current_user.company_id, db)
    return {
        "status":    "ok",
        "reversed":  len(processed),
        "entry_ids": processed,
        "message":   f"{len(processed)} auto-reversal(s) posted." if processed else "No reversals due.",
    }


@router.post("/reverse/{entry_id}")
async def reverse_entry_endpoint(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually reverse a single journal entry by ID.
    Posts the mirror entry immediately regardless of auto_reverse or reversal_date.
    Returns 400 if the entry has already been reversed.
    """
    entry = db.query(JournalEntry).filter(
        JournalEntry.id         == entry_id,
        JournalEntry.company_id == current_user.company_id,
    ).first()
    if not entry:
        raise HTTPException(404, "Journal entry not found")
    try:
        rev = reverse_entry_by_id(entry_id, db, reason=f"Manual reversal — {entry.description}")
        db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "status":          "ok",
        "reversal_entry_id": rev.id,
        "message":         f"Reversal entry {rev.id} posted for original entry {entry_id}.",
    }
