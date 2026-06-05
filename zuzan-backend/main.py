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

@app.get("/health")
async def health(): return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://zuzan-app.onrender.com",
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

from auth import router as auth_router
from companies import (
    router as companies_router,
    invoices_router,
    expenses_router,
    employees_router,
    bank_router,
)
from payroll import payroll_router, reports_router, payments_router

app.include_router(auth_router,      prefix="/auth",      tags=["Auth"])
app.include_router(companies_router, prefix="/companies", tags=["Companies"])
app.include_router(invoices_router,  prefix="/invoices",  tags=["Invoices"])
app.include_router(expenses_router,  prefix="/expenses",  tags=["Expenses"])
app.include_router(employees_router, prefix="/employees", tags=["Employees"])
app.include_router(payroll_router,   prefix="/payroll",   tags=["Payroll"])
app.include_router(payments_router,  prefix="/payments",  tags=["Payments"])
app.include_router(reports_router,   prefix="/reports",   tags=["Reports"])
app.include_router(bank_router,      prefix="/bank",      tags=["Bank Import"])


@app.get("/")
async def root():
    return {"status": "ZuZan API running", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
