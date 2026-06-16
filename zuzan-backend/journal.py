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
      DR Accounts Receivable   (total incl VAT)
      CR Sales Revenue         (amount excl VAT)
      CR VAT Output Payable    (vat_amount)
    """
    cid = invoice.company_id
    lines = []
    entry = _make_entry(cid, invoice.issue_date or datetime.utcnow(),
        f"Invoice raised — {invoice.client_name}",
        invoice.invoice_number, "invoice", invoice.id, db)

    ar  = get_account(cid, "1100", db)
    rev = get_account(cid, "4000", db)
    vat = get_account(cid, "2100", db)

    lines.append(_line(entry.id, ar,  debit=invoice.total_amount, description=invoice.invoice_number))
    lines.append(_line(entry.id, rev, credit=invoice.amount,      description="Revenue excl VAT"))
    if invoice.vat_amount:
        lines.append(_line(entry.id, vat, credit=invoice.vat_amount, description="VAT output"))

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

    # For foreign-currency invoices use the ZAR amount actually received;
    # fall back to total_amount if paid_amount_zar was not recorded.
    zar_received = invoice.paid_amount_zar if invoice.paid_amount_zar else invoice.total_amount
    lines = [
        _line(entry.id, bank, debit=zar_received,          description="Cash received"),
        _line(entry.id, ar,   credit=invoice.total_amount, description=invoice.invoice_number),
    ]
    _assert_balanced(lines)
    for l in lines: db.add(l)
    return entry


def post_expense(expense, db: Session) -> JournalEntry:
    """
    Expense paid:
      DR Expense Account       (amount excl VAT)
      DR VAT Input Recoverable (vat_amount)
      CR Bank / Cash           (total paid)
    """
    cid = invoice_cid = expense.company_id
    total = round((expense.amount or 0), 2)
    vat   = round((expense.vat_amount or 0), 2)
    net   = round(total - vat, 2)

    entry = _make_entry(cid, expense.expense_date or datetime.utcnow(),
        f"Expense — {expense.vendor}: {expense.description or ''}",
        f"EXP-{expense.id}", "expense", expense.id, db)

    exp_acct = expense_account(cid, expense.category, db)
    vat_in   = get_account(cid, "1300", db)
    bank     = get_account(cid, "1000", db)

    lines = [_line(entry.id, exp_acct, debit=net,   description=expense.category)]
    if vat > 0:
        lines.append(_line(entry.id, vat_in, debit=vat, description="VAT input"))
    lines.append(_line(entry.id, bank, credit=total, description="Cash paid"))

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
      DR Inventory at Cost / Expense  (amount excl VAT)
      DR VAT Input Recoverable        (vat_amount)
      CR Accounts Payable             (total_amount)
    """
    cid = po.company_id
    total = round(po.total_amount or 0, 2)
    vat   = round(po.vat_amount   or 0, 2)
    net   = round(total - vat, 2)

    entry = _make_entry(cid, po.received_date or datetime.utcnow(),
        f"PO received — {po.supplier_name or 'Supplier'}",
        po.po_number, "purchase_order", po.id, db)

    inventory = get_account(cid, "1200", db)
    vat_in    = get_account(cid, "1300", db)
    ap        = get_account(cid, "2000", db)

    lines = [_line(entry.id, inventory, debit=net,    description="Goods/services received")]
    if vat > 0:
        lines.append(_line(entry.id, vat_in, debit=vat, description="VAT input"))
    lines.append(_line(entry.id, ap, credit=total,    description=po.po_number))

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

    db.commit()
    return posted


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
            "id":          e.id,
            "date":        e.date.strftime("%Y-%m-%d"),
            "description": e.description,
            "reference":   e.reference,
            "source":      e.source,
            "is_reconciled": e.is_reconciled,
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
    date:        str
    description: str
    reference:   Optional[str] = None
    lines:       List[ManualEntryLine]

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

    entry = _make_entry(
        current_user.company_id,
        datetime.fromisoformat(data.date),
        data.description,
        data.reference,
        "manual", None, db,
    )
    for l in data.lines:
        acct = db.query(Account).filter(
            Account.id == l.account_id,
            Account.company_id == current_user.company_id,
        ).first()
        if not acct:
            raise HTTPException(404, f"Account {l.account_id} not found")
        db.add(_line(entry.id, acct, l.debit, l.credit, l.description))

    db.commit()
    return {"id": entry.id, "message": "Journal entry created"}
