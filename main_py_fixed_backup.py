from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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
    yield


app = FastAPI(title="ZuZan API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin",
                   "X-Requested-With", "X-API-Key", "X-Admin-Secret"],
    max_age=86400,
)

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
    from sqlalchemy import func
    total_revenue  = db.query(func.sum(Invoice.total_amount)).filter(Invoice.company_id==company.id, Invoice.status=="paid").scalar() or 0
    total_expenses = db.query(func.sum(Expense.amount)).filter(Expense.company_id==company.id).scalar() or 0
    outstanding    = db.query(func.sum(Invoice.total_amount)).filter(Invoice.company_id==company.id, Invoice.status!="paid").scalar() or 0
    return {"company":company.name,"total_revenue":round(total_revenue,2),"total_expenses":round(total_expenses,2),"outstanding":round(outstanding,2),"net_profit":round(total_revenue-total_expenses,2)}


# ── AI CHAT ───────────────────────────────────────────────────────────────────
from pydantic import BaseModel as BM
class ChatRequest(BM):
    message: str
    context: str = ""

@app.post("/ai/chat")
@limiter.limit("30/minute")
async def ai_chat(request: Request, data: ChatRequest, current_user=Depends(__import__("auth").get_current_user)):
    msg = data.message.lower()
    ctx = data.context.lower()

    # ── INVOICING ─────────────────────────────────────────────────────────────
    if any(x in msg for x in ["create invoice","new invoice","add invoice","how do i invoice"]):
        return {"reply":"To create an invoice: go to Sales → Invoices, click '+ New Invoice', fill in the client name, description and amount. ZuZan automatically calculates 15% VAT and assigns an invoice number. You can then send it directly to the client."}
    if "overdue" in msg and "invoice" in msg:
        return {"reply":"Overdue invoices appear in red on the Invoices tab. ZuZan marks an invoice as overdue once the due date passes without payment. Follow up with the client and record payment once received by clicking 'Mark as Paid'."}
    if ("mark" in msg or "record" in msg) and "paid" in msg:
        return {"reply":"To mark an invoice as paid: open the invoice, click 'Mark as Paid'. ZuZan records the payment date and updates the invoice status. This also updates your revenue figures in the dashboard and reports."}
    if "send" in msg and "invoice" in msg:
        return {"reply":"To send an invoice: open the invoice and click 'Send Invoice'. ZuZan emails a PDF to the client's email address. Make sure the client email is filled in when creating the invoice."}
    if "payment term" in msg or "payment terms" in msg:
        return {"reply":"Payment terms define how many days a client has to pay. Common SA terms are 30 days (net 30) or 7 days for smaller jobs. Set payment terms when creating the invoice — the due date is calculated automatically."}
    if ("invoice" in msg and "vat" in msg) or ("tax invoice" in msg):
        return {"reply":"A valid SA tax invoice must include: your VAT registration number, the buyer's VAT number (if VAT-registered), a unique invoice number, date, description of goods/services, amount excl. VAT, VAT amount at 15%, and total incl. VAT. ZuZan generates compliant invoices automatically."}
    if "invoice number" in msg:
        return {"reply":"ZuZan automatically assigns sequential invoice numbers (INV-0001, INV-0002, etc.) when you create an invoice. These cannot be changed as SARS requires sequential numbering for audit purposes."}
    if "proforma" in msg:
        return {"reply":"A proforma invoice is a preliminary bill sent before goods/services are delivered. In ZuZan, use the Quotes tab to create a proforma — it has the same format but is clearly marked as a quote/estimate, not a tax invoice."}

    # ── QUOTES ────────────────────────────────────────────────────────────────
    if any(x in msg for x in ["create quote","new quote","add quote","how do i quote"]):
        return {"reply":"To create a quote: go to Sales → Quotes, click '+ New Quote', fill in the client name, description, amount and validity date. Once the client accepts it, click 'Convert to Invoice' to automatically create an invoice from the quote."}
    if "convert" in msg and ("quote" in msg or "estimate" in msg):
        return {"reply":"To convert a quote to an invoice: open the quote, click 'Accept' to mark it as accepted, then click 'Convert to Invoice'. ZuZan creates a new invoice with all the quote details pre-filled and takes you straight to the Invoices tab."}
    if ("quote" in msg or "estimate" in msg) and "valid" in msg:
        return {"reply":"A quote should include a validity date — the date after which the quoted price is no longer guaranteed. Common practice in SA is 30 days. Set this when creating the quote using the 'Valid Until' field."}
    if ("quote" in msg and "invoice" in msg) or ("difference" in msg and "quote" in msg):
        return {"reply":"A quote is a non-binding price offer to a client. An invoice is a demand for payment after goods/services have been delivered. In ZuZan, quotes can be converted to invoices once accepted, keeping all the details intact."}
    if "quote" in msg and ("follow" in msg or "status" in msg):
        return {"reply":"Track quote status in the Quotes tab: Draft (not yet sent), Sent (awaiting client response), Accepted (client agreed), or Declined. Update the status as you hear back from clients to keep your pipeline accurate."}

    # ── EXPENSES ──────────────────────────────────────────────────────────────
    if any(x in msg for x in ["add expense","create expense","new expense","record expense","how do i add"]):
        return {"reply":"To add an expense: go to Expenses, click '+ Add Expense', fill in the vendor, amount, category, and date. You can also scan a receipt using the camera icon to auto-fill the details. ZuZan calculates input VAT automatically if VAT applies."}
    if "categor" in msg and "expense" in msg:
        return {"reply":"Common SA expense categories in ZuZan:\n• 6000 - Cost of Sales\n• 6100 - Salaries & Wages\n• 6200 - Rent\n• 6300 - Telephone & Internet\n• 6400 - Office Supplies\n• 6500 - Marketing\n• 6510 - Fuel & Oil\n• 6600 - Insurance\n• 6700 - Professional Fees\n• 7100 - Depreciation\nChoose the one that best matches the nature of the expense."}
    if "scan" in msg and ("receipt" in msg or "expense" in msg):
        return {"reply":"To scan a receipt: click '+ Add Expense', then tap the camera/scan icon. ZuZan will extract the vendor name, amount and date from the receipt image automatically. Review the extracted details before saving."}
    if "input vat" in msg or ("vat" in msg and "expense" in msg and "claim" in msg):
        return {"reply":"Input VAT is the 15% VAT you paid on business expenses — you can claim this back if you are VAT-registered. ZuZan tracks input VAT on expenses automatically. Your VAT201 net payment = output VAT (on sales) minus input VAT (on expenses)."}
    if "rent" in msg and "expense" in msg:
        return {"reply":"Record rent as an expense to account 6200 - Rent. If your landlord is VAT-registered, the invoice will include 15% VAT which you can claim as input VAT. Make sure you have a valid tax invoice from the landlord."}
    if "entertain" in msg or "client lunch" in msg or "client dinner" in msg:
        return {"reply":"Entertainment expenses (client lunches, dinners) are partially deductible for tax purposes. Only 50% of the cost is deductible under SARS rules. Categorise to 6500 - Marketing or create a dedicated Entertainment category. Input VAT on entertainment is generally not claimable."}
    if "salary" in msg and "expense" in msg:
        return {"reply":"Salaries are automatically recorded as expenses when you run payroll in the Payroll tab. They are categorised to 6100 - Salaries & Wages. Do not manually add salary expenses — use the Payroll module to avoid double-counting."}

    # ── PAYROLL ───────────────────────────────────────────────────────────────
    if "paye" in msg and any(x in msg for x in ["35000","35 000"]):
        return {"reply":"For R35,000/month gross (R420,000 annual): PAYE ≈ R4,673/month after the R17,235 primary rebate (2025/2026 tables). Check the Payroll tab for exact figures."}
    if "emp201" in msg or "emp 201" in msg:
        return {"reply":"EMP201 is due by the 7th of each month following the payroll period. It covers PAYE, UIF and SDL. You can download the EMP201 file from the Payroll tab after running payroll."}
    if "uif" in msg:
        return {"reply":"UIF is 1% employee + 1% employer contribution, capped at R17,712/month gross. Both portions are calculated automatically in ZuZan's Payroll tab. Total max UIF per employee is R354.24/month."}
    if "sdl" in msg:
        return {"reply":"SDL (Skills Development Levy) is 1% of gross payroll, payable if your annual payroll exceeds R500,000. It is an employer cost — not deducted from the employee. Due by the 7th of each month with PAYE."}

    # ── GENERAL ACCOUNTING ────────────────────────────────────────────────────
    if "vat" in msg and "rate" in msg:
        return {"reply":"The standard VAT rate in South Africa is 15%. Basic foods, exports and certain supplies are zero-rated. VAT201 is submitted monthly or bi-monthly. Late submission incurs a 10% penalty plus interest."}
    if "fuel" in msg or "petrol" in msg or "diesel" in msg:
        return {"reply":"Fuel expenses should be categorised to account 6510 - Fuel and Oil under Expenses. Only the business-use portion is deductible. Keep a logbook if the vehicle is used for both business and private travel."}
    if "bad debt" in msg:
        return {"reply":"Record a bad debt write-off by creating an expense to account 7300 - Bad Debts Written Off. This reduces debtors and is tax-deductible in the year the debt becomes irrecoverable."}
    if "depreciation" in msg:
        return {"reply":"SARS wear-and-tear allowances: computers 3 years, vehicles 5 years, machinery varies. Record depreciation monthly to account 7100 - Depreciation. ZuZan tracks this in the Expenses section."}
    if "provisional tax" in msg or "irp6" in msg:
        return {"reply":"Provisional tax (IRP6) is paid twice a year: first payment by 31 August, second by 28 February. Based on estimated taxable income. Check Reports for your estimated figures."}
    if "dividend" in msg:
        return {"reply":"Dividends paid to shareholders go to account 3300 - Dividends Paid under Equity. Dividends tax is 20% — withheld before payment and paid to SARS by the company."}

    # ── CONTEXTUAL FALLBACK ───────────────────────────────────────────────────
    context_hints = {
        "invoicing": "You're on the Invoices tab. I can help you create invoices, mark payments, handle overdue accounts, or explain VAT requirements.",
        "quotes":    "You're on the Quotes tab. I can help you create quotes, convert them to invoices, or explain quoting best practices.",
        "expenses":  "You're on the Expenses tab. I can help you categorise expenses, scan receipts, or explain input VAT claims.",
        "payroll":   "You're on the Payroll tab. I can help with PAYE calculations, UIF, SDL, or EMP201 submissions.",
    }
    for key, hint in context_hints.items():
        if key in ctx:
            return {"reply":f"I'm not sure about that specific question. {hint} What would you like to know?"}
    return {"reply":f"Good question. For specific SARS guidance, refer to sars.gov.za or consult your accountant. ZuZan handles the calculations automatically — check the relevant tab for details."}


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
.refresh{background:#C8401A;color:#fff;border:none;padding:8px 18px;border-radius:6px;cursor:pointer;font-size:13px;margin-left:auto}
.refresh:hover{background:#a33316}
.err{color:#c00;font-size:13px;margin-top:8px;text-align:center}
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
  <div class="stats" id="statsRow"></div>
  <div class="card">
    <div class="card-header">
      <h3>Registered Clients</h3>
      <button class="refresh" onclick="load()">↻ Refresh</button>
    </div>
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
  </div>
</div>

<script>
let secret = '';
function login() {
  secret = document.getElementById('secretInput').value.trim();
  if (!secret) return;
  load();
}
async function load() {
  try {
    const res = await fetch('/admin/api/clients', { headers: {'X-Admin-Secret': secret} });
    if (res.status === 403) { document.getElementById('loginErr').textContent = 'Incorrect secret.'; return; }
    if (!res.ok) {
      const txt = await res.text();
      document.getElementById('loginErr').textContent = 'Server error: ' + txt.slice(0, 120);
      return;
    }
    const data = await res.json();
    document.getElementById('loginBox').style.display = 'none';
    document.getElementById('main').style.display = 'block';
    renderStats(data);
    renderTable(data);
  } catch(e) {
    document.getElementById('loginErr').textContent = 'Error: ' + e.message;
  }
}
function renderStats(data) {
  const total   = data.length;
  const trial   = data.filter(d => d.status==='trial').length;
  const active  = data.filter(d => d.status==='active').length;
  const revenue = data.reduce((s,d) => s+(d.revenue_collected||0), 0);
  document.getElementById('statsRow').innerHTML = `
    <div class="stat"><div class="val">${total}</div><div class="lbl">Total Clients</div></div>
    <div class="stat"><div class="val">${active}</div><div class="lbl">Active (Paid)</div></div>
    <div class="stat"><div class="val">${trial}</div><div class="lbl">On Trial</div></div>
    <div class="stat"><div class="val">R${revenue.toLocaleString('en-ZA',{minimumFractionDigits:2})}</div><div class="lbl">Revenue Collected</div></div>`;
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
      ? '<span class="verified" title="Verified">✓ Yes</span>'
      : '<span class="unverified" title="Not verified">✗ No</span>'}</td>
    <td><span class="badge ${d.plan}">${d.plan}</span></td>
    <td><span class="badge ${d.status}">${d.status}</span></td>
    <td>${d.signed_up