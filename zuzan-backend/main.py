from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zuzan.api")

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ZuZan backend...")
    from database import init_db, SessionLocal, Company
    init_db()
    logger.info("Database ready")
    # Backfill journal for any existing companies that have no entries yet
    try:
        from journal import backfill_company, init_accounts
        from database import JournalEntry
        db = SessionLocal()
        companies = db.query(Company).all()
        for co in companies:
            has_entries = db.query(JournalEntry).filter(JournalEntry.company_id == co.id).count()
            if has_entries == 0:
                logger.info(f"Backfilling journal for company {co.id} ({co.name})...")
                result = backfill_company(co.id, db)
                logger.info(f"  Backfill done: {result}")
            else:
                init_accounts(co.id, db)   # ensure CoA exists even if already backfilled
        db.close()
        logger.info("Journal backfill complete")
    except Exception as e:
        logger.warning(f"Journal backfill failed (non-fatal): {e}")
    # Encrypt any existing plain-text bank fields
    try:
        from crypto import encrypt_field, _is_fernet_token, encryption_enabled
        from database import Employee, Supplier
        if encryption_enabled():
            db = SessionLocal()
            migrated = 0
            # Company bank fields
            for co in db.query(Company).all():
                changed = False
                for attr in ("bank_name", "bank_account", "bank_branch"):
                    val = getattr(co, attr)
                    if val and not _is_fernet_token(val):
                        setattr(co, attr, encrypt_field(val)); changed = True
                if changed: migrated += 1
            # Employee bank fields
            for emp in db.query(Employee).all():
                changed = False
                for attr in ("bank_name", "bank_account", "account_number", "branch_code"):
                    val = getattr(emp, attr)
                    if val and not _is_fernet_token(val):
                        setattr(emp, attr, encrypt_field(val)); changed = True
                if changed: migrated += 1
            # Supplier bank fields
            for sup in db.query(Supplier).all():
                changed = False
                for attr in ("bank_name", "account_number", "branch_code"):
                    val = getattr(sup, attr)
                    if val and not _is_fernet_token(val):
                        setattr(sup, attr, encrypt_field(val)); changed = True
                if changed: migrated += 1
            db.commit(); db.close()
            logger.info(f"Bank field encryption migration complete — {migrated} records encrypted")
        else:
            logger.warning("Skipping bank field migration — FIELD_ENCRYPTION_KEY not set")
    except Exception as e:
        logger.warning(f"Bank field encryption migration failed (non-fatal): {e}")
    yield


app = FastAPI(title="ZuZan API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from starlette.types import ASGIApp, Receive, Scope, Send as _Send
from starlette.responses import Response as _Resp
from starlette.datastructures import MutableHeaders

_CORS_HEADERS = {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD",
    "access-control-allow-headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With, X-API-Key, X-Admin-Secret",
    "access-control-max-age": "86400",
}

class _CORSMiddleware:
    """Raw ASGI CORS middleware — avoids BaseHTTPMiddleware header-stripping bug."""
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: _Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("method") == "OPTIONS":
            response = _Resp(content=b"", status_code=200, headers=_CORS_HEADERS)
            await response(scope, receive, send)
            return
        async def _send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("access-control-allow-origin", "*")
            await send(message)
        await self.app(scope, receive, _send_with_cors)

app.add_middleware(_CORSMiddleware)

@app.get("/health")
async def health(): return {"status": "ok"}

from auth import router as auth_router
from companies import (
    router as companies_router,
    invoices_router,
    expenses_router,
    employees_router,
    bank_router,
)
from payroll import payroll_router, reports_router, payments_router
from api_keys import router as api_keys_router
from inventory import router as inventory_router
from customers import router as customers_router
from suppliers import router as suppliers_router
from purchase_orders import router as po_router
from quotes import router as quotes_router
from budgets import router as budgets_router
from journal import router as journal_router
from leave import router as leave_router

app.include_router(auth_router,      prefix="/auth",      tags=["Auth"])
app.include_router(companies_router, prefix="/companies", tags=["Companies"])
app.include_router(invoices_router,  prefix="/invoices",  tags=["Invoices"])
app.include_router(expenses_router,  prefix="/expenses",  tags=["Expenses"])
app.include_router(employees_router, prefix="/employees", tags=["Employees"])
app.include_router(payroll_router,   prefix="/payroll",   tags=["Payroll"])
app.include_router(payments_router,  prefix="/payments",  tags=["Payments"])
app.include_router(reports_router,   prefix="/reports",   tags=["Reports"])
app.include_router(bank_router,      prefix="/bank",      tags=["Bank Import"])
app.include_router(api_keys_router,  prefix="/api-keys",      tags=["API Keys"])
app.include_router(inventory_router, prefix="/inventory",     tags=["Inventory"])
app.include_router(customers_router, prefix="/customers",     tags=["Customers"])
app.include_router(suppliers_router, prefix="/suppliers",     tags=["Suppliers"])
app.include_router(po_router,        prefix="/purchase-orders", tags=["Purchase Orders"])
app.include_router(quotes_router,    prefix="/quotes",          tags=["Quotes"])
app.include_router(budgets_router,   prefix="/budgets",         tags=["Budgets"])
app.include_router(journal_router,   prefix="/journal",         tags=["Journal"])
app.include_router(leave_router,     prefix="/leave",           tags=["Leave"])


@app.get("/")
async def root():
    return {"status": "ZuZan API running", "version": "1.0.0"}


# ── PUBLIC API (API key authenticated) ───────────────────────────────────────
from fastapi import Header, Depends, HTTPException
import os as _os
from fastapi.responses import HTMLResponse as _HTML
from database import Company as _Company, User as _User, Invoice as _Invoice, Expense as _Expense, Employee as _Employee
from sqlalchemy import func as _func

ADMIN_SECRET = _os.environ.get("ADMIN_SECRET", "")
from api_keys import get_company_from_api_key
from database import Invoice, Expense, Employee
from sqlalchemy.orm import Session

def get_db_session():
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_api_key(x_api_key: str = Header(...), db: Session = Depends(get_db_session)):
    company, key_record = get_company_from_api_key(x_api_key, db)
    if not company:
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")
    return company, key_record, db

@app.get("/v1/invoices", tags=["Public API"])
async def api_list_invoices(auth=Depends(require_api_key)):
    company, _, db = auth
    items = db.query(Invoice).filter(Invoice.company_id == company.id).all()
    return [{"id":i.id,"invoice_number":i.invoice_number,"client_name":i.client_name,"amount":i.total_amount,"status":str(i.status.value),"issue_date":str(i.issue_date)[:10],"due_date":str(i.due_date)[:10] if i.due_date else None} for i in items]

@app.get("/v1/expenses", tags=["Public API"])
async def api_list_expenses(auth=Depends(require_api_key)):
    company, _, db = auth
    items = db.query(Expense).filter(Expense.company_id == company.id).all()
    return [{"id":e.id,"vendor":e.vendor,"description":e.description,"amount":e.amount,"category":e.category,"date":str(e.expense_date)[:10] if e.expense_date else None} for e in items]

@app.get("/v1/employees", tags=["Public API"])
async def api_list_employees(auth=Depends(require_api_key)):
    company, key_record, db = auth
    if "payroll" not in (key_record.scopes or ""):
        raise HTTPException(status_code=403, detail="This API key does not have the 'payroll' scope.")
    items = db.query(Employee).filter(Employee.company_id == company.id, Employee.is_active == True).all()
    return [{"id":e.id,"name":f"{e.first_name} {e.last_name}","position":e.position,"department":e.department,"gross_salary":e.gross_salary} for e in items]

@app.get("/v1/summary", tags=["Public API"])
async def api_summary(auth=Depends(require_api_key)):
    company, _, db = auth
    from payroll import _to_zar
    from database import InvoiceStatus, PurchaseOrder
    paid_invs  = db.query(Invoice).filter(Invoice.company_id==company.id, Invoice.status==InvoiceStatus.paid).all()
    out_invs   = db.query(Invoice).filter(Invoice.company_id==company.id, Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])).all()
    total_revenue  = sum(_to_zar(i) for i in paid_invs)
    # Expenses ex-VAT
    exp_rows = db.query(Expense).filter(Expense.company_id==company.id).all()
    total_expenses = sum(e.amount - (e.vat_amount or 0) for e in exp_rows)
    # Add PO COGS (received/partial/paid purchase orders)
    po_cogs = sum(
        po.total_amount or 0
        for po in db.query(PurchaseOrder).filter(
            PurchaseOrder.company_id==company.id,
            PurchaseOrder.status.in_(["received", "partial", "paid"]),
        ).all()
    )
    total_expenses = total_expenses + po_cogs
    outstanding    = sum(_to_zar(i) for i in out_invs)
    return {"company":company.name,"total_revenue":round(total_revenue,2),"total_expenses":round(total_expenses,2),"outstanding":round(outstanding,2),"net_profit":round(total_revenue-total_expenses,2)}


# ── AI CHAT ───────────────────────────────────────────────────────────────────
from pydantic import BaseModel as BM
class ChatRequest(BM):
    message: str
    context: str = ""

ZUZAN_SYSTEM_PROMPT = """You are ZuZan AI, the built-in assistant for ZuZan — a South African bookkeeping and payroll platform for SMEs. You help users navigate the app and understand SA tax/accounting rules.

ZuZan's modules and how they work:
- Sales → Invoices: Create invoices (+ New Invoice), mark as paid, send to clients by email. INV-XXXX numbering. 15% VAT calculated automatically. Multi-currency (ZAR/USD) supported.
- Sales → Quotes: Create quotes (+ New Quote), set validity date, update status (Draft/Sent/Accepted/Declined), convert accepted quotes to invoices.
- Expenses: Add expenses (+ Add Expense), scan receipts with camera, categorise to chart-of-accounts codes (6000-7300). Input VAT tracked automatically.
- Procurement → Purchase Orders: Create POs (+ New PO), send to suppliers by email (📧 Send to Supplier), receive goods (📦 Receive Goods), mark as paid. Statuses: Draft/Sent/Received/Partial/Paid/Cancelled. Edit POs in draft/sent status.
- Procurement → Suppliers: Manage supplier details including email addresses.
- Customers: Manage customer records.
- Payroll: Run monthly payroll, calculate PAYE/UIF/SDL automatically, download EMP201. SDL only applies if annual payroll > R500k.
- Reports: P&L, Balance Sheet, Trial Balance, VAT201, Reconciliation, Journal Viewer. Filter by date range and financial year.
- Budgeting: Set monthly budgets per account, track actuals vs budget.
- Accounts: Chart of accounts, journal entries, double-entry bookkeeping.
- Settings: Company details, banking info, VAT number, financial year.
- Dashboard: Revenue, expenses, outstanding invoices, cash position.

SA tax rules you know:
- VAT: Standard rate 15%. VAT201 due monthly or bi-monthly. Late = 10% penalty + interest. Zero-rated: basic foods, exports.
- PAYE: Withheld monthly. EMP201 due 7th of following month. 2025/2026 primary rebate R17,235.
- UIF: 1% employee + 1% employer, capped at R177.12/month each (R17,712 monthly gross ceiling).
- SDL: 1% of gross payroll if annual payroll exceeds R500,000.
- Provisional tax (IRP6): Twice yearly — 31 August and 28 February.
- Dividends tax: 20%, withheld by company.
- Entertainment expenses: 50% deductible, input VAT not claimable.
- Bad debts: Deductible when irrecoverable — account 7300.
- Wear & tear: Computers 3 years, vehicles 5 years.

Response style:
- Be concise and practical. Give step-by-step instructions when explaining how to do something in the app.
- Use ZAR (R) for amounts. Reference the correct tab/button names exactly as they appear in ZuZan.
- If a question is outside bookkeeping/tax/ZuZan scope, politely redirect to the relevant tab or suggest consulting an accountant for complex matters.
- Keep responses under 120 words unless a detailed explanation is genuinely needed.
- Never make up features that don't exist in ZuZan."""

_ANTHROPIC_KEY = _os.environ.get("ANTHROPIC_API_KEY", "")

@app.post("/ai/chat")
@limiter.limit("30/minute")
async def ai_chat(request: Request, data: ChatRequest, current_user=Depends(__import__("auth").get_current_user)):
    if not _ANTHROPIC_KEY:
        return {"reply": "AI assistant is not configured. Please contact your administrator to set up the ANTHROPIC_API_KEY."}

    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=_ANTHROPIC_KEY)

        user_msg = data.message
        if data.context:
            user_msg = f"[User is currently on the {data.context} section of ZuZan]\n\n{data.message}"

        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=300,
            system=ZUZAN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        reply = response.content[0].text.strip()
        return {"reply": reply}

    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return _keyword_fallback(data.message.lower(), data.context.lower())


def _keyword_fallback(msg: str, ctx: str) -> dict:
    if ("invoice" in msg and any(x in msg for x in ["create","new","add","make","how","generate"])):
        return {"reply":"To create an invoice: go to Sales → Invoices, click '+ New Invoice', fill in the client name, description and amount. ZuZan automatically calculates 15% VAT and assigns an invoice number. You can then send it directly to the client."}
    if "overdue" in msg and "invoice" in msg:
        return {"reply":"Overdue invoices appear in red on the Invoices tab. ZuZan marks an invoice as overdue once the due date passes without payment. Follow up with the client and record payment once received by clicking 'Mark as Paid'."}
    if ("mark" in msg or "record" in msg) and "paid" in msg:
        return {"reply":"To mark an invoice as paid: open the invoice, click 'Mark as Paid'. ZuZan records the payment date and updates the invoice status."}
    if "send" in msg and "invoice" in msg:
        return {"reply":"To send an invoice: open the invoice and click 'Send Invoice'. ZuZan emails it to the client's email address."}
    if ("quote" in msg or "estimate" in msg) and any(x in msg for x in ["create","new","add","make","how","find","where"]):
        return {"reply":"To create a quote: go to Sales → Quotes, click '+ New Quote', fill in the client name, description, amount and validity date. Once accepted, click 'Convert to Invoice'."}
    if "convert" in msg and ("quote" in msg or "estimate" in msg):
        return {"reply":"To convert a quote to an invoice: open the quote, click 'Accept', then click 'Convert to Invoice'. ZuZan creates a new invoice with all details pre-filled."}
    if "expense" in msg and any(x in msg for x in ["add","create","new","record","how","make"]):
        return {"reply":"To add an expense: go to Expenses, click '+ Add Expense', fill in the vendor, amount, category, and date. You can also scan a receipt using the camera icon."}
    if "purchase order" in msg or " po " in msg or msg.startswith("po "):
        return {"reply":"To create a PO: go to Procurement → Purchase Orders, click '+ New PO'. You can send it to the supplier by email, receive goods, and mark it as paid when done."}
    if "uif" in msg:
        return {"reply":"UIF is 1% employee + 1% employer, capped at R17,712/month gross. Both portions are calculated automatically in ZuZan's Payroll tab."}
    if "paye" in msg:
        return {"reply":"PAYE is calculated automatically in the Payroll tab based on SARS tables. EMP201 is due by the 7th of each month."}
    if "sdl" in msg:
        return {"reply":"SDL is 1% of gross payroll, only if annual payroll exceeds R500,000. It is an employer cost calculated automatically in Payroll."}
    if "vat" in msg:
        return {"reply":"South Africa's standard VAT rate is 15%. ZuZan calculates VAT automatically on invoices and expenses. VAT201 reports are in the Reports tab."}
    if "payroll" in msg:
        return {"reply":"Go to the Payroll tab to run monthly payroll. ZuZan calculates PAYE, UIF and SDL automatically and lets you download the EMP201."}
    if "report" in msg or "balance sheet" in msg or "profit" in msg:
        return {"reply":"Reports are under the Reports tab. You'll find P&L, Balance Sheet, Trial Balance, VAT201, and Reconciliation. Filter by date range or financial year."}
    return {"reply":"I'm here to help with ZuZan. You can ask me about invoices, quotes, expenses, purchase orders, payroll, VAT, or any SARS compliance questions."}


# ── RECEIPT SCAN ──────────────────────────────────────────────────────────────
import base64, re as _re
class ReceiptRequest(BM):
    image: str  # base64

@app.post("/expenses/scan-receipt")
async def scan_receipt(data: ReceiptRequest, current_user=Depends(__import__("auth").get_current_user)):
    # Basic OCR using pytesseract if available, else return empty
    try:
        import pytesseract
        from PIL import Image
        import io
        img_bytes = base64.b64decode(data.image)
        img = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img)
        # Extract amount
        amounts = _re.findall(r'R\s*(\d+[\.,]\d{2})', text)
        amount = float(amounts[0].replace(",",".")) if amounts else None
        # Extract date
        dates = _re.findall(r'\d{2}[\/\-]\d{2}[\/\-]\d{4}', text)
        date = dates[0].replace("/","-") if dates else None
        # Extract vendor (first non-empty line)
        lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 3]
        vendor = lines[0] if lines else None
        return {"vendor":vendor,"amount":amount,"date":date,"desc":"Receipt scan","raw":text[:200]}
    except Exception as e:
        return {"vendor":None,"amount":None,"date":None,"desc":None,"error":str(e)}


# ── ADMIN ─────────────────────────────────────────────────────────────────────
def _check_admin(x_admin_secret: str = Header(None)):
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/admin/api/clients", tags=["Admin"])
async def admin_clients(db: Session = Depends(get_db_session), _=Depends(_check_admin)):
    try:
        companies = db.query(_Company).order_by(_Company.created_at.desc()).all()
        result = []
        for c in companies:
            try:
                owner     = db.query(_User).filter(_User.company_id == c.id, _User.role == "owner").first()
                inv_count = db.query(_func.count(_Invoice.id)).filter(_Invoice.company_id == c.id).scalar() or 0
                exp_count = db.query(_func.count(_Expense.id)).filter(_Expense.company_id == c.id).scalar() or 0
                emp_count = db.query(_func.count(_Employee.id)).filter(_Employee.company_id == c.id, _Employee.is_active == True).scalar() or 0
                inv_rev   = db.query(_func.sum(_Invoice.total_amount)).filter(_Invoice.company_id == c.id).scalar() or 0
                last_inv  = db.query(_func.max(_Invoice.created_at)).filter(_Invoice.company_id == c.id).scalar()
                last_exp  = db.query(_func.max(_Expense.created_at)).filter(_Expense.company_id == c.id).scalar()
                last_act  = max(filter(None, [last_inv, last_exp]), default=None)
                result.append({
                    "id":                c.id,
                    "company":           c.name or "—",
                    "owner_name":        f"{owner.first_name} {owner.last_name}" if owner else "—",
                    "owner_email":       owner.email if owner else "—",
                    "email_verified":    getattr(owner, "email_verified", False) or False,
                    "plan":              str(c.plan.value) if c.plan else "starter",
                    "billing_cycle":     str(c.billing_cycle.value) if c.billing_cycle else "monthly",
                    "status":            str(c.subscription_status.value) if c.subscription_status else "trial",
                    "trial_ends":        c.trial_ends.strftime("%Y-%m-%d") if c.trial_ends else None,
                    "signed_up":         c.created_at.strftime("%Y-%m-%d") if c.created_at else None,
                    "invoices":          inv_count,
                    "expenses":          exp_count,
                    "employees":         emp_count,
                    "revenue_collected": round(inv_rev, 2),
                    "last_activity":     last_act.strftime("%Y-%m-%d") if last_act else None,
                })
            except Exception as row_err:
                logger.error(f"Admin: error processing company {c.id}: {row_err}")
                continue
        return result
    except Exception as e:
        logger.error(f"Admin clients error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/api/subscriptions", tags=["Admin"])
async def admin_subscriptions(db: Session = Depends(get_db_session), _=Depends(_check_admin)):
    from database import SubscriptionPayment as _SubPay
    try:
        rows = db.query(_SubPay).order_by(_SubPay.payment_date.desc()).limit(500).all()
        return [{
            "id":                   r.id,
            "company_id":           r.company_id,
            "company_name":         r.company_name,
            "owner_email":          r.owner_email or "—",
            "plan":                 r.plan,
            "billing_cycle":        r.billing_cycle,
            "amount":               r.amount,
            "payfast_payment_id":   r.payfast_payment_id or "—",
            "status":               r.status,
            "payment_date":         r.payment_date.strftime("%Y-%m-%d") if r.payment_date else None,
            "period_start":         r.period_start.strftime("%Y-%m-%d") if r.period_start else None,
            "period_end":           r.period_end.strftime("%Y-%m-%d") if r.period_end else None,
            "notes":                r.notes or "",
        } for r in rows]
    except Exception as e:
        logger.error(f"Admin subscriptions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/api/subscriptions", tags=["Admin"])
async def admin_add_subscription(request: Request, db: Session = Depends(get_db_session), _=Depends(_check_admin)):
    """Manually record a subscription payment (for payments before webhook was live)."""
    from database import SubscriptionPayment as _SubPay
    body = await request.json()
    try:
        sp = _SubPay(
            company_id   = body.get("company_id"),
            company_name = body["company_name"],
            owner_email  = body.get("owner_email"),
            plan         = body["plan"],
            billing_cycle= body.get("billing_cycle", "monthly"),
            amount       = float(body["amount"]),
            payfast_payment_id = body.get("payfast_payment_id"),
            status       = body.get("status", "success"),
            payment_date = datetime.fromisoformat(body["payment_date"]) if body.get("payment_date") else datetime.utcnow(),
            notes        = body.get("notes"),
        )
        db.add(sp); db.commit(); db.refresh(sp)
        return {"id": sp.id, "status": "created"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/admin/api/mrr", tags=["Admin"])
async def admin_mrr(db: Session = Depends(get_db_session), _=Depends(_check_admin)):
    """Return MRR, ARR, total collected, and monthly breakdown for the revenue chart."""
    from database import SubscriptionPayment as _SubPay
    from sqlalchemy import extract
    try:
        now = datetime.utcnow()
        all_rows = db.query(_SubPay).filter(_SubPay.status == "success").all()
        total_collected = sum(r.amount for r in all_rows)

        # MRR: sum of monthly-equivalent amounts for currently active subscriptions
        # (monthly plans count full amount, annual plans divide by 12)
        active_companies = db.query(_Company).filter(
            _Company.subscription_status == "active"
        ).all()
        mrr = 0
        for c in active_companies:
            plan_str  = str(c.plan.value) if c.plan else "starter"
            cycle_str = str(c.billing_cycle.value) if c.billing_cycle else "monthly"
            prices = {"starter": 399, "professional": 899, "business": 1499}
            monthly_price = prices.get(plan_str, 399)
            if cycle_str == "annual":
                monthly_price = round(monthly_price * 10 / 12)  # 2-month discount
            mrr += monthly_price

        arr = mrr * 12

        # Monthly breakdown for the last 12 months
        monthly = []
        for i in range(11, -1, -1):
            m_date = datetime(now.year, now.month, 1)
            from dateutil.relativedelta import relativedelta as _rd
            m_date = m_date - _rd(months=i)
            month_rows = [r for r in all_rows
                          if r.payment_date and r.payment_date.year == m_date.year
                          and r.payment_date.month == m_date.month]
            monthly.append({
                "month": m_date.strftime("%b %Y"),
                "revenue": round(sum(r.amount for r in month_rows), 2),
                "count":   len(month_rows),
            })

        # Plan breakdown
        plan_breakdown = {}
        for r in all_rows:
            plan_breakdown[r.plan] = plan_breakdown.get(r.plan, 0) + r.amount

        return {
            "mrr":             round(mrr, 2),
            "arr":             round(arr, 2),
            "total_collected": round(total_collected, 2),
            "active_subscribers": len(active_companies),
            "monthly_breakdown":  monthly,
            "plan_breakdown":     plan_breakdown,
        }
    except Exception as e:
        logger.error(f"Admin MRR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin", response_class=_HTML, tags=["Admin"])
async def admin_dashboard():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZuZan Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;background:#f0ece6;min-height:100vh}
.topbar{background:#C8401A;color:#fff;padding:16px 28px;display:flex;align-items:center;gap:12px}
.topbar h1{font-size:22px;letter-spacing:1px}
.topbar span{font-size:13px;opacity:.75}
.login{max-width:360px;margin:80px auto;background:#fff;border-radius:12px;padding:32px;box-shadow:0 2px 12px rgba(0,0,0,.1)}
.login h2{color:#C8401A;margin-bottom:20px}
.login input{width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:6px;font-size:14px;margin-bottom:12px}
.login button{width:100%;background:#C8401A;color:#fff;border:none;padding:12px;border-radius:6px;font-size:15px;font-weight:bold;cursor:pointer}
.login button:hover{background:#a33316}
#main{display:none;padding:24px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:24px}
.stat{background:#fff;border-radius:10px;padding:20px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.stat .val{font-size:28px;font-weight:bold;color:#C8401A}
.stat .lbl{font-size:12px;color:#888;margin-top:4px}
.card{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.06);overflow-x:auto}
.card-header{display:flex;align-items:center;margin-bottom:16px}
.card-header h3{color:#1a1a1a;font-size:15px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 12px;background:#f8f5f2;color:#555;font-weight:600;border-bottom:2px solid #e8e2db;white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid #f0ece6;vertical-align:middle;white-space:nowrap}
tr:hover td{background:#fdf9f7}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:bold;text-transform:uppercase}
.badge.trial{background:#fff3cd;color:#856404}
.badge.active{background:#d4edda;color:#155724}
.badge.expired,.badge.cancelled{background:#f8d7da;color:#721c24}
.badge.starter{background:#e8f4fd;color:#0c5460}
.badge.professional{background:#e8f0fe;color:#1a237e}
.badge.business{background:#fce4ec;color:#880e4f}
.verified{color:#28a745}
.unverified{color:#dc3545}
.refresh{background:#C8401A;color:#fff;border:none;padding:8px 18px;border-radius:6px;cursor:pointer;font-size:13px}
.refresh:hover{background:#a33316}
.err{color:#c00;font-size:13px;margin-top:8px;text-align:center}
.tabs{display:flex;gap:0;border-bottom:2px solid #e8e2db;margin-bottom:20px}
.tab{padding:10px 22px;cursor:pointer;font-size:13px;font-weight:600;color:#888;border-bottom:3px solid transparent;margin-bottom:-2px;background:none;border-top:none;border-left:none;border-right:none}
.tab.active{color:#C8401A;border-bottom-color:#C8401A}
.mrr-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:24px}
.mrr-card{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.06);text-align:center}
.mrr-card .val{font-size:24px;font-weight:bold;color:#C8401A}
.mrr-card .lbl{font-size:12px;color:#888;margin-top:4px}
.bar-wrap{display:flex;align-items:flex-end;gap:6px;height:100px;margin:16px 0 4px}
.bar{background:#C8401A;border-radius:4px 4px 0 0;min-width:20px;flex:1;transition:height .3s;position:relative;cursor:default}
.bar:hover::after{content:attr(data-tip);position:absolute;bottom:105%;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:4px 8px;border-radius:4px;font-size:11px;white-space:nowrap}
.bar-labels{display:flex;gap:6px}
.bar-label{flex:1;text-align:center;font-size:10px;color:#aaa;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.add-form{background:#fff8f5;border:1px solid #f0d0c0;border-radius:10px;padding:18px;margin-bottom:20px;display:none}
.add-form h4{color:#C8401A;margin-bottom:12px;font-size:14px}
.add-form .grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:12px}
.add-form input,.add-form select{width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px}
.add-form button{background:#C8401A;color:#fff;border:none;padding:9px 20px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:bold}
.add-form button.sec{background:#fff;color:#C8401A;border:1px solid #C8401A;margin-left:8px}
</style>
</head>
<body>
<div class="topbar">
  <h1>ZuZan</h1><span>Admin Dashboard</span>
</div>

<div class="login" id="loginBox">
  <h2>Admin Access</h2>
  <input type="password" id="secretInput" placeholder="Enter admin secret"
         onkeydown="if(event.key==='Enter')login()">
  <button onclick="login()">Sign In</button>
  <div class="err" id="loginErr"></div>
</div>

<div id="main">
  <div class="tabs">
    <button class="tab active" onclick="showTab('clients')">Clients</button>
    <button class="tab" onclick="showTab('revenue')">Subscription Revenue</button>
  </div>

  <!-- ── CLIENTS TAB ── -->
  <div id="tab-clients">
  <div class="stats" id="statsRow"></div>
  <div class="card">
    <div class="card-header">
      <h3>Registered Clients</h3>
      <div style="margin-left:auto;display:flex;align-items:center;gap:10px">
        <span id="lastUpdated" style="font-size:11px;color:#aaa"></span>
        <button class="refresh" id="refreshBtn" onclick="load()">↻ Refresh</button>
      </div>
    </div>
    <div class="err" id="mainErr" style="margin-bottom:10px"></div>
    <table>
      <thead><tr>
        <th>#</th><th>Company</th><th>Owner</th><th>Email</th>
        <th>✉ Verified</th><th>Plan</th><th>Status</th>
        <th>Signed Up</th><th>Trial Ends</th>
        <th>Invoices</th><th>Expenses</th><th>Employees</th>
        <th>Revenue (ZAR)</th><th>Last Activity</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="err" id="mainErr" style="margin-top:10px"></div>
  </div>
  </div><!-- end tab-clients -->

  <!-- ── REVENUE TAB ── -->
  <div id="tab-revenue" style="display:none">
    <div class="mrr-grid" id="mrrStats"></div>
    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <h3>Monthly Subscription Revenue (Last 12 Months)</h3>
        <button class="refresh" style="margin-left:auto" onclick="loadRevenue()">↻ Refresh</button>
      </div>
      <div class="bar-wrap" id="revenueChart"></div>
      <div class="bar-labels" id="revenueLabels"></div>
    </div>
    <div class="card">
      <div class="card-header">
        <h3>Payment History</h3>
        <button onclick="toggleAddForm()" style="margin-left:auto;background:#C8401A;color:#fff;border:none;padding:7px 16px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:bold">+ Add Manual Entry</button>
      </div>
      <div class="add-form" id="addForm">
        <h4>Record Manual Payment</h4>
        <div class="grid">
          <input id="f_company" placeholder="Company name *"/>
          <input id="f_email" placeholder="Owner email"/>
          <input id="f_amount" type="number" placeholder="Amount (ZAR) *"/>
          <select id="f_plan"><option value="starter">Starter</option><option value="professional">Professional</option><option value="business">Business</option></select>
          <select id="f_cycle"><option value="monthly">Monthly</option><option value="annual">Annual</option></select>
          <input id="f_date" type="date"/>
          <input id="f_pfid" placeholder="PayFast payment ID (optional)"/>
          <input id="f_notes" placeholder="Notes (optional)"/>
        </div>
        <button onclick="submitManual()">Save Payment</button>
        <button class="sec" onclick="toggleAddForm()">Cancel</button>
        <span id="addMsg" style="font-size:12px;margin-left:12px"></span>
      </div>
      <table>
        <thead><tr>
          <th>#</th><th>Date</th><th>Company</th><th>Email</th>
          <th>Plan</th><th>Cycle</th><th>Amount</th>
          <th>PayFast Ref</th><th>Status</th><th>Period</th><th>Notes</th>
        </tr></thead>
        <tbody id="revTbody"></tbody>
      </table>
    </div>
  </div><!-- end tab-revenue -->
</div><!-- end main -->

<script>
let secret = '';
let currentTab = 'clients';

function showTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-clients').style.display = tab === 'clients' ? '' : 'none';
  document.getElementById('tab-revenue').style.display = tab === 'revenue' ? '' : 'none';
  if (tab === 'revenue') loadRevenue();
}

function login() {
  secret = document.getElementById('secretInput').value.trim();
  if (!secret) return;
  load();
}

function setError(msg) {
  const loggedIn = document.getElementById('main').style.display === 'block';
  if (loggedIn) {
    const el = document.getElementById('mainErr');
    if (el) el.textContent = msg;
  } else {
    document.getElementById('loginErr').textContent = msg;
  }
}

async function load() {
  const btn = document.getElementById('refreshBtn');
  if (btn) { btn.disabled = true; btn.textContent = '↻ Loading…'; }
  const errEl = document.getElementById('mainErr');
  if (errEl) errEl.textContent = '';
  try {
    const res = await fetch('/admin/api/clients', { headers: {'X-Admin-Secret': secret} });
    if (res.status === 403) { setError('Incorrect secret.'); return; }
    if (!res.ok) { setError('Server error: ' + (await res.text()).slice(0,120)); return; }
    const data = await res.json();
    document.getElementById('loginBox').style.display = 'none';
    document.getElementById('main').style.display = 'block';
    renderStats(data);
    renderTable(data);
    const now = new Date();
    document.getElementById('lastUpdated').textContent =
      'Updated ' + now.toLocaleTimeString('en-ZA', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  } catch(e) { setError('Error: ' + e.message); }
  finally { if (btn) { btn.disabled = false; btn.textContent = '↻ Refresh'; } }
}

function renderStats(data) {
  const total = data.length;
  const trial = data.filter(d => d.status==='trial').length;
  const active = data.filter(d => d.status==='active').length;
  const revenue = data.reduce((s,d) => s+(d.revenue_collected||0), 0);
  document.getElementById('statsRow').innerHTML = `
    <div class="stat"><div class="val">${total}</div><div class="lbl">Total Clients</div></div>
    <div class="stat"><div class="val">${active}</div><div class="lbl">Active (Paid)</div></div>
    <div class="stat"><div class="val">${trial}</div><div class="lbl">On Trial</div></div>
    <div class="stat"><div class="val">R${revenue.toLocaleString('en-ZA',{minimumFractionDigits:2})}</div><div class="lbl">Client Revenue (Invoiced)</div></div>`;
}

function renderTable(data) {
  const tbody = document.getElementById('tbody');
  if (!data.length) { tbody.innerHTML='<tr><td colspan="14" style="text-align:center;color:#888;padding:40px">No clients yet</td></tr>'; return; }
  tbody.innerHTML = data.map((d,i) => `<tr>
    <td style="color:#888">${i+1}</td>
    <td><strong>${d.company}</strong></td>
    <td>${d.owner_name}</td>
    <td><a href="mailto:${d.owner_email}" style="color:#C8401A">${d.owner_email}</a></td>
    <td style="text-align:center">${d.email_verified
      ? '<span class="verified">✓ Yes</span>'
      : '<span class="unverified">✗ No</span>'}</td>
    <td><span class="badge ${d.plan}">${d.plan}</span></td>
    <td><span class="badge ${d.status}">${d.status}</span></td>
    <td>${d.signed_up||'—'}</td><td>${d.trial_ends||'—'}</td>
    <td style="text-align:center">${d.invoices}</td>
    <td style="text-align:center">${d.expenses}</td>
    <td style="text-align:center">${d.employees}</td>
    <td>R${(d.revenue_collected||0).toLocaleString('en-ZA',{minimumFractionDigits:2})}</td>
    <td style="color:#888">${d.last_activity||'No activity yet'}</td>
  </tr>`).join('');
}

async function loadRevenue() {
  try {
    const [mrrRes, subRes] = await Promise.all([
      fetch('/admin/api/mrr',           { headers: {'X-Admin-Secret': secret} }),
      fetch('/admin/api/subscriptions', { headers: {'X-Admin-Secret': secret} }),
    ]);
    const mrr  = await mrrRes.json();
    const subs = await subRes.json();
    renderMrrStats(mrr);
    renderRevenueChart(mrr.monthly_breakdown||[]);
    renderSubTable(subs);
  } catch(e) { alert('Failed to load revenue data: ' + e.message); }
}

function renderMrrStats(mrr) {
  const fmt = v => 'R' + (v||0).toLocaleString('en-ZA',{minimumFractionDigits:2});
  document.getElementById('mrrStats').innerHTML = `
    <div class="mrr-card"><div class="val">${fmt(mrr.mrr)}</div><div class="lbl">MRR</div></div>
    <div class="mrr-card"><div class="val">${fmt(mrr.arr)}</div><div class="lbl">ARR</div></div>
    <div class="mrr-card"><div class="val">${fmt(mrr.total_collected)}</div><div class="lbl">Total Collected</div></div>
    <div class="mrr-card"><div class="val">${mrr.active_subscribers||0}</div><div class="lbl">Active Subscribers</div></div>`;
}

function renderRevenueChart(monthly) {
  const maxVal = Math.max(...monthly.map(m => m.revenue), 1);
  document.getElementById('revenueChart').innerHTML = monthly.map(m => {
    const h = Math.round((m.revenue / maxVal) * 90) + 10;
    const tip = m.month + ': R' + (m.revenue||0).toLocaleString('en-ZA',{minimumFractionDigits:2}) + ' (' + m.count + ' payments)';
    return '<div class="bar" style="height:' + h + 'px" data-tip="' + tip + '"></div>';
  }).join('');
  document.getElementById('revenueLabels').innerHTML = monthly.map(m =>
    '<div class="bar-label">' + m.month.split(' ')[0] + '</div>'
  ).join('');
}

function renderSubTable(subs) {
  const tbody = document.getElementById('revTbody');
  if (!subs.length) { tbody.innerHTML='<tr><td colspan="11" style="text-align:center;color:#888;padding:40px">No subscription payments recorded yet.</td></tr>'; return; }
  const fmt = v => 'R' + (v||0).toLocaleString('en-ZA',{minimumFractionDigits:2});
  tbody.innerHTML = subs.map((s,i) => `<tr>
    <td style="color:#888">${i+1}</td>
    <td>${s.payment_date||'—'}</td>
    <td><strong>${s.company_name}</strong></td>
    <td><a href="mailto:${s.owner_email}" style="color:#C8401A">${s.owner_email}</a></td>
    <td><span class="badge ${s.plan}">${s.plan}</span></td>
    <td>${s.billing_cycle}</td>
    <td style="font-weight:bold;color:#C8401A">${fmt(s.amount)}</td>
    <td style="color:#888;font-size:11px">${s.payfast_payment_id}</td>
    <td><span class="badge ${s.status==='success'?'active':s.status==='refunded'?'cancelled':'expired'}">${s.status}</span></td>
    <td style="font-size:11px;color:#888">${s.period_start||''}${s.period_end?' → '+s.period_end:''}</td>
    <td style="color:#888">${s.notes||''}</td>
  </tr>`).join('');
}

function toggleAddForm() {
  const f = document.getElementById('addForm');
  f.style.display = f.style.display === 'none' ? 'block' : 'none';
}

async function submitManual() {
  const company_name = document.getElementById('f_company').value.trim();
  const amount = document.getElementById('f_amount').value;
  const plan = document.getElementById('f_plan').value;
  if (!company_name || !amount) { document.getElementById('addMsg').textContent = 'Company name and amount are required.'; return; }
  const body = {
    company_name,
    owner_email:       document.getElementById('f_email').value.trim()||null,
    amount:            parseFloat(amount),
    plan,
    billing_cycle:     document.getElementById('f_cycle').value,
    payment_date:      document.getElementById('f_date').value||null,
    payfast_payment_id:document.getElementById('f_pfid').value.trim()||null,
    notes:             document.getElementById('f_notes').value.trim()||null,
  };
  try {
    const res = await fetch('/admin/api/subscriptions', {
      method:'POST', headers:{'X-Admin-Secret':secret,'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(await res.text());
    document.getElementById('addMsg').textContent = '✓ Saved';
    setTimeout(() => { toggleAddForm(); loadRevenue(); }, 800);
  } catch(e) { document.getEl