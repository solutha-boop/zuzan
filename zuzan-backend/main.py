from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zuzan.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ZuZan backend...")
    from database import init_db
    init_db()
    logger.info("Database ready")
    yield


app = FastAPI(title="ZuZan API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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

app.include_router(auth_router,      prefix="/auth",      tags=["Auth"])
app.include_router(companies_router, prefix="/companies", tags=["Companies"])
app.include_router(invoices_router,  prefix="/invoices",  tags=["Invoices"])
app.include_router(expenses_router,  prefix="/expenses",  tags=["Expenses"])
app.include_router(employees_router, prefix="/employees", tags=["Employees"])
app.include_router(payroll_router,   prefix="/payroll",   tags=["Payroll"])
app.include_router(payments_router,  prefix="/payments",  tags=["Payments"])
app.include_router(reports_router,   prefix="/reports",   tags=["Reports"])
app.include_router(bank_router,      prefix="/bank",      tags=["Bank Import"])
app.include_router(api_keys_router,  prefix="/api-keys",  tags=["API Keys"])
app.include_router(inventory_router, prefix="/inventory", tags=["Inventory"])


@app.get("/")
async def root():
    return {"status": "ZuZan API running", "version": "1.0.0"}


# ── PUBLIC API (API key authenticated) ───────────────────────────────────────
from fastapi import Header, Depends, HTTPException
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
async def ai_chat(data: ChatRequest):
    import re, os
    msg = data.message.lower()
    # Rule-based SA bookkeeping responses
    if "paye" in msg and any(x in msg for x in ["35000","35 000"]):
        return {"reply":"For R35,000/month gross (R420,000 annual): PAYE ≈ R4,673/month after the R17,235 primary rebate (2025/2026 tables). Check the Payroll tab for exact figures."}
    if "emp201" in msg or "emp 201" in msg:
        return {"reply":"EMP201 is due by the 7th of each month following the payroll period. It covers PAYE, UIF and SDL. You can download the EMP201 file from the Payroll tab after running payroll."}
    if "vat" in msg and "rate" in msg:
        return {"reply":"The standard VAT rate in South Africa is 15%. Basic foods, exports and certain supplies are zero-rated. VAT201 is submitted monthly or bi-monthly. Late submission incurs a 10% penalty plus interest."}
    if "fuel" in msg or "petrol" in msg or "diesel" in msg:
        return {"reply":"Fuel expenses should be categorised to account 6510 - Fuel and Oil under Expenses. Only the business-use portion is deductible. Keep a logbook if the vehicle is used for both business and private travel."}
    if "bad debt" in msg:
        return {"reply":"Record a bad debt write-off by creating an expense to account 7300 - Bad Debts Written Off. This reduces debtors and is tax-deductible in the year the debt becomes irrecoverable."}
    if "uif" in msg:
        return {"reply":"UIF is 1% employee + 1% employer contribution, capped at R17,712/month gross. Both portions are calculated automatically in ZuZan's Payroll tab. Total max UIF per employee is R354.24/month."}
    if "sdl" in msg:
        return {"reply":"SDL (Skills Development Levy) is 1% of gross payroll, payable if your annual payroll exceeds R500,000. It is an employer cost — not deducted from the employee. Due by the 7th of each month with PAYE."}
    if "invoice" in msg and "vat" in msg:
        return {"reply":"A valid SA tax invoice must include: your VAT registration number, the buyer's VAT number (if VAT-registered), invoice number, date, description of goods/services, amount excl. VAT, VAT amount, and total incl. VAT."}
    if "depreciation" in msg:
        return {"reply":"For tax purposes, SARS allows wear-and-tear allowances: computers 3 years, vehicles 5 years, machinery varies. Record depreciation monthly to account 7100 - Depreciation and the corresponding accumulated depreciation account."}
    if "provisional tax" in msg or "irp6" in msg:
        return {"reply":"Provisional tax (IRP6) is paid twice a year: first payment by 31 August, second by 28 February. Based on estimated taxable income for the year. Check the Reports → Provisional Tax tab for your estimated figures."}
    if "dividend" in msg:
        return {"reply":"Dividends paid to shareholders should be recorded to account 3300 - Dividends Paid under Equity. Dividends tax is 20% and must be withheld before payment. The company declares and pays this to SARS."}
    return {"reply":f"Good question about '{data.message}'. For specific SARS guidance, refer to sars.gov.za or consult your accountant. ZuZan handles the calculations automatically — check the relevant tab for details."}


# ── RECEIPT SCAN ──────────────────────────────────────────────────────────────
import base64, re as _re
class ReceiptRequest(BM):
    image: str  # base64

@app.post("/expenses/scan-receipt")
async def scan_receipt(data: ReceiptRequest):
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
