"""
Monthly management report (2026-11-15).

After month-end the accountant opens a client's report for the month, checks the figures, edits the commentary
(drafted by AI from the figures) and sends a PDF to the client's management. Nothing is sent automatically.

Figures come from the general ledger, so they match the trial balance and the annual financial statements:
  - Income statement: the month and the financial year to date, each against the same period last year.
  - Balance sheet: at month-end against the last financial year-end.
  - Cash flow: the month and the year to date, derived from balance sheet movements (indirect method).

Routes (mounted at /management-report, roles owner/admin/accountant):
  GET  /                         history of reports for the company
  GET  /{period}                 figures + saved draft for YYYY-MM
  PUT  /{period}                 save commentary / recipients (draft only)
  POST /{period}/draft-commentary  AI (or template) commentary from the figures
  GET  /{period}/pdf             the PDF
  POST /{period}/send            email the PDF to the recipients and freeze the figures
  POST /{period}/reopen          back to draft so it can be corrected and sent again
"""
import io
import json
import logging
import os
import re
import calendar
from datetime import datetime, timedelta, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_role, log_action, User
from database import get_db, Company, AccountType, ManagementReport
import financial_statements as FS

logger = logging.getLogger("zuzan.management_report")
router = APIRouter()

_ROLES = ("owner", "admin", "accountant")
_PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_EPS = timedelta(microseconds=1)


# ── periods ───────────────────────────────────────────────────────────────────

def _parse_period(period: str):
    m = _PERIOD_RE.match(period or "")
    if not m:
        raise HTTPException(400, "Period must be YYYY-MM, e.g. 2026-10.")
    return int(m.group(1)), int(m.group(2))


def _month_bounds(y: int, m: int):
    start = datetime(y, m, 1)
    end_excl = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
    return start, end_excl


def _fy_start(company, on: date) -> date:
    from payroll import _company_fy
    return _company_fy(company, on)[0]


def _month_label(y: int, m: int) -> str:
    return f"{calendar.month_name[m]} {y}"


# ── classification ────────────────────────────────────────────────────────────

def _num(code: str) -> Optional[int]:
    c = (code or "").strip()
    return int(c) if c.isdigit() else None


def _is_cash(code: str, name: str) -> bool:
    n = (name or "").lower()
    if any(w in n for w in ("guarantee", "receivable", "accrued", "deposit")):
        return False
    if any(w in n for w in ("bank", "cash", "call account", "money market", "petty")):
        return True
    c = _num(code)
    return c is not None and 1000 <= c <= 1009


def _is_non_current_asset(code: str, name: str) -> bool:
    c = _num(code)
    if c is not None:
        return c >= 1500
    n = (name or "").lower()
    return any(w in n for w in ("property", "plant", "equipment", "goodwill", "intangible", "vehicle",
                                "depreciation", "long-term invest", "deferred tax"))


def _is_non_current_liability(code: str, name: str) -> bool:
    c = _num(code)
    n = (name or "").lower()
    if "current portion" in n:
        return False
    if c is not None:
        return c >= 2500
    return any(w in n for w in ("long-term", "long term", "non-current", "shareholder", "director"))


def _cash_flow_bucket(atype: AccountType, code: str, name: str) -> str:
    """Where a balance sheet account's movement goes in the cash flow."""
    n = (name or "").lower()
    if atype == AccountType.asset:
        if _is_cash(code, name):
            return "cash"
        if _is_non_current_asset(code, name):
            return "investing"
        if "vat" in n:
            return "vat"
        if any(w in n for w in ("inventor", "stock")) or (_num(code) is not None and 1200 <= _num(code) <= 1299):
            return "inventory"
        return "receivables"
    if atype == AccountType.liability:
        if "vat" in n:
            return "vat"
        if "loan" in n or _is_non_current_liability(code, name):
            return "financing"
        if any(w in n for w in ("income tax", "provisional tax")):
            return "tax"
        return "payables"
    return "financing"          # equity accounts (share capital, drawings, dividends)


# ── ledger reads ──────────────────────────────────────────────────────────────

def _pl_by_account(db, cid, start, end_excl) -> dict:
    """{(type, code, name): signed amount} for P&L accounts in [start, end_excl); revenue positive, costs positive."""
    out = {}
    for t in (AccountType.revenue, AccountType.cogs, AccountType.expense):
        for code, name, dr, cr in FS._acct_lines(db, cid, t, start, end_excl - _EPS):
            amt = (cr - dr) if t == AccountType.revenue else (dr - cr)
            if abs(amt) >= 0.005:
                out[(t.value, code, name)] = round(amt, 2)
    return out


def _balances(db, cid, at: datetime) -> dict:
    """{(type, code, name): balance} for balance sheet accounts at `at` (inclusive); assets debit-positive,
    liabilities and equity credit-positive."""
    out = {}
    for t in (AccountType.asset, AccountType.liability, AccountType.equity):
        for code, name, dr, cr in FS._acct_lines(db, cid, t, None, at):
            bal = (dr - cr) if t == AccountType.asset else (cr - dr)
            if abs(bal) >= 0.005:
                out[(t.value, code, name)] = round(bal, 2)
    return out


def _cum_profit(db, cid, at: datetime) -> float:
    total = 0.0
    for t in (AccountType.revenue, AccountType.cogs, AccountType.expense):
        for _c, _n, dr, cr in FS._acct_lines(db, cid, t, None, at):
            total += (cr - dr)
    return round(total, 2)


def _is_finance_cost(code: str, name: str) -> bool:
    n = (name or "").lower()
    return code == "6700" or "interest" in n or "finance cost" in n


def _is_dep(name: str) -> bool:
    n = (name or "").lower()
    return "depreciation" in n or "amortisation" in n or "amortization" in n


# ── the figures ───────────────────────────────────────────────────────────────

def _income_statement(periods: dict) -> dict:
    """periods: {"month": pl, "month_py": pl, "ytd": pl, "ytd_py": pl} from _pl_by_account."""
    keys = sorted({k for pl in periods.values() for k in pl}, key=lambda k: (k[1] or "", k[2] or ""))
    cols = list(periods)

    def section(pred):
        rows = []
        for k in keys:
            if pred(k):
                rows.append({"code": k[1], "name": k[2], **{c: periods[c].get(k, 0.0) for c in cols}})
        total = {c: round(sum(r[c] for r in rows), 2) for c in cols}
        return rows, total

    revenue, rev_t = section(lambda k: k[0] == "revenue")
    cogs, cogs_t = section(lambda k: k[0] == "cogs")
    opex, opex_t = section(lambda k: k[0] == "expense" and not _is_finance_cost(k[1], k[2]))
    finance, fin_t = section(lambda k: k[0] == "expense" and _is_finance_cost(k[1], k[2]))
    gp = {c: round(rev_t[c] - cogs_t[c], 2) for c in cols}
    op = {c: round(gp[c] - opex_t[c], 2) for c in cols}
    npbt = {c: round(op[c] - fin_t[c], 2) for c in cols}
    pct = lambda a, b: round(a / b * 100, 1) if abs(b) >= 0.005 else None
    return {
        "columns": cols,
        "revenue": revenue, "total_revenue": rev_t,
        "cogs": cogs, "total_cogs": cogs_t,
        "gross_profit": gp, "gross_margin_pct": {c: pct(gp[c], rev_t[c]) for c in cols},
        "opex": opex, "total_opex": opex_t,
        "operating_profit": op,
        "finance_costs": finance, "total_finance_costs": fin_t,
        "net_profit_before_tax": npbt, "net_margin_pct": {c: pct(npbt[c], rev_t[c]) for c in cols},
    }


def _balance_sheet(db, cid, at: datetime, comp_at: datetime) -> dict:
    now_b, comp_b = _balances(db, cid, at), _balances(db, cid, comp_at)
    keys = sorted(set(now_b) | set(comp_b), key=lambda k: (k[1] or "", k[2] or ""))

    def rows(pred):
        r = [{"code": k[1], "name": k[2], "now": now_b.get(k, 0.0), "comp": comp_b.get(k, 0.0)} for k in keys if pred(k)]
        return r, {"now": round(sum(x["now"] for x in r), 2), "comp": round(sum(x["comp"] for x in r), 2)}

    nca, nca_t = rows(lambda k: k[0] == "asset" and _is_non_current_asset(k[1], k[2]))
    ca, ca_t = rows(lambda k: k[0] == "asset" and not _is_non_current_asset(k[1], k[2]))
    ncl, ncl_t = rows(lambda k: k[0] == "liability" and _is_non_current_liability(k[1], k[2]))
    cl, cl_t = rows(lambda k: k[0] == "liability" and not _is_non_current_liability(k[1], k[2]))
    eq, eq_t = rows(lambda k: k[0] == "equity")
    re_now, re_comp = _cum_profit(db, cid, at), _cum_profit(db, cid, comp_at)
    total_assets = {"now": round(nca_t["now"] + ca_t["now"], 2), "comp": round(nca_t["comp"] + ca_t["comp"], 2)}
    total_equity = {"now": round(eq_t["now"] + re_now, 2), "comp": round(eq_t["comp"] + re_comp, 2)}
    total_le = {s: round(ncl_t[s] + cl_t[s] + total_equity[s], 2) for s in ("now", "comp")}
    return {
        "non_current_assets": nca, "total_non_current_assets": nca_t,
        "current_assets": ca, "total_current_assets": ca_t, "total_assets": total_assets,
        "equity": eq, "retained_earnings": {"now": re_now, "comp": re_comp}, "total_equity": total_equity,
        "non_current_liabilities": ncl, "total_non_current_liabilities": ncl_t,
        "current_liabilities": cl, "total_current_liabilities": cl_t,
        "total_liabilities_and_equity": total_le,
        "balanced": all(abs(total_assets[s] - total_le[s]) < 1.0 for s in ("now", "comp")),
    }


def _cash_flow(db, cid, start: datetime, end_excl: datetime, net_profit: float, pl: dict) -> dict:
    open_b, close_b = _balances(db, cid, start - _EPS), _balances(db, cid, end_excl - _EPS)
    buckets = {b: 0.0 for b in ("receivables", "inventory", "vat", "payables", "tax", "investing", "financing")}
    cash_open = cash_close = 0.0
    for k in set(open_b) | set(close_b):
        atype = AccountType(k[0])
        delta = close_b.get(k, 0.0) - open_b.get(k, 0.0)
        b = _cash_flow_bucket(atype, k[1], k[2])
        if b == "cash":
            cash_open += open_b.get(k, 0.0)
            cash_close += close_b.get(k, 0.0)
            continue
        buckets[b] += -delta if atype == AccountType.asset else delta
    depreciation = round(sum(v for k, v in pl.items() if k[0] in ("expense", "cogs") and _is_dep(k[2])), 2)
    buckets["investing"] -= depreciation          # accumulated depreciation moved: that part is non-cash
    b = {k: round(v, 2) for k, v in buckets.items()}
    operating = round(net_profit + depreciation + b["receivables"] + b["inventory"] + b["vat"] + b["payables"] + b["tax"], 2)
    net = round(operating + b["investing"] + b["financing"], 2)
    return {
        "net_profit": round(net_profit, 2), "depreciation": depreciation,
        "receivables": b["receivables"], "inventory": b["inventory"], "vat": b["vat"],
        "payables": b["payables"], "tax": b["tax"],
        "operating": operating, "investing": b["investing"], "financing": b["financing"],
        "net_change": net, "opening_cash": round(cash_open, 2), "closing_cash": round(cash_close, 2),
        "reconciles": abs(round(cash_open + net - cash_close, 2)) < 1.0,
    }


def build_figures(db: Session, company, period: str) -> dict:
    y, m = _parse_period(period)
    cid = company.id
    m_start, m_end = _month_bounds(y, m)
    fy_start = _fy_start(company, date(y, m, 1))
    ytd_start = datetime.combine(fy_start, datetime.min.time())
    py_m_start, py_m_end = _month_bounds(y - 1, m)
    py_fy_start = _fy_start(company, date(y - 1, m, 1))
    py_ytd_start = datetime.combine(py_fy_start, datetime.min.time())

    pls = {
        "month":    _pl_by_account(db, cid, m_start, m_end),
        "month_py": _pl_by_account(db, cid, py_m_start, py_m_end),
        "ytd":      _pl_by_account(db, cid, ytd_start, m_end),
        "ytd_py":   _pl_by_account(db, cid, py_ytd_start, py_m_end),
    }
    inc = _income_statement(pls)
    fy_end_prev = ytd_start - _EPS
    bs = _balance_sheet(db, cid, m_end - _EPS, fy_end_prev)
    cf = {
        "month": _cash_flow(db, cid, m_start, m_end, inc["net_profit_before_tax"]["month"], pls["month"]),
        "ytd":   _cash_flow(db, cid, ytd_start, m_end, inc["net_profit_before_tax"]["ytd"], pls["ytd"]),
    }
    return {
        "period": period,
        "period_label": _month_label(y, m),
        "company": {"id": cid, "name": company.name},
        "financial_year": {"start": fy_start.isoformat(), "label": f"{fy_start.strftime('%B %Y')} to {_month_label(y, m)}"},
        "comparatives": {"month_py": _month_label(y - 1, m),
                         "ytd_py": f"{py_fy_start.strftime('%B %Y')} to {_month_label(y - 1, m)}",
                         "balance_sheet": f"{fy_end_prev.strftime('%d %b %Y')}"},
        "income_statement": inc,
        "balance_sheet": bs,
        "cash_flow": cf,
        "has_activity": any(pls["month"]) or any(pls["ytd"]),
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
    }


# ── commentary ────────────────────────────────────────────────────────────────

def _r0(v) -> str:
    v = v or 0
    s = f"R{abs(v):,.0f}"
    return f"({s})" if v < 0 else s


def _chg(a, b) -> str:
    if not b:
        return "n/a"
    return f"{(a - b) / abs(b) * 100:+.1f}%"


def _summary_for_ai(f: dict) -> str:
    inc, bs = f["income_statement"], f["balance_sheet"]
    L = [f"Company: {f['company']['name']}", f"Month: {f['period_label']}", f"Financial year to date: {f['financial_year']['label']}"]
    for key, label in (("total_revenue", "Revenue"), ("total_cogs", "Cost of sales"), ("gross_profit", "Gross profit"),
                       ("total_opex", "Operating expenses"), ("total_finance_costs", "Finance costs"),
                       ("net_profit_before_tax", "Net profit before tax")):
        v = inc[key]
        L.append(f"{label}: month {_r0(v['month'])} (same month last year {_r0(v['month_py'])}, {_chg(v['month'], v['month_py'])}); "
                 f"YTD {_r0(v['ytd'])} (last year YTD {_r0(v['ytd_py'])}, {_chg(v['ytd'], v['ytd_py'])})")
    gm, nm = inc["gross_margin_pct"], inc["net_margin_pct"]
    L.append(f"Gross margin: month {gm['month']}% vs {gm['month_py']}%; YTD {gm['ytd']}% vs {gm['ytd_py']}%")
    L.append(f"Net margin: month {nm['month']}%; YTD {nm['ytd']}%")
    top = sorted(inc["opex"], key=lambda r: -abs(r["ytd"]))[:6]
    L.append("Largest expenses YTD (vs last year YTD): " + "; ".join(f"{r['name']} {_r0(r['ytd'])} ({_r0(r['ytd_py'])})" for r in top))
    for r in inc["revenue"]:
        L.append(f"Revenue line {r['name']}: month {_r0(r['month'])}, YTD {_r0(r['ytd'])} (last year YTD {_r0(r['ytd_py'])})")
    L.append(f"Cash: {_r0(f['cash_flow']['month']['opening_cash'])} at start of month, {_r0(f['cash_flow']['month']['closing_cash'])} at month-end; "
             f"operating cash flow month {_r0(f['cash_flow']['month']['operating'])}, YTD {_r0(f['cash_flow']['ytd']['operating'])}; "
             f"investing YTD {_r0(f['cash_flow']['ytd']['investing'])}; financing YTD {_r0(f['cash_flow']['ytd']['financing'])}")
    L.append(f"Balance sheet at month-end: total assets {_r0(bs['total_assets']['now'])} (year-end {_r0(bs['total_assets']['comp'])}), "
             f"current assets {_r0(bs['total_current_assets']['now'])}, current liabilities {_r0(bs['total_current_liabilities']['now'])}, "
             f"non-current liabilities {_r0(bs['total_non_current_liabilities']['now'])}, equity {_r0(bs['total_equity']['now'])}")
    return "\n".join(L)


def _template_commentary(f: dict) -> str:
    inc, cf = f["income_statement"], f["cash_flow"]
    rev, gp, np_ = inc["total_revenue"], inc["gross_profit"], inc["net_profit_before_tax"]
    gm = inc["gross_margin_pct"]
    paras = [
        f"Revenue for {f['period_label']} was {_r0(rev['month'])}, compared with {_r0(rev['month_py'])} in the same month last year "
        f"({_chg(rev['month'], rev['month_py'])}). Year to date revenue is {_r0(rev['ytd'])} against {_r0(rev['ytd_py'])} last year.",
        f"Gross profit for the month was {_r0(gp['month'])} at a margin of {gm['month'] if gm['month'] is not None else 'n/a'}%, "
        f"and {gm['ytd'] if gm['ytd'] is not None else 'n/a'}% for the year to date.",
        f"Net profit before tax was {_r0(np_['month'])} for the month and {_r0(np_['ytd'])} for the year to date "
        f"(last year to date: {_r0(np_['ytd_py'])}).",
        f"Cash moved from {_r0(cf['month']['opening_cash'])} to {_r0(cf['month']['closing_cash'])} during the month; "
        f"operating activities generated {_r0(cf['month']['operating'])}.",
    ]
    return "\n\n".join(paras)


def draft_commentary(f: dict) -> tuple:
    """(text, source): AI draft from the figures, or a plain template when AI is unavailable."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return _template_commentary(f), "template"
    prompt = (
        "You are a South African chartered accountant writing the commentary for a client's monthly management "
        "report to its directors. Use ONLY the figures below; never invent numbers, causes or events. Where a "
        "change needs an explanation the figures do not give, say it should be confirmed with management.\n\n"
        f"{_summary_for_ai(f)}\n\n"
        "Write 4 to 6 short paragraphs in plain business English, under 250 words in total, no headings, no bullet "
        "symbols, no markdown. Cover: revenue against last year, gross margin, the main cost movements, profit, "
        "and cash. Amounts in Rand rounded to the nearest rand (e.g. R1,234,567). End with one practical point "
        "for management's attention."
    )
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=key)
        resp = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=700,
                                      messages=[{"role": "user", "content": prompt}])
        text = (resp.content[0].text or "").strip()
        if text:
            return text, "ai"
    except Exception as e:
        logger.error(f"management report commentary: {e}")
    return _template_commentary(f), "template"


# ── PDF ───────────────────────────────────────────────────────────────────────

def render_pdf(f: dict, commentary: str, prepared_by: str = "") -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    from xml.sax.saxutils import escape

    ink, mid, line = colors.HexColor("#1f2937"), colors.HexColor("#6b7280"), colors.HexColor("#d1d5db")
    band = colors.HexColor("#f3f4f6")
    st_title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=18, leading=23, textColor=ink, spaceAfter=4)
    st_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=10, leading=14, textColor=mid, spaceAfter=10)
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12, textColor=ink, spaceBefore=10, spaceAfter=6)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=ink, spaceAfter=6)
    st_note = ParagraphStyle("n", fontName="Helvetica", fontSize=7.5, textColor=mid, leading=10)

    def money(v):
        v = v or 0
        if abs(v) < 0.5:
            return "-"
        s = f"{abs(v):,.0f}"
        return f"({s})" if v < 0 else s

    def pct(v):
        return "" if v is None else f"{v:.1f}%"

    def table(data, widths, bold_rows=(), band_rows=(), header=True):
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                 ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("TOPPADDING", (0, 0), (-1, -1), 2.5)]
        if header:
            style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("TEXTCOLOR", (0, 0), (-1, 0), mid),
                      ("LINEBELOW", (0, 0), (-1, 0), 0.6, line)]
        for r in bold_rows:
            style += [("FONT", (0, r), (-1, r), "Helvetica-Bold", 8.5), ("LINEABOVE", (1, r), (-1, r), 0.5, line)]
        for r in band_rows:
            style += [("BACKGROUND", (0, r), (-1, r), band)]
        t.setStyle(TableStyle(style))
        return t

    inc, bs, cf = f["income_statement"], f["balance_sheet"], f["cash_flow"]
    cmp = f["comparatives"]
    story = [Paragraph(escape(f["company"]["name"]), st_title),
             Paragraph(f"Management report for {escape(f['period_label'])} &middot; financial year to date "
                       f"{escape(f['financial_year']['label'])}", st_sub)]

    # commentary
    story.append(Paragraph("Commentary", st_h))
    for para in [p.strip() for p in (commentary or "").split("\n") if p.strip()]:
        story.append(Paragraph(escape(para), st_p))

    # key figures
    kf = [["", f["period_label"], cmp["month_py"], "Year to date", "Last year to date"]]
    for key, label in (("total_revenue", "Revenue"), ("gross_profit", "Gross profit"),
                       ("net_profit_before_tax", "Net profit before tax")):
        v = inc[key]
        kf.append([label, money(v["month"]), money(v["month_py"]), money(v["ytd"]), money(v["ytd_py"])])
    gm, nm = inc["gross_margin_pct"], inc["net_margin_pct"]
    kf.append(["Gross margin", pct(gm["month"]), pct(gm["month_py"]), pct(gm["ytd"]), pct(gm["ytd_py"])])
    kf.append(["Net margin", pct(nm["month"]), pct(nm["month_py"]), pct(nm["ytd"]), pct(nm["ytd_py"])])
    kf.append(["Cash at month-end", money(cf["month"]["closing_cash"]), "", "", ""])
    story += [Paragraph("Key figures (Rand)", st_h), table(kf, [52 * mm, 30 * mm, 30 * mm, 30 * mm, 32 * mm])]

    # income statement
    story.append(PageBreak())
    story.append(Paragraph("Income statement (Rand)", st_h))
    cols = ["month", "month_py", "ytd", "ytd_py"]
    data = [["", f["period_label"], cmp["month_py"], "Year to date", "Last year to date"]]
    bold, bands = [], []

    def add_section(title, rows, total, total_label):
        bands.append(len(data)); data.append([title, "", "", "", ""])
        for r in rows:
            data.append(["   " + r["name"]] + [money(r[c]) for c in cols])
        bold.append(len(data)); data.append([total_label] + [money(total[c]) for c in cols])

    add_section("Revenue", inc["revenue"], inc["total_revenue"], "Total revenue")
    if inc["cogs"]:
        add_section("Cost of sales", inc["cogs"], inc["total_cogs"], "Total cost of sales")
    bold.append(len(data)); data.append(["Gross profit"] + [money(inc["gross_profit"][c]) for c in cols])
    data.append(["   Gross margin"] + [pct(inc["gross_margin_pct"][c]) for c in cols])
    add_section("Operating expenses", inc["opex"], inc["total_opex"], "Total operating expenses")
    bold.append(len(data)); data.append(["Operating profit"] + [money(inc["operating_profit"][c]) for c in cols])
    if inc["finance_costs"]:
        add_section("Finance costs", inc["finance_costs"], inc["total_finance_costs"], "Total finance costs")
    bold.append(len(data)); data.append(["Net profit before tax"] + [money(inc["net_profit_before_tax"][c]) for c in cols])
    story.append(table(data, [62 * mm, 27 * mm, 27 * mm, 27 * mm, 31 * mm], bold_rows=bold, band_rows=bands))

    # balance sheet
    story.append(PageBreak())
    story.append(Paragraph("Balance sheet (Rand)", st_h))
    data = [["", f"End of {f['period_label']}", cmp["balance_sheet"]]]
    bold, bands = [], []

    def bs_section(title, rows, total, total_label):
        if not rows:
            return
        bands.append(len(data)); data.append([title, "", ""])
        for r in rows:
            data.append(["   " + r["name"], money(r["now"]), money(r["comp"])])
        bold.append(len(data)); data.append([total_label, money(total["now"]), money(total["comp"])])

    bs_section("Non-current assets", bs["non_current_assets"], bs["total_non_current_assets"], "Total non-current assets")
    bs_section("Current assets", bs["current_assets"], bs["total_current_assets"], "Total current assets")
    bold.append(len(data)); data.append(["TOTAL ASSETS", money(bs["total_assets"]["now"]), money(bs["total_assets"]["comp"])])
    bands.append(len(data)); data.append(["Equity", "", ""])
    for r in bs["equity"]:
        data.append(["   " + r["name"], money(r["now"]), money(r["comp"])])
    data.append(["   Retained earnings (accumulated profit)", money(bs["retained_earnings"]["now"]), money(bs["retained_earnings"]["comp"])])
    bold.append(len(data)); data.append(["Total equity", money(bs["total_equity"]["now"]), money(bs["total_equity"]["comp"])])
    bs_section("Non-current liabilities", bs["non_current_liabilities"], bs["total_non_current_liabilities"], "Total non-current liabilities")
    bs_section("Current liabilities", bs["current_liabilities"], bs["total_current_liabilities"], "Total current liabilities")
    bold.append(len(data)); data.append(["TOTAL EQUITY AND LIABILITIES", money(bs["total_liabilities_and_equity"]["now"]),
                                         money(bs["total_liabilities_and_equity"]["comp"])])
    story.append(table(data, [100 * mm, 37 * mm, 37 * mm], bold_rows=bold, band_rows=bands))

    # cash flow
    story.append(Spacer(1, 6 * mm))
    rows = [("Net profit before tax", "net_profit"), ("Add back depreciation", "depreciation"),
            ("(Increase) / decrease in receivables and other assets", "receivables"),
            ("(Increase) / decrease in inventory", "inventory"), ("VAT movement", "vat"),
            ("Increase / (decrease) in payables and accruals", "payables"), ("Income tax movement", "tax")]
    data = [["", f["period_label"], "Year to date"]]
    for label, k in rows:
        if abs(cf["month"][k]) >= 0.5 or abs(cf["ytd"][k]) >= 0.5:
            data.append(["   " + label, money(cf["month"][k]), money(cf["ytd"][k])])
    bold = [len(data)]; data.append(["Cash from operating activities", money(cf["month"]["operating"]), money(cf["ytd"]["operating"])])
    data.append(["Cash from investing activities", money(cf["month"]["investing"]), money(cf["ytd"]["investing"])])
    data.append(["Cash from financing activities", money(cf["month"]["financing"]), money(cf["ytd"]["financing"])])
    bold.append(len(data)); data.append(["Net change in cash", money(cf["month"]["net_change"]), money(cf["ytd"]["net_change"])])
    data.append(["Cash at start", money(cf["month"]["opening_cash"]), money(cf["ytd"]["opening_cash"])])
    bold.append(len(data)); data.append(["Cash at end", money(cf["month"]["closing_cash"]), money(cf["ytd"]["closing_cash"])])
    story.append(KeepTogether([Paragraph("Cash flow (Rand)", st_h), table(data, [100 * mm, 37 * mm, 37 * mm], bold_rows=bold)]))

    note = ("Unaudited management accounts prepared from the general ledger on the accrual basis: revenue is "
            "recognised when invoiced, whether or not it has been paid. Figures may change once month-end and "
            "year-end adjustments are finalised. Net profit is before income tax.")
    if prepared_by:
        note = f"Prepared by {escape(prepared_by)}. " + note
    story += [Spacer(1, 6 * mm), Paragraph(note, st_note)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(mid)
        canvas.drawString(18 * mm, 10 * mm, f"{f['company']['name']} - management report {f['period_label']}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"{f['company']['name']} management report {f['period_label']}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ── storage helpers ───────────────────────────────────────────────────────────

def _row(db, cid, period, create=False, user_id=None):
    r = db.query(ManagementReport).filter(ManagementReport.company_id == cid, ManagementReport.period == period).first()
    if r is None and create:
        last = (db.query(ManagementReport).filter(ManagementReport.company_id == cid, ManagementReport.status == "sent")
                .order_by(ManagementReport.sent_at.desc()).first())
        company = db.query(Company).filter(Company.id == cid).first()
        r = ManagementReport(company_id=cid, period=period, status="draft", created_by=user_id,
                             recipients=(last.recipients if last and last.recipients else (company.email or "")))
        db.add(r)
        db.flush()
    return r


def _clean_recipients(raw) -> List[str]:
    items = raw if isinstance(raw, list) else re.split(r"[,;\s]+", raw or "")
    out, seen = [], set()
    for e in (x.strip() for x in items):
        if not e:
            continue
        if not _EMAIL_RE.match(e):
            raise HTTPException(400, f"'{e}' is not a valid email address.")
        if e.lower() not in seen:
            seen.add(e.lower())
            out.append(e)
    if len(out) > 15:
        raise HTTPException(400, "At most 15 recipients.")
    return out


def _report_out(r) -> dict:
    if r is None:
        return {"status": "new", "commentary": "", "commentary_source": None, "recipients": "", "sent_at": None, "sent_to": None}
    return {"status": r.status, "commentary": r.commentary or "", "commentary_source": r.commentary_source,
            "recipients": r.recipients or "", "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "sent_to": r.sent_to, "updated_at": r.updated_at.isoformat() if r.updated_at else None}


def _figures_for(db, company, period, r):
    """Frozen figures for a sent report, live ledger figures otherwise."""
    if r is not None and r.status == "sent" and r.data_json:
        try:
            f = json.loads(r.data_json)
            f["frozen"] = True
            return f
        except ValueError:
            pass
    f = build_figures(db, company, period)
    f["frozen"] = False
    return f


def _user_name(cu) -> str:
    first, last = getattr(cu, "first_name", "") or "", getattr(cu, "last_name", "") or ""
    return (first + " " + last).strip()


# ── routes ────────────────────────────────────────────────────────────────────

class ReportUpdate(BaseModel):
    commentary: Optional[str] = None
    recipients: Optional[str] = None


class SendRequest(BaseModel):
    recipients: Optional[str] = None


@router.get("")
def list_reports(current_user: User = Depends(require_role(*_ROLES)), db: Session = Depends(get_db)):
    rows = (db.query(ManagementReport).filter(ManagementReport.company_id == current_user.company_id)
            .order_by(ManagementReport.period.desc()).limit(36).all())
    return [{"period": r.period, **_report_out(r)} for r in rows]


@router.get("/{period}")
def get_report(period: str, current_user: User = Depends(require_role(*_ROLES)), db: Session = Depends(get_db)):
    _parse_period(period)
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    r = _row(db, company.id, period)
    return {"figures": _figures_for(db, company, period, r), "report": _report_out(r)}


@router.put("/{period}")
def save_report(period: str, data: ReportUpdate, current_user: User = Depends(require_role(*_ROLES)),
                db: Session = Depends(get_db)):
    _parse_period(period)
    r = _row(db, current_user.company_id, period, create=True, user_id=current_user.id)
    if r.status == "sent":
        raise HTTPException(409, "This report has been sent. Reopen it to make changes.")
    if data.commentary is not None:
        if data.commentary != (r.commentary or ""):
            r.commentary_source = "edited" if r.commentary_source in ("ai", "template", "edited") else "manual"
        r.commentary = data.commentary[:20000]
    if data.recipients is not None:
        r.recipients = ", ".join(_clean_recipients(data.recipients))
    r.updated_at = datetime.utcnow()
    db.commit()
    return _report_out(r)


@router.post("/{period}/draft-commentary")
def make_commentary(period: str, current_user: User = Depends(require_role(*_ROLES)), db: Session = Depends(get_db)):
    _parse_period(period)
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    r = _row(db, company.id, period, create=True, user_id=current_user.id)
    if r.status == "sent":
        raise HTTPException(409, "This report has been sent. Reopen it to make changes.")
    f = build_figures(db, company, period)
    if not f["has_activity"]:
        raise HTTPException(400, "There are no transactions for this month or year to date to comment on.")
    text, source = draft_commentary(f)
    r.commentary, r.commentary_source, r.updated_at = text, source, datetime.utcnow()
    db.commit()
    return _report_out(r)


@router.get("/{period}/pdf")
def report_pdf(period: str, current_user: User = Depends(require_role(*_ROLES)), db: Session = Depends(get_db)):
    _parse_period(period)
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    r = _row(db, company.id, period)
    f = _figures_for(db, company, period, r)
    pdf = render_pdf(f, (r.commentary if r else "") or "", _user_name(current_user))
    fname = re.sub(r"[^A-Za-z0-9]+", "_", f"{company.name}_management_report_{period}").strip("_") + ".pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/{period}/send")
def send_report(period: str, data: SendRequest, current_user: User = Depends(require_role(*_ROLES)),
                db: Session = Depends(get_db)):
    y, m = _parse_period(period)
    _start, end_excl = _month_bounds(y, m)
    if end_excl > datetime.utcnow() + timedelta(hours=2):
        raise HTTPException(400, "The month has not ended yet. Send the report after month-end close.")
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    r = _row(db, company.id, period, create=True, user_id=current_user.id)
    if data.recipients is not None:
        r.recipients = ", ".join(_clean_recipients(data.recipients))
    to = _clean_recipients(r.recipients or "")
    if not to:
        raise HTTPException(400, "Add at least one recipient.")
    if not (r.commentary or "").strip():
        raise HTTPException(400, "Add the commentary before sending (draft it with AI or write it).")

    f = build_figures(db, company, period)
    sender_name = _user_name(current_user)
    pdf = render_pdf(f, r.commentary, sender_name)
    fname = re.sub(r"[^A-Za-z0-9]+", "_", f"{company.name}_management_report_{period}").strip("_") + ".pdf"
    from email_service import send_email, _wrap
    from xml.sax.saxutils import escape
    first_para = escape((r.commentary or "").strip().split("\n")[0])[:900]
    html = _wrap(
        f"<p>Good day,</p><p>Please find attached the management report for <strong>{escape(company.name)}</strong> "
        f"for <strong>{escape(f['period_label'])}</strong>.</p><p style='color:#374151'>{first_para}</p>"
        f"<p>The full commentary, income statement, balance sheet and cash flow are in the attached PDF.</p>"
        f"<p>Kind regards,<br>{escape(sender_name or 'Your accountant')}</p>",
        transactional=True)
    subject = f"{company.name}: management report for {f['period_label']}"
    sent, failed = [], []
    for addr in to:
        ok = send_email(addr, subject, html, attachments=[{"Name": fname, "Content": pdf}])
        (sent if ok else failed).append(addr)
    if not sent:
        db.commit()
        raise HTTPException(502, "The email could not be sent. Check the email service settings and try again.")
    r.status, r.sent_at, r.sent_by = "sent", datetime.utcnow(), current_user.id
    r.sent_to = ", ".join(sent)
    r.data_json = json.dumps(f)
    r.updated_at = datetime.utcnow()
    db.commit()
    log_action(db, company.id, current_user, "management_report_sent", target_type="management_report",
               target_id=r.id, detail=f"{period} to {', '.join(sent)}")
    return {**_report_out(r), "failed": failed}


@router.post("/{period}/reopen")
def reopen_report(period: str, current_user: User = Depends(require_role(*_ROLES)), db: Session = Depends(get_db)):
    _parse_period(period)
    r = _row(db, current_user.company_id, period)
    if r is None:
        raise HTTPException(404, "No report for this month.")
    r.status, r.updated_at = "draft", datetime.utcnow()
    db.commit()
    return _report_out(r)
