"""
Annual Financial Statements — IFRS for SMEs
Produces: Income Statement, Balance Sheet, Cash Flow (indirect), Notes
SA financial year default: 1 March (year-1) to 28 Feb (year)
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import (
    get_db, Company, Invoice, Expense, Payslip, Employee,
    PurchaseOrder, InventoryItem, FixedAsset, DepreciationEntry,
    Account, JournalEntry, JournalLine, AccountType, InvoiceStatus,
)
from auth import require_role
from datetime import datetime
import calendar

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

def fy_dates(year: int):
    """SA tax year: 1 March (year-1) to last day of Feb (year)."""
    start = datetime(year - 1, 3, 1, 0, 0, 0)
    last_feb = calendar.monthrange(year, 2)[1]
    end   = datetime(year, 2, last_feb, 23, 59, 59)
    return start, end


def _acct_lines(db, company_id, acct_type: AccountType, date_from=None, date_to=None):
    """Return list of (code, name, total_debit, total_credit) per account."""
    q = (
        db.query(
            Account.code, Account.name,
            func.coalesce(func.sum(JournalLine.debit),  0).label("dr"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("cr"),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .filter(Account.company_id == company_id, Account.type == acct_type)
    )
    if date_from:
        q = q.filter(JournalEntry.date >= date_from)
    if date_to:
        q = q.filter(JournalEntry.date <= date_to)
    q = q.group_by(Account.code, Account.name).order_by(Account.code)
    return [(r.code, r.name, float(r.dr), float(r.cr)) for r in q.all()]


def _r(v): return round(v, 2)


def _inv_rate(inv) -> float:
    """ZAR conversion rate for an invoice at the raised-basis exchange rate —
    the same rate post_invoice_raised uses, so note amounts reconcile with the
    journal-driven statement lines. ZAR invoices are 1.0."""
    if inv.currency and inv.currency != "ZAR":
        return float(inv.exchange_rate or 1.0)
    return 1.0


def _inv_total_zar(inv) -> float:
    """Invoice total (incl VAT) in ZAR at the raised-basis rate — matches the
    AR control (1100) posting in post_invoice_raised."""
    return round((inv.total_amount or 0) * _inv_rate(inv), 2)


# ── Deferred tax (IAS 12 / IFRS for SMEs Section 29) ─────────────────────────
# Fixed-asset temporary differences: accounting carrying value vs SARS tax base
# (s11(e) wear-and-tear, Interpretation Note 47). Both sides are computed
# analytically as at a date so opening and closing balances are consistent for
# historical financial years. Nothing is posted to the journal — the closing
# balance is presented as a computed AFS line, like retained earnings.
# (Audit implementation 2026-07-14, action item L3.)

_CIT_RATE = 0.27

# Fallback IN47 write-off rates (% p.a.), matched by substring on the asset's
# category when neither wear_and_tear_rate nor sars_category is set.
# Order matters — first match wins.
_CATEGORY_WT_RATES = [
    ("software",  50.0),        # 2 yrs (purchased, off-the-shelf)
    ("computer",  100.0 / 3),   # 3 yrs
    ("laptop",    100.0 / 3),   # 3 yrs
    ("phone",     50.0),        # 2 yrs (smartphones/tablets)
    ("furniture", 100.0 / 6),   # 6 yrs
    ("fitting",   100.0 / 6),   # 6 yrs
    ("truck",     25.0),        # 4 yrs (delivery/heavy)
    ("vehicle",   20.0),        # 5 yrs (passenger)
    ("plant",     20.0),        # 5 yrs
    ("machinery", 20.0),        # 5 yrs
    ("building",  4.0),         # 25 yrs (s13quin commercial)
    ("equipment", 20.0),        # 5 yrs (office equipment, general)
]


def _wt_rate_pct(fa):
    """SARS wear-and-tear rate (% p.a.) for an asset, or None if unmappable.
    Priority: explicit wear_and_tear_rate → sars_category (IN47 table in
    fixed_assets.py) → category-name heuristic → None."""
    if fa.wear_and_tear_rate:
        return float(fa.wear_and_tear_rate)
    if fa.sars_category:
        try:
            from fixed_assets import SARS_WEAR_TEAR
            info = SARS_WEAR_TEAR.get(fa.sars_category)
            if info:
                years = info.get("years", 0)
                return 100.0 if years <= 0 else 100.0 / years
        except Exception:
            pass
    cat = (fa.category or "").lower()
    for key, rate in _CATEGORY_WT_RATES:
        if key in cat:
            return rate
    return None


def _months_between(d1, d2) -> int:
    return max(0, (d2.year - d1.year) * 12 + (d2.month - d1.month))


def _deferred_tax_balance(db, cid, as_at) -> float:
    """Net deferred tax balance (positive = liability, negative = asset) from
    fixed-asset temporary differences as at a date.

    Per asset: tax base = cost − cumulative straight-line wear-and-tear at the
    SARS rate (apportioned monthly from purchase date, floored at 0);
    temporary difference = accounting carrying value − tax base; balance =
    temporary difference × 27%. Assets with no mappable rate use the accounting
    carrying value as tax base, so their difference is exactly zero. With no
    fixed assets or no rate data the result is exactly 0.0 and the AFS output
    shape is unchanged."""
    assets = db.query(FixedAsset).filter(
        FixedAsset.company_id == cid,
        FixedAsset.purchase_date <= as_at,
    ).all()
    balance = 0.0
    for fa in assets:
        # Disposed / written off on or before as_at — temporary difference reversed
        if fa.disposal_date and fa.disposal_date <= as_at:
            continue
        cost = float(fa.cost or 0)
        if cost <= 0:
            continue
        months = _months_between(fa.purchase_date, as_at)
        # Accounting carrying value at as_at (analytic — mirrors the register's
        # methods so historical FY ends don't use today's accumulated figure)
        residual = float(fa.residual_value or 0)
        life = fa.useful_life_months or 0
        if fa.depreciation_method == "diminishing_balance" and fa.depreciation_rate:
            carrying = max(residual, cost * (1.0 - float(fa.depreciation_rate)) ** (months / 12.0))
        elif life > 0:
            monthly = (cost - residual) / life
            carrying = max(residual, cost - monthly * months)
        else:
            carrying = cost
        rate = _wt_rate_pct(fa)
        if rate is None:
            tax_base = carrying           # unmappable → zero temporary difference
        else:
            allowance = min(cost, cost * (rate / 100.0) * (months / 12.0))
            tax_base = max(0.0, cost - allowance)
        balance += (carrying - tax_base) * _CIT_RATE
    return _r(balance)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/annual")
def annual_financial_statements(
    year: int = Query(..., description="Financial year end, e.g. 2025 = 1 Mar 2024 – 28 Feb 2025"),
    db: Session = Depends(get_db),
    current_user=Depends(require_role("owner", "admin", "accountant")),
):
    cid   = current_user.company_id
    start, end = fy_dates(year)
    company = db.query(Company).filter(Company.id == cid).first()

    # ── INCOME STATEMENT ─────────────────────────────────────────────────────
    # Revenue (credit-normal accounts)
    rev_rows = _acct_lines(db, cid, AccountType.revenue, start, end)
    revenue_lines = [
        {"code": c, "name": n, "amount": _r(cr - dr)}
        for c, n, dr, cr in rev_rows if _r(cr - dr) != 0
    ]
    total_revenue = sum(l["amount"] for l in revenue_lines)

    # Expenses (debit-normal accounts)
    exp_rows = _acct_lines(db, cid, AccountType.expense, start, end)
    expense_lines = [
        {"code": c, "name": n, "amount": _r(dr - cr)}
        for c, n, dr, cr in exp_rows if _r(dr - cr) != 0
    ]

    # Finance costs (audit fix 2026-07-13): interest lines are presented below
    # EBIT, not inside opex. Matches account 6700 plus any imported account whose
    # name indicates interest/finance charges.
    def _is_finance_cost(l):
        nm = l["name"].lower()
        return l["code"] == "6700" or "interest" in nm or "finance cost" in nm
    finance_lines = [l for l in expense_lines if _is_finance_cost(l)]
    finance_costs = _r(sum(l["amount"] for l in finance_lines))

    # Split COGS (51xx) from OPEX
    cogs_lines = [l for l in expense_lines if l["code"].startswith("51") and not _is_finance_cost(l)]
    opex_lines  = [l for l in expense_lines if not l["code"].startswith("51") and not _is_finance_cost(l)]

    total_cogs    = sum(l["amount"] for l in cogs_lines)
    gross_profit  = _r(total_revenue - total_cogs)
    gross_margin  = _r(gross_profit / total_revenue * 100) if total_revenue else 0
    total_opex    = sum(l["amount"] for l in opex_lines)
    ebit          = _r(gross_profit - total_opex)

    # Depreciation line (pulled from DepreciationEntry for transparency)
    dep_period = [
        d for d in
        db.query(DepreciationEntry).filter(DepreciationEntry.company_id == cid).all()
        if d.period >= start.strftime("%Y-%m") and d.period <= end.strftime("%Y-%m")
    ]
    total_depreciation = _r(sum(d.amount for d in dep_period))

    # SA corporate tax (27%) — on profit before tax, i.e. after finance costs
    # (audit fix 2026-07-13; previously taxed EBIT with finance_costs stubbed 0.0)
    profit_before_tax = _r(ebit - finance_costs)
    tax_expense = _r(max(0.0, profit_before_tax * 0.27))
    net_profit  = _r(profit_before_tax - tax_expense)

    # Deferred tax from fixed-asset temporary differences (audit implementation
    # 2026-07-14 — IAS 12 / IFRS for SMEs Section 29). Expense = movement in the
    # computed balance over the period; 0.0 when there are no fixed assets.
    dt_opening = _deferred_tax_balance(db, cid, start)
    dt_closing = _deferred_tax_balance(db, cid, end)
    deferred_tax_expense = _r(dt_closing - dt_opening)

    # ── BALANCE SHEET (cumulative to period end) ──────────────────────────────

    # Assets (debit-normal: balance = DR - CR)
    asset_rows = _acct_lines(db, cid, AccountType.asset, date_to=end)
    asset_lines = [
        {"code": c, "name": n, "amount": _r(dr - cr)}
        for c, n, dr, cr in asset_rows
    ]

    # Separate current (1xxx–14xx) vs non-current (15xx+)
    current_assets     = [l for l in asset_lines if l["code"] < "1500"]
    non_current_assets = [l for l in asset_lines if l["code"] >= "1500"]
    total_current_assets     = _r(sum(l["amount"] for l in current_assets))
    total_non_current_assets = _r(sum(l["amount"] for l in non_current_assets))
    total_assets = _r(total_current_assets + total_non_current_assets)

    # Liabilities (credit-normal: balance = CR - DR)
    liab_rows = _acct_lines(db, cid, AccountType.liability, date_to=end)
    liab_lines = [
        {"code": c, "name": n, "amount": _r(cr - dr)}
        for c, n, dr, cr in liab_rows
    ]
    current_liabilities     = [l for l in liab_lines if l["code"] < "2500"]
    non_current_liabilities = [l for l in liab_lines if l["code"] >= "2500"]
    total_current_liabilities     = _r(sum(l["amount"] for l in current_liabilities))
    total_non_current_liabilities = _r(sum(l["amount"] for l in non_current_liabilities))
    total_liabilities = _r(total_current_liabilities + total_non_current_liabilities)

    # Equity (credit-normal: balance = CR - DR)
    eq_rows = _acct_lines(db, cid, AccountType.equity, date_to=end)
    eq_lines = [
        {"code": c, "name": n, "amount": _r(cr - dr)}
        for c, n, dr, cr in eq_rows
    ]

    # Retained earnings = all-time cumulative net profit not yet closed to equity accounts
    all_rev = _acct_lines(db, cid, AccountType.revenue, date_to=end)
    all_exp = _acct_lines(db, cid, AccountType.expense, date_to=end)
    cum_revenue  = sum(cr - dr for _, _, dr, cr in all_rev)
    cum_expenses = sum(dr - cr for _, _, dr, cr in all_exp)
    retained_earnings = _r(cum_revenue - cum_expenses)

    # Deferred tax presentation (audit implementation 2026-07-14): the closing
    # balance is a computed AFS line — not a journal posting — with the matching
    # adjustment made to retained earnings so Assets = Equity + Liabilities holds.
    if dt_closing > 0.005:
        non_current_liabilities = non_current_liabilities + [
            {"code": "2600", "name": "Deferred Tax Liability", "amount": dt_closing}
        ]
        total_non_current_liabilities = _r(total_non_current_liabilities + dt_closing)
        total_liabilities             = _r(total_liabilities + dt_closing)
        retained_earnings             = _r(retained_earnings - dt_closing)
    elif dt_closing < -0.005:
        non_current_assets = non_current_assets + [
            {"code": "1900", "name": "Deferred Tax Asset", "amount": _r(-dt_closing)}
        ]
        total_non_current_assets = _r(total_non_current_assets - dt_closing)
        total_assets              = _r(total_assets - dt_closing)
        retained_earnings         = _r(retained_earnings - dt_closing)

    equity_capital    = _r(sum(l["amount"] for l in eq_lines))
    total_equity      = _r(equity_capital + retained_earnings)
    total_equity_and_liabilities = _r(total_liabilities + total_equity)

    # ── STATEMENT OF CHANGES IN EQUITY ────────────────────────────────────────
    # Opening equity capital (equity account balances at start of period)
    open_eq_rows         = _acct_lines(db, cid, AccountType.equity, date_to=start)
    opening_equity_cap   = _r(sum(cr - dr for _, _, dr, cr in open_eq_rows))

    # Opening retained earnings (all-time cumulative P&L up to start)
    open_rev             = _acct_lines(db, cid, AccountType.revenue, date_to=start)
    open_exp             = _acct_lines(db, cid, AccountType.expense, date_to=start)
    opening_retained     = _r(
        sum(cr - dr for _, _, dr, cr in open_rev) -
        sum(dr - cr for _, _, dr, cr in open_exp)
    )
    # Match the balance-sheet presentation: opening retained earnings carry the
    # opening deferred-tax adjustment, so the equity statement reconciles up to
    # the period's deferred-tax movement (disclosed as deferred_tax_movement).
    opening_retained     = _r(opening_retained - dt_opening)
    opening_total_equity = _r(opening_equity_cap + opening_retained)

    # Equity movements during the period (e.g. owner contributions and drawings)
    eq_period_rows       = _acct_lines(db, cid, AccountType.equity, date_from=start, date_to=end)
    period_contributions = _r(sum(max(0.0, cr - dr) for _, _, dr, cr in eq_period_rows))
    period_drawings      = _r(sum(max(0.0, dr - cr) for _, _, dr, cr in eq_period_rows))

    # ── CASH FLOW (Indirect Method) ───────────────────────────────────────────
    # Operating
    # Changes in AR (1100) between start-1 and end
    ar_end_rows   = [r for r in asset_rows if r[0] == "1100"]
    ar_end        = _r((ar_end_rows[0][2] - ar_end_rows[0][3]) if ar_end_rows else 0)
    ar_start_rows = _acct_lines(db, cid, AccountType.asset, date_to=datetime(start.year, start.month, start.day))
    ar_start_row  = next((r for r in ar_start_rows if r[0] == "1100"), None)
    ar_start      = _r((ar_start_row[2] - ar_start_row[3]) if ar_start_row else 0)
    change_in_ar  = _r(-(ar_end - ar_start))   # increase in AR = cash NOT received

    # Changes in AP (2000)
    ap_end_rows   = [r for r in liab_rows if r[0] == "2000"]
    ap_end        = _r((ap_end_rows[0][3] - ap_end_rows[0][2]) if ap_end_rows else 0)
    ap_start_rows = _acct_lines(db, cid, AccountType.liability, date_to=datetime(start.year, start.month, start.day))
    ap_start_row  = next((r for r in ap_start_rows if r[0] == "2000"), None)
    ap_start      = _r((ap_start_row[3] - ap_start_row[2]) if ap_start_row else 0)
    change_in_ap  = _r(ap_end - ap_start)       # increase in AP = cash NOT yet paid

    # Changes in inventory (1200)
    inv_end_rows  = [r for r in asset_rows if r[0] == "1200"]
    inv_end       = _r((inv_end_rows[0][2] - inv_end_rows[0][3]) if inv_end_rows else 0)
    inv_start_rows = _acct_lines(db, cid, AccountType.asset, date_to=datetime(start.year, start.month, start.day))
    inv_start_row = next((r for r in inv_start_rows if r[0] == "1200"), None)
    inv_start     = _r((inv_start_row[2] - inv_start_row[3]) if inv_start_row else 0)
    change_in_inv = _r(-(inv_end - inv_start))  # increase in inventory = cash outflow

    cash_from_operations = _r(net_profit + total_depreciation + change_in_ar + change_in_ap + change_in_inv)

    # Investing — fixed asset purchases in period
    fa_in_period = db.query(FixedAsset).filter(
        FixedAsset.company_id == cid,
        FixedAsset.purchase_date >= start,
        FixedAsset.purchase_date <= end,
    ).all()
    fa_purchases = _r(sum(fa.cost for fa in fa_in_period))

    # Disposal proceeds
    fa_disposals = _r(sum(
        (fa.disposal_proceeds or 0)
        for fa in db.query(FixedAsset).filter(
            FixedAsset.company_id == cid,
            FixedAsset.disposal_date >= start,
            FixedAsset.disposal_date <= end,
        ).all()
    ))
    cash_from_investing = _r(-fa_purchases + fa_disposals)

    # Financing (loans not yet tracked)
    cash_from_financing = 0.0
    net_cash_change = _r(cash_from_operations + cash_from_investing + cash_from_financing)

    # Opening cash
    cash_acct_start = _acct_lines(db, cid, AccountType.asset, date_to=datetime(start.year, start.month, start.day))
    cash_start_row  = next((r for r in cash_acct_start if r[0] == "1000"), None)
    opening_cash    = _r((cash_start_row[2] - cash_start_row[3]) if cash_start_row else 0)
    closing_cash    = _r(opening_cash + net_cash_change)

    # ── NOTES ────────────────────────────────────────────────────────────────

    # Note 2 — Property, Plant and Equipment schedule (all-time, not period-filtered)
    all_fa = db.query(FixedAsset).filter(FixedAsset.company_id == cid).all()
    fa_schedule = [
        {
            "number":       fa.asset_number or f"FA-{fa.id:03d}",
            "name":         fa.asset_name,
            "category":     fa.category,
            "cost":         _r(fa.cost),
            "accum_dep":    _r(fa.accumulated_depreciation),
            "carrying":     _r(fa.carrying_value),
            "dep_method":   fa.depreciation_method,
            "useful_life":  fa.useful_life_months,
            "status":       fa.status,
        }
        for fa in all_fa
    ]

    # Note 3 — Trade receivables aging (as at period end)
    open_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue]),
        Invoice.issue_date <= end,
    ).all()
    # Break into aging buckets (0-30, 31-60, 61-90, 90+) based on days past due_date
    today = datetime.utcnow()
    def _days_overdue(inv):
        ref = inv.due_date or inv.issue_date
        return max(0, (today - ref).days) if ref else 0
    # ZAR at the raised-basis rate (audit fix 2026-07-11 M4) — previously raw
    # foreign-currency totals were summed, so this note could not reconcile
    # with the ZAR-denominated trade receivables line (1100) on the balance sheet.
    ar_current = _r(sum(_inv_total_zar(i) for i in open_invoices if _days_overdue(i) == 0))
    ar_0_30    = _r(sum(_inv_total_zar(i) for i in open_invoices if 1  <= _days_overdue(i) <= 30))
    ar_31_60   = _r(sum(_inv_total_zar(i) for i in open_invoices if 31 <= _days_overdue(i) <= 60))
    ar_61_90   = _r(sum(_inv_total_zar(i) for i in open_invoices if 61 <= _days_overdue(i) <= 90))
    ar_90plus  = _r(sum(_inv_total_zar(i) for i in open_invoices if _days_overdue(i) > 90))
    receivables_aging = {
        "current":   ar_current,
        "days_1_30": ar_0_30,
        "days_31_60": ar_31_60,
        "days_61_90": ar_61_90,
        "days_90plus": ar_90plus,
        "total":     _r(sum(_inv_total_zar(i) for i in open_invoices)),
        "count":     len(open_invoices),
    }

    # Note 4 — Revenue by customer (top 10, period).
    # Accrual basis to match the income statement (audit fix 2026-07-11 M4):
    # all ISSUED invoices (sent/overdue/paid) by issue date — previously only
    # paid invoices were counted, so this note reconciled to nothing on the face
    # of the statements. Amounts ex-VAT, translated to ZAR at the invoice
    # exchange rate — the same raised-basis rate post_invoice_raised uses for
    # the revenue account (4000) this note breaks down.
    issued_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue, InvoiceStatus.paid]),
        Invoice.issue_date >= start,
        Invoice.issue_date <= end,
    ).all()
    client_rev: dict = {}
    for inv in issued_invoices:
        k = inv.client_name or "Unknown"
        client_rev[k] = client_rev.get(k, 0) + round((inv.amount or 0) * _inv_rate(inv), 2)
    revenue_by_customer = sorted(
        [{"client": k, "revenue": _r(v)} for k, v in client_rev.items()],
        key=lambda x: x["revenue"], reverse=True
    )[:10]

    # Note 5 — Expense analysis by category (period)
    period_expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= start,
        Expense.expense_date <= end,
    ).all()
    cat_totals: dict = {}
    for exp in period_expenses:
        k = exp.category or "Uncategorised"
        cat_totals[k] = cat_totals.get(k, 0) + (exp.amount or 0)
    expense_by_category = sorted(
        [{"category": k, "total": _r(v)} for k, v in cat_totals.items()],
        key=lambda x: x["total"], reverse=True
    )
    total_expenses_ex_vat = _r(sum(exp.amount or 0 for exp in period_expenses))

    # Note 6 — Employee benefits / payroll summary (period)
    # Payslip.period is stored as "YYYY-MM", so filter by year range
    period_months = set()
    d = start.replace(day=1)
    while d <= end:
        period_months.add(d.strftime("%Y-%m"))
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1)
        else:
            d = d.replace(month=d.month + 1)

    all_payslips = db.query(Payslip).join(Employee).filter(
        Employee.company_id == cid
    ).all()
    period_payslips = [p for p in all_payslips if p.period in period_months]
    payroll_summary = {
        "gross_pay":      _r(sum(p.gross_salary   or 0 for p in period_payslips)),
        "paye":           _r(sum(p.paye            or 0 for p in period_payslips)),
        "uif_employee":   _r(sum(p.uif_employee    or 0 for p in period_payslips)),
        "uif_employer":   _r(sum(p.uif_employer    or 0 for p in period_payslips)),
        "sdl":            _r(sum(p.sdl             or 0 for p in period_payslips)),
        "net_pay":        _r(sum(p.net_pay         or 0 for p in period_payslips)),
        "total_cost":     _r(sum(p.total_cost      or 0 for p in period_payslips)),
        "periods_count":  len(set(p.period for p in period_payslips)),
        "headcount":      db.query(Employee).filter(Employee.company_id == cid, Employee.is_active == True).count(),
    }

    # Note 7 — Trade payables (as at period end)
    # Open POs (received/partial, not yet fully paid) + unpaid credit expenses
    open_pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id == cid,
        PurchaseOrder.status.in_(["received", "partial"]),
    ).all()
    unpaid_credit_expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.is_on_credit == True,
        Expense.paid_at == None,
        Expense.expense_date <= end,
    ).all()
    payables_summary = {
        "open_pos":               _r(sum(po.total_amount or 0 for po in open_pos)),
        "open_pos_count":         len(open_pos),
        "unpaid_credit_expenses": _r(sum(e.amount or 0 for e in unpaid_credit_expenses)),
        "total_payables":         _r(
            sum(po.total_amount or 0 for po in open_pos) +
            sum(e.amount or 0 for e in unpaid_credit_expenses)
        ),
    }

    # Note 8 — Inventory detail
    inv_items = db.query(InventoryItem).filter(InventoryItem.company_id == cid, InventoryItem.is_active == True).all()
    inventory_note = {
        "total_value": _r(sum(i.unit_cost * i.quantity_on_hand for i in inv_items)),
        "item_count":  len(inv_items),
        "items": sorted(
            [{"name": i.name, "sku": i.sku, "qty": i.quantity_on_hand,
              "unit_cost": _r(i.unit_cost), "total": _r(i.unit_cost * i.quantity_on_hand)}
             for i in inv_items],
            key=lambda x: x["total"], reverse=True
        )[:20],
    }

    # Note 9 — Taxation (deferred tax computed from fixed-asset temporary
    # differences — audit implementation 2026-07-14)
    total_tax = _r(tax_expense + deferred_tax_expense)
    tax_note = {
        "profit_before_tax": _r(profit_before_tax),
        "tax_rate_pct":      27.0,
        "current_tax":       _r(tax_expense),
        "deferred_tax":      deferred_tax_expense,
        "total_tax":         total_tax,
        "effective_rate_pct": round(total_tax / profit_before_tax * 100, 1) if profit_before_tax > 0 else 0.0,
        "deferred_tax_opening_balance": dt_opening,
        "deferred_tax_closing_balance": dt_closing,
    }

    return {
        "meta": {
            "company_name":    company.name,
            "reg_number":      company.reg_number or "",
            "vat_number":      company.vat_number or "",
            "address":         company.address or "",
            "period_start":    start.strftime("%d %B %Y"),
            "period_end":      end.strftime("%d %B %Y"),
            "year":            year,
            "generated_at":    datetime.utcnow().isoformat(),
            "basis":           "IFRS for SMEs",
            "currency":        "ZAR",
        },
        "income_statement": {
            "revenue_lines":   revenue_lines,
            "total_revenue":   _r(total_revenue),
            "cogs_lines":      cogs_lines,
            "total_cogs":      _r(total_cogs),
            "gross_profit":    gross_profit,
            "gross_margin_pct": gross_margin,
            "opex_lines":      opex_lines,
            "total_opex":      _r(total_opex),
            "depreciation":    total_depreciation,
            "ebit":            ebit,
            "finance_lines":   finance_lines,
            "finance_costs":   finance_costs,
            "profit_before_tax": profit_before_tax,
            "tax_expense":     tax_expense,
            "tax_rate_pct":    27.0,
            "net_profit":      net_profit,
        },
        "balance_sheet": {
            "assets": {
                "current":          current_assets,
                "total_current":    total_current_assets,
                "non_current":      non_current_assets,
                "total_non_current": total_non_current_assets,
                "total":            total_assets,
            },
            "liabilities": {
                "current":              current_liabilities,
                "total_current":        total_current_liabilities,
                "non_current":          non_current_liabilities,
                "total_non_current":    total_non_current_liabilities,
                "total":                total_liabilities,
            },
            "equity": {
                "lines":              eq_lines,
                "equity_capital":     equity_capital,
                "retained_earnings":  retained_earnings,
                "total":              total_equity,
            },
            "total_equity_and_liabilities": total_equity_and_liabilities,
            "balanced":  abs(total_assets - total_equity_and_liabilities) < 0.10,
        },
        "changes_in_equity": {
            "opening_share_capital":  opening_equity_cap,
            "opening_retained":       opening_retained,
            "opening_total":          opening_total_equity,
            "net_profit":             net_profit,
            "contributions":          period_contributions,
            "drawings":               period_drawings,
            "closing_share_capital":  equity_capital,
            "closing_retained":       retained_earnings,
            "closing_total":          total_equity,
            # Non-cash deferred-tax movement (negative = charge) — explains the
            # difference between opening + profit + contributions − drawings and
            # closing when deferred tax is non-zero.
            "deferred_tax_movement":  _r(-deferred_tax_expense),
        },
        "cash_flow": {
            "operating": {
                "net_profit":           net_profit,
                "add_depreciation":     total_depreciation,
                "change_in_ar":         change_in_ar,
                "change_in_ap":         change_in_ap,
                "change_in_inventory":  change_in_inv,
                "total":                cash_from_operations,
            },
            "investing": {
                "purchase_of_fa":       _r(-fa_purchases),
                "disposal_proceeds":    fa_disposals,
                "total":                cash_from_investing,
            },
            "financing": {
                "total": cash_from_financing,
            },
            "net_change":     net_cash_change,
            "opening_cash":   opening_cash,
            "closing_cash":   closing_cash,
        },
        "notes": {
            "fixed_assets":          fa_schedule,
            "receivables_aging":     receivables_aging,
            "revenue_by_customer":   revenue_by_customer,
            "expense_by_category":   expense_by_category,
            "total_expenses_ex_vat": total_expenses_ex_vat,
            "payroll_summary":       payroll_summary,
            "payables_summary":      payables_summary,
            "inventory":             inventory_note,
            "tax_note":              tax_note,
            "accounting_policies": {
                "basis_of_preparation":
                    "These financial statements have been prepared in accordance with the International "
                    "Financial Reporting Standard for Small and Medium-sized Entities (IFRS for SMEs).",
                "revenue_recognition":
                    "Revenue is recognised on the accrual basis when invoices are issued to customers "
                    "and the entity's performance obligation is satisfied (Section 23 of the IFRS for "
                    "SMEs Standard). Revenue is measured at the fair value of the consideration "
                    "receivable, net of VAT. Foreign-currency invoices are translated to Rand at the "
                    "exchange rate ruling at the transaction date.",
                "fixed_assets":
                    "Property, plant and equipment are stated at cost less accumulated depreciation. "
                    "Depreciation is calculated on the straight-line or diminishing balance method "
                    "over the estimated useful life of each asset.",
                "inventory":
                    "Inventories are measured at the lower of cost and estimated selling price less "
                    "costs to complete and sell, on a first-in first-out (FIFO) basis.",
                "vat":
                    "The entity is registered for Value-Added Tax (VAT). All amounts in these "
                    "financial statements are stated exclusive of VAT unless otherwise indicated.",
                "employee_benefits":
                    "Short-term employee benefits are expensed as the related service is provided. "
                    "Contributions to UIF and SDL are expensed in the period in which they arise.",
                "income_tax":
                    "Income tax is calculated at the standard corporate rate of 27% on taxable profit. "
                    "Deferred tax is recognised on temporary differences between the carrying value of "
                    "property, plant and equipment and its tax base (SARS section 11(e) wear-and-tear "
                    "allowances, Interpretation Note 47), measured at the corporate rate of 27% "
                    "(Section 29 of the IFRS for SMEs Standard).",
            },
        },
    }
