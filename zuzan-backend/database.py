from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum

import os
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./zuzan.db")

# Render's PostgreSQL URLs use postgres:// but SQLAlchemy requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite needs check_same_thread; PostgreSQL doesn't
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AccountType(str, enum.Enum):
    asset     = "asset"
    liability = "liability"
    equity    = "equity"
    revenue   = "revenue"
    expense   = "expense"

class PlanType(str, enum.Enum):
    starter="starter" 
    professional="professional"
    business="business"

class BillingCycle(str, enum.Enum):
    monthly="monthly" 
    annual="annual"

class InvoiceStatus(str, enum.Enum):
    draft="draft"
    sent="sent"       # aka "pending" in AR/audit terminology — invoice issued and awaiting payment
    paid="paid"
    overdue="overdue"

class SubscriptionStatus(str, enum.Enum):
    trial="trial" 
    active="active"
    cancelled="cancelled"
    expired="expired"

class Company(Base):
    __tablename__ = "companies"
    id=Column(Integer,primary_key=True,index=True)
    name=Column(String,nullable=False)
    reg_number=Column(String); vat_number=Column(String); industry=Column(String)
    address=Column(Text); phone=Column(String); email=Column(String)
    bank_name=Column(String); bank_account=Column(String); bank_branch=Column(String)
    logo_url=Column(Text,nullable=True)
    payroll_pin_hash=Column(String,nullable=True)
    plan=Column(Enum(PlanType),default=PlanType.starter)
    billing_cycle=Column(Enum(BillingCycle),default=BillingCycle.monthly)
    subscription_status=Column(Enum(SubscriptionStatus),default=SubscriptionStatus.trial)
    trial_ends=Column(DateTime); payroll_enabled=Column(Boolean,default=False)
    payroll_employees=Column(Integer,default=0)
    afs_enabled=Column(Boolean,default=False)
    payfast_merchant_id=Column(String,nullable=True)   # Per-company PayFast credentials (encrypted)
    payfast_merchant_key=Column(String,nullable=True)
    payfast_passphrase=Column(String,nullable=True)
    cipc_registration_date=Column(DateTime,nullable=True)   # Company anniversary for CIPC AR reminder
    # ── SARS e@syFile / IRP5 fields (BRS v25.3.0) ────────────────────────────
    paye_ref=Column(String,nullable=True)             # PAYE Reference Number (10 digits, starts 7)
    sdl_ref=Column(String,nullable=True)              # SDL Reference Number (starts L)
    uif_ref=Column(String,nullable=True)              # UIF Reference Number (starts U)
    sic7_code=Column(String,nullable=True)            # Standard Industrial Classification code
    contact_name=Column(String,nullable=True)         # Contact person name for SARS submissions
    # Billing lifecycle tracking
    trial_warning_sent_at=Column(DateTime,nullable=True)    # When 3-day warning email was sent
    trial_expiry_email_sent_at=Column(DateTime,nullable=True) # When "trial ended" email was sent
    overdue_reminders_enabled=Column(Boolean,default=True)  # Whether auto overdue reminders fire
    created_at=Column(DateTime,default=datetime.utcnow)
    users=relationship("User",back_populates="company")
    invoices=relationship("Invoice",back_populates="company")
    expenses=relationship("Expense",back_populates="company")
    employees=relationship("Employee",back_populates="company")
    payments=relationship("Payment",back_populates="company")
    api_keys=relationship("APIKey",back_populates="company")
    inventory=relationship("InventoryItem",back_populates="company")
    customers=relationship("Customer",back_populates="company")
    suppliers=relationship("Supplier",back_populates="company")
    purchase_orders=relationship("PurchaseOrder",back_populates="company")
    quotes=relationship("Quote",back_populates="company")
    budgets=relationship("Budget",back_populates="company")
    accounts=relationship("Account",back_populates="company")
    journal_entries=relationship("JournalEntry",back_populates="company")
    leave_requests=relationship("LeaveRequest",back_populates="company")
    leave_balances=relationship("LeaveBalance",back_populates="company")
    fixed_assets=relationship("FixedAsset",back_populates="company")
    category_rules=relationship("CategoryRule",back_populates="company")
    documents=relationship("CompanyDocument",back_populates="company")
    stitch_connection=relationship("StitchConnection",foreign_keys="StitchConnection.company_id",uselist=False)
    stitch_bank_accounts=relationship("StitchBankAccount",foreign_keys="StitchBankAccount.company_id")
    stitch_transactions=relationship("StitchTransaction",foreign_keys="StitchTransaction.company_id")
    recurring_invoices=relationship("RecurringInvoice",back_populates="company")
    credit_notes=relationship("CreditNote",back_populates="company")

class User(Base):
    __tablename__ = "users"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    first_name=Column(String,nullable=False); last_name=Column(String,nullable=False)
    email=Column(String,unique=True,nullable=False,index=True)
    phone=Column(String); hashed_password=Column(String,nullable=False)
    role=Column(String,default="owner"); is_active=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    reset_token=Column(String,nullable=True); reset_token_expires=Column(DateTime,nullable=True)
    email_verified=Column(Boolean,default=False); email_verify_token=Column(String,nullable=True)
    company=relationship("Company",back_populates="users")

class Invoice(Base):
    __tablename__ = "invoices"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    invoice_number=Column(String,nullable=False); client_name=Column(String,nullable=False)
    client_email=Column(String); description=Column(Text)
    amount=Column(Float,nullable=False); vat_amount=Column(Float,default=0)
    total_amount=Column(Float,nullable=False)
    currency=Column(String,default="ZAR")
    exchange_rate=Column(Float,default=1)
    status=Column(Enum(InvoiceStatus),default=InvoiceStatus.draft)
    issue_date=Column(DateTime,default=datetime.utcnow); due_date=Column(DateTime)
    paid_date=Column(DateTime,nullable=True); paid_amount_zar=Column(Float,nullable=True); notes=Column(Text)
    portal_token=Column(String,nullable=True,unique=True,index=True)   # UUID for public payment portal
    portal_token_created_at=Column(DateTime,nullable=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="invoices")

class Expense(Base):
    __tablename__ = "expenses"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    vendor=Column(String,nullable=False); description=Column(Text)
    amount=Column(Float,nullable=False); vat_amount=Column(Float,default=0); category=Column(String)
    expense_date=Column(DateTime,default=datetime.utcnow)
    # When True, the expense was purchased on credit (not yet cash-paid).
    # journal.post_expense will credit Accounts Payable (2000) instead of Bank (1000).
    is_on_credit=Column(Boolean,default=False)
    # Set by POST /expenses/{id}/pay once the supplier invoice is settled.
    # NULL means unpaid (still an open creditor). Non-NULL means AP cleared.
    paid_at=Column(DateTime,nullable=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="expenses")

class Employee(Base):
    __tablename__ = "employees"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    employee_number=Column(String); first_name=Column(String,nullable=False)
    last_name=Column(String,nullable=False); id_number=Column(String)
    tax_number=Column(String); date_of_birth=Column(DateTime)
    appointment_date=Column(DateTime); address=Column(String)
    position=Column(String); department=Column(String)
    grade=Column(String,nullable=True)                # e.g. "A", "B", "Senior", "Grade 7"
    employment_type=Column(String,default="salaried") # "salaried" | "hourly"
    hourly_rate=Column(Float,nullable=True)           # explicit hourly rate for hourly employees; None = derive from gross_salary / BCEA hours
    gross_salary=Column(Float,nullable=False); start_date=Column(DateTime)
    # Pension / Provident fund (s11F — cap R430,000/year from 1 March 2026)
    # Use pct OR fixed_amount (or both — they add up). s11F relief applies to the total, capped.
    pension_fund_employee_pct=Column(Float,default=0.0)     # e.g. 0.075 = 7.5% of gross salary
    pension_fund_employer_pct=Column(Float,default=0.0)     # e.g. 0.075 = 7.5% of gross salary
    pension_employee_fixed=Column(Float,default=0.0)        # optional fixed monthly ZAR top-up (voluntary)
    pension_employer_fixed=Column(Float,default=0.0)        # optional fixed monthly ZAR employer add-on
    # Medical aid (s6A MTC: R376/month main+first dependant, R254 additional — 2026/2027)
    medical_aid_employee=Column(Float,default=0.0)       # employee monthly contribution (ZAR)
    medical_aid_employer=Column(Float,default=0.0)       # employer monthly contribution (ZAR) — taxable fringe benefit
    medical_aid_dependants=Column(Integer,default=0)     # dependants excluding main member
    bank_name=Column(String); bank_account=Column(String)
    account_number=Column(String); branch_code=Column(String); account_type=Column(String)
    is_active=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="employees")
    payslips=relationship("Payslip",back_populates="employee")
    leave_requests=relationship("LeaveRequest",back_populates="employee")
    leave_balance=relationship("LeaveBalance",back_populates="employee",uselist=False)

class InventoryItem(Base):
    __tablename__ = "inventory"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    sku=Column(String); name=Column(String,nullable=False)
    description=Column(Text); category=Column(String)
    unit_cost=Column(Float,default=0)        # cost price (COGS)
    unit_price=Column(Float,default=0)       # selling price
    quantity_on_hand=Column(Float,default=0)
    reorder_level=Column(Float,default=5)    # alert when stock falls below
    unit_of_measure=Column(String,default="Unit")
    is_active=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="inventory")

class Payslip(Base):
    __tablename__ = "payslips"
    id=Column(Integer,primary_key=True,index=True)
    employee_id=Column(Integer,ForeignKey("employees.id"))
    period=Column(String); gross_salary=Column(Float); paye=Column(Float)
    uif_employee=Column(Float); uif_employer=Column(Float); sdl=Column(Float)
    net_pay=Column(Float); total_cost=Column(Float)
    # BCEA overtime breakdown
    overtime_hours=Column(Float,default=0)   # weekday/Saturday OT hours (1.5x)
    overtime_amount=Column(Float,default=0)
    sunday_hours=Column(Float,default=0)     # Sunday hours (2x)
    sunday_amount=Column(Float,default=0)
    ph_hours=Column(Float,default=0)         # public holiday hours (2x)
    ph_amount=Column(Float,default=0)
    # Pension / Provident fund
    pension_employee=Column(Float,default=0.0)       # employee monthly contribution (ZAR)
    pension_employer=Column(Float,default=0.0)       # employer monthly contribution (ZAR)
    s11f_deduction=Column(Float,default=0.0)         # s11F monthly deduction applied
    # Medical aid
    medical_aid_employee_ded=Column(Float,default=0.0)  # employee deduction
    medical_aid_employer_con=Column(Float,default=0.0)  # employer contribution (fringe benefit)
    medical_tax_credit=Column(Float,default=0.0)        # s6A MTC applied (reduces PAYE)
    generated_at=Column(DateTime,default=datetime.utcnow)
    employee=relationship("Employee",back_populates="payslips")

class APIKey(Base):
    __tablename__ = "api_keys"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    name=Column(String,nullable=False)            # e.g. "My Integration"
    key_hash=Column(String,nullable=False,unique=True)  # hashed key
    key_prefix=Column(String,nullable=False)       # first 8 chars for display
    scopes=Column(String,default="read")           # comma-separated: read,write,payroll
    is_active=Column(Boolean,default=True)
    last_used=Column(DateTime,nullable=True)
    requests_today=Column(Integer,default=0)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="api_keys")

class Customer(Base):
    __tablename__="customers"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    name=Column(String,nullable=False)
    contact_person=Column(String); email=Column(String); phone=Column(String)
    address=Column(Text); vat_number=Column(String)
    payment_terms=Column(Integer,default=30)  # days
    notes=Column(Text); is_active=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="customers")

class Supplier(Base):
    __tablename__="suppliers"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    name=Column(String,nullable=False)
    contact_person=Column(String); email=Column(String); phone=Column(String)
    address=Column(Text); vat_number=Column(String)
    bank_name=Column(String); account_number=Column(String)
    branch_code=Column(String); account_type=Column(String)
    payment_terms=Column(Integer,default=30)
    notes=Column(Text); is_active=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="suppliers")
    purchase_orders=relationship("PurchaseOrder",back_populates="supplier")

class PurchaseOrder(Base):
    # CURRENCY POLICY (audit 2026-07-05): purchase orders are ZAR-only by design —
    # there is deliberately no currency/exchange_rate column. All downstream AP code
    # (_po_delivered_net, /reports/creditors-aging, post_po_received/post_po_paid,
    # AP control account 2000) assumes ZAR amounts. If foreign-currency POs are ever
    # added, every one of those consumers needs exchange-rate handling first.
    __tablename__="purchase_orders"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    supplier_id=Column(Integer,ForeignKey("suppliers.id"),nullable=True)
    po_number=Column(String,nullable=False)
    supplier_name=Column(String)
    status=Column(String,default="draft")  # draft, sent, received, partial, cancelled
    order_date=Column(DateTime,default=datetime.utcnow)
    delivery_date=Column(DateTime,nullable=True)
    subtotal=Column(Float,default=0); vat_amount=Column(Float,default=0); total_amount=Column(Float,default=0)
    notes=Column(Text); received_date=Column(DateTime,nullable=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="purchase_orders")
    supplier=relationship("Supplier",back_populates="purchase_orders")
    items=relationship("PurchaseOrderItem",back_populates="purchase_order",cascade="all, delete-orphan")

class PurchaseOrderItem(Base):
    __tablename__="purchase_order_items"
    id=Column(Integer,primary_key=True,index=True)
    purchase_order_id=Column(Integer,ForeignKey("purchase_orders.id"))
    description=Column(String,nullable=False)
    quantity=Column(Float,default=1); unit_price=Column(Float,default=0); total=Column(Float,default=0)
    # Cumulative quantity received across all deliveries (audit fix 2026-07-02:
    # enables multi-delivery POs to reach "received" and blocks over-receipt double-posting)
    quantity_received=Column(Float,default=0)
    purchase_order=relationship("PurchaseOrder",back_populates="items")

class Quote(Base):
    __tablename__="quotes"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    quote_number=Column(String,nullable=False)
    client_name=Column(String,nullable=False)
    client_email=Column(String,nullable=True)
    description=Column(Text)
    amount=Column(Float,nullable=False)
    vat_applicable=Column(Boolean,default=True)
    vat_amount=Column(Float,default=0)
    total_amount=Column(Float,nullable=False)
    currency=Column(String,default="ZAR")
    exchange_rate=Column(Float,default=1)
    status=Column(String,default="draft")
    valid_until=Column(DateTime,nullable=True)
    notes=Column(Text,nullable=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="quotes")

class Account(Base):
    """Chart of Accounts — one set per company, system accounts auto-created."""
    __tablename__="accounts"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    code=Column(String,nullable=False)              # e.g. "1100"
    name=Column(String,nullable=False)              # e.g. "Accounts Receivable"
    type=Column(Enum(AccountType),nullable=False)
    is_system=Column(Boolean,default=False)         # system accounts can't be deleted
    is_active=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="accounts")
    journal_lines=relationship("JournalLine",back_populates="account")

class JournalEntry(Base):
    """Header record for a double-entry transaction."""
    __tablename__="journal_entries"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    date=Column(DateTime,nullable=False)
    description=Column(Text)
    reference=Column(String)        # e.g. "INV-0001", "EXP-0042", "PAY-0003"
    source=Column(String)           # "invoice","expense","payroll","purchase_order","manual"
    source_id=Column(Integer,nullable=True)   # FK to the originating record
    is_reconciled=Column(Boolean,default=False)
    # ── Auto-reversal fields ─────────────────────────────────────────────────
    auto_reverse=Column(Boolean,default=False)        # True = reverse automatically on reversal_date
    reversal_date=Column(DateTime,nullable=True)      # Date on which the reversal entry should be posted
    is_reversal_of=Column(Integer,nullable=True)      # ID of the original entry this one reverses
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="journal_entries")
    lines=relationship("JournalLine",back_populates="entry",cascade="all, delete-orphan")

class JournalLine(Base):
    """Single debit or credit line within a journal entry."""
    __tablename__="journal_lines"
    id=Column(Integer,primary_key=True,index=True)
    entry_id=Column(Integer,ForeignKey("journal_entries.id"))
    account_id=Column(Integer,ForeignKey("accounts.id"))
    debit=Column(Float,default=0)
    credit=Column(Float,default=0)
    description=Column(String,nullable=True)
    entry=relationship("JournalEntry",back_populates="lines")
    account=relationship("Account",back_populates="journal_lines")

class Budget(Base):
    __tablename__="budgets"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    year=Column(Integer,nullable=False)
    month=Column(Integer,nullable=False)          # 1-12
    category=Column(String,nullable=False)        # expense category or "Revenue"
    department=Column(String,nullable=True)       # optional dept/project tag
    type=Column(String,default="expense")         # "expense" or "income"
    amount=Column(Float,nullable=False,default=0)
    created_at=Column(DateTime,default=datetime.utcnow)
    updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    company=relationship("Company",back_populates="budgets")

class Payment(Base):
    __tablename__ = "payments"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    amount=Column(Float,nullable=False); currency=Column(String,default="ZAR")
    plan=Column(String); billing_cycle=Column(String)
    payfast_id=Column(String,nullable=True); status=Column(String,default="pending")
    payment_method=Column(String); created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="payments")

class LeaveRequest(Base):
    """One leave application per employee per period."""
    __tablename__ = "leave_requests"
    id             = Column(Integer, primary_key=True, index=True)
    company_id     = Column(Integer, ForeignKey("companies.id"))
    employee_id    = Column(Integer, ForeignKey("employees.id"))
    leave_type     = Column(String, nullable=False)   # annual/sick/family/maternity/unpaid
    start_date     = Column(DateTime, nullable=False)
    end_date       = Column(DateTime, nullable=False)
    days_requested = Column(Float, nullable=False)
    status         = Column(String, default="pending")  # pending/approved/rejected/cancelled
    reason         = Column(Text, nullable=True)
    submitted_at   = Column(DateTime, default=datetime.utcnow)
    reviewed_at    = Column(DateTime, nullable=True)
    reviewed_by    = Column(String, nullable=True)
    auto_approved  = Column(Boolean, default=False)
    employee       = relationship("Employee", back_populates="leave_requests")
    company        = relationship("Company", back_populates="leave_requests")

class LeaveBalance(Base):
    """Running leave balance per employee (one row per employee)."""
    __tablename__ = "leave_balances"
    id                 = Column(Integer, primary_key=True, index=True)
    company_id         = Column(Integer, ForeignKey("companies.id"))
    employee_id        = Column(Integer, ForeignKey("employees.id"), unique=True)
    # Annual leave — BCEA: 15 working days/year; accrues at 1.25 days/month
    annual_balance     = Column(Float, default=15.0)
    annual_accrued_ytd = Column(Float, default=0.0)
    annual_taken_ytd   = Column(Float, default=0.0)
    # Sick leave — BCEA: 30 days per 3-year cycle
    sick_balance       = Column(Float, default=30.0)
    sick_taken_ytd     = Column(Float, default=0.0)
    # Family responsibility — BCEA: 3 days/year
    family_balance     = Column(Float, default=3.0)
    family_taken_ytd   = Column(Float, default=0.0)
    last_accrual_date  = Column(DateTime, nullable=True)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    employee           = relationship("Employee", back_populates="leave_balance")
    company            = relationship("Company", back_populates="leave_balances")

class FixedAsset(Base):
    """Fixed asset register — IAS 16 / IFRS for SMEs Section 17."""
    __tablename__ = "fixed_assets"
    id                      = Column(Integer, primary_key=True, index=True)
    company_id              = Column(Integer, ForeignKey("companies.id"))
    asset_number            = Column(String, nullable=True)       # e.g. FA-001
    asset_name              = Column(String, nullable=False)
    category                = Column(String, nullable=False)      # e.g. Vehicles, Equipment
    description             = Column(Text, nullable=True)
    location                = Column(String, nullable=True)
    # Cost model (IAS 16.30)
    purchase_date           = Column(DateTime, nullable=False)
    cost                    = Column(Float, nullable=False)       # original cost (ZAR)
    residual_value          = Column(Float, default=0.0)          # expected scrap/residual
    useful_life_months      = Column(Integer, nullable=False)     # e.g. 60 = 5 years
    # Depreciation
    depreciation_method     = Column(String, default="straight_line")  # straight_line | diminishing_balance
    depreciation_rate       = Column(Float, nullable=True)        # for DB method, e.g. 0.20 = 20%
    accumulated_depreciation = Column(Float, default=0.0)
    last_depreciation_date  = Column(DateTime, nullable=True)
    # Status
    status                  = Column(String, default="active")   # active | disposed | written_off
    # Disposal (IAS 16.67-72)
    disposal_date           = Column(DateTime, nullable=True)
    disposal_proceeds       = Column(Float, nullable=True)
    disposal_gain_loss      = Column(Float, nullable=True)        # positive = gain, negative = loss
    disposal_notes          = Column(Text, nullable=True)
    # SARS tax depreciation (s11(e) / IN47 — for deferred tax)
    sars_category           = Column(String, nullable=True)    # SARS IN47 category name
    wear_and_tear_rate      = Column(Float, nullable=True)     # % p.a. s11(e)/IN47 override, e.g. 33.33
    # Audit
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    company                 = relationship("Company", back_populates="fixed_assets")
    depreciation_entries    = relationship("DepreciationEntry", back_populates="asset", cascade="all, delete-orphan")

    @property
    def carrying_value(self):
        return max(self.residual_value, self.cost - self.accumulated_depreciation)


class DepreciationEntry(Base):
    """Monthly depreciation journal posted for each fixed asset."""
    __tablename__ = "depreciation_entries"
    id             = Column(Integer, primary_key=True, index=True)
    company_id     = Column(Integer, ForeignKey("companies.id"))
    asset_id       = Column(Integer, ForeignKey("fixed_assets.id"))
    period         = Column(String, nullable=False)   # YYYY-MM
    amount         = Column(Float, nullable=False)    # depreciation charged this period
    posted_at      = Column(DateTime, default=datetime.utcnow)
    asset          = relationship("FixedAsset", back_populates="depreciation_entries")
    company        = relationship("Company", foreign_keys=[company_id])


class SubscriptionPayment(Base):
    """ZuZan's own revenue ledger — one row per subscription fee collected."""
    __tablename__ = "subscription_payments"
    id              = Column(Integer, primary_key=True, index=True)
    company_id      = Column(Integer, ForeignKey("companies.id"), nullable=True)
    company_name    = Column(String, nullable=False)          # denormalized for easy reporting
    owner_email     = Column(String, nullable=True)
    plan            = Column(String, nullable=False)          # starter / professional / business
    billing_cycle   = Column(String, default="monthly")       # monthly / annual
    amount          = Column(Float, nullable=False)           # ZAR amount collected
    payfast_payment_id = Column(String, nullable=True)        # pf_payment_id from PayFast
    internal_payment_id = Column(Integer, nullable=True)      # FK to payments.id
    status          = Column(String, default="success")       # success / failed / refunded
    payment_date    = Column(DateTime, default=datetime.utcnow)
    period_start    = Column(DateTime, nullable=True)
    period_end      = Column(DateTime, nullable=True)
    notes           = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    company         = relationship("Company", foreign_keys=[company_id])


class InviteToken(Base):
    """Pending team invitation — one row per invite sent."""
    __tablename__ = "invite_tokens"
    id         = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    email      = Column(String, nullable=False, index=True)
    role       = Column(String, nullable=False, default="accountant")  # admin|accountant|employee
    token      = Column(String, nullable=False, unique=True, index=True)
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at    = Column(DateTime, nullable=True)
    company    = relationship("Company", foreign_keys=[company_id])

class AuditLog(Base):
    """Immutable record of every mutation in a company."""
    __tablename__ = "audit_log"
    id          = Column(Integer, primary_key=True, index=True)
    company_id  = Column(Integer, ForeignKey("companies.id"), nullable=False)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email  = Column(String, nullable=True)   # denormalised for easy display
    action      = Column(String, nullable=False)  # e.g. "invoice.created"
    target_type = Column(String, nullable=True)   # e.g. "invoice"
    target_id   = Column(Integer, nullable=True)
    detail      = Column(Text, nullable=True)     # JSON string for extra context
    created_at  = Column(DateTime, default=datetime.utcnow)
    company     = relationship("Company", foreign_keys=[company_id])


class CompanyDocument(Base):
    """Document vault — stores company docs (PDF, DOCX, etc.) as base64 in the DB."""
    __tablename__ = "company_documents"
    id          = Column(Integer, primary_key=True, index=True)
    company_id  = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    name        = Column(String, nullable=False)          # user-given display name
    category    = Column(String, default="General")      # CIPC, Tax, Contracts, AFS, Payroll, Insurance, General
    description = Column(Text, nullable=True)
    file_name   = Column(String, nullable=False)          # original filename
    file_type   = Column(String, nullable=False)          # MIME type
    file_size   = Column(Integer, default=0)             # bytes
    file_data   = Column(Text, nullable=False)            # base64-encoded binary
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    company     = relationship("Company", back_populates="documents")


# ── PILLAR 3: STITCH BANK FEEDS ──────────────────────────────────────────────

class StitchConnection(Base):
    """Stitch OAuth tokens per company — one row per connected company."""
    __tablename__ = "stitch_connections"
    id            = Column(Integer, primary_key=True, index=True)
    company_id    = Column(Integer, ForeignKey("companies.id"), unique=True, nullable=False)
    stitch_user_id = Column(String, nullable=True)   # sub claim from id_token
    access_token  = Column(Text, nullable=False)     # encrypted Fernet token
    refresh_token = Column(Text, nullable=False)     # encrypted Fernet token
    token_expiry  = Column(DateTime, nullable=False) # when access_token expires
    scopes        = Column(String, nullable=True)    # granted OAuth scopes
    connected_at  = Column(DateTime, default=datetime.utcnow)
    last_synced   = Column(DateTime, nullable=True)
    company       = relationship("Company", foreign_keys=[company_id])


class StitchBankAccount(Base):
    """A bank account linked via Stitch for a company."""
    __tablename__ = "stitch_bank_accounts"
    id                  = Column(Integer, primary_key=True, index=True)
    company_id          = Column(Integer, ForeignKey("companies.id"))
    stitch_account_id   = Column(String, nullable=False, unique=True)  # Stitch node ID
    bank_id             = Column(String, nullable=True)   # e.g. "fnb", "absa"
    account_number      = Column(String, nullable=True)   # encrypted
    account_name        = Column(String, nullable=True)   # e.g. "Business Cheque"
    account_type        = Column(String, nullable=True)   # e.g. "current"
    current_balance     = Column(Float, nullable=True)
    available_balance   = Column(Float, nullable=True)
    currency            = Column(String, default="ZAR")
    last_synced         = Column(DateTime, nullable=True)
    is_active           = Column(Boolean, default=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    company             = relationship("Company", foreign_keys=[company_id])
    transactions        = relationship("StitchTransaction", back_populates="bank_account", cascade="all, delete-orphan")


class StitchTransaction(Base):
    """A transaction synced from Stitch."""
    __tablename__ = "stitch_transactions"
    id                  = Column(Integer, primary_key=True, index=True)
    company_id          = Column(Integer, ForeignKey("companies.id"))
    bank_account_id     = Column(Integer, ForeignKey("stitch_bank_accounts.id"))
    stitch_txn_id       = Column(String, nullable=False, unique=True)
    amount              = Column(Float, nullable=False)    # positive=credit, negative=debit
    description         = Column(Text, nullable=True)
    reference           = Column(String, nullable=True)
    txn_date            = Column(DateTime, nullable=False)
    running_balance     = Column(Float, nullable=True)
    # Matching
    match_status        = Column(String, default="unmatched")  # unmatched|matched|excluded
    matched_invoice_id  = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    matched_expense_id  = Column(Integer, ForeignKey("expenses.id"), nullable=True)
    match_confidence    = Column(Float, nullable=True)   # 0.0–1.0
    matched_at          = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    bank_account        = relationship("StitchBankAccount", back_populates="transactions")
    company             = relationship("Company", foreign_keys=[company_id])

class SaltEdgeConnection(Base):
    """Salt Edge connection for a company (one per company)."""
    __tablename__ = "saltedge_connections"
    id                      = Column(Integer, primary_key=True, index=True)
    company_id              = Column(Integer, ForeignKey("companies.id"), unique=True, nullable=False)
    saltedge_customer_id    = Column(String, nullable=True)   # Salt Edge customer id
    saltedge_connection_id  = Column(String, nullable=True, unique=True)  # connection id
    provider_name           = Column(String, nullable=True)   # e.g. "FNB", "ABSA"
    status                  = Column(String, default="active")  # active|inactive|error
    connected_at            = Column(DateTime, default=datetime.utcnow)
    last_synced             = Column(DateTime, nullable=True)
    company                 = relationship("Company", foreign_keys=[company_id])

class SaltEdgeBankAccount(Base):
    """A bank account synced from Salt Edge."""
    __tablename__ = "saltedge_bank_accounts"
    id                      = Column(Integer, primary_key=True, index=True)
    company_id              = Column(Integer, ForeignKey("companies.id"))
    connection_id           = Column(Integer, ForeignKey("saltedge_connections.id"))
    saltedge_account_id     = Column(String, nullable=False, unique=True)
    name                    = Column(String, nullable=True)
    nature                  = Column(String, nullable=True)   # card, account, savings, etc.
    balance                 = Column(Float, nullable=True)
    currency_code           = Column(String, default="ZAR")
    is_active               = Column(Boolean, default=True)
    last_synced             = Column(DateTime, nullable=True)
    created_at              = Column(DateTime, default=datetime.utcnow)
    company                 = relationship("Company", foreign_keys=[company_id])
    transactions            = relationship("SaltEdgeTransaction", back_populates="bank_account", cascade="all, delete-orphan")

class SaltEdgeTransaction(Base):
    """A transaction synced from Salt Edge."""
    __tablename__ = "saltedge_transactions"
    id                  = Column(Integer, primary_key=True, index=True)
    company_id          = Column(Integer, ForeignKey("companies.id"))
    bank_account_id     = Column(Integer, ForeignKey("saltedge_bank_accounts.id"))
    saltedge_txn_id     = Column(String, nullable=False, unique=True)
    amount              = Column(Float, nullable=False)    # positive=credit, negative=debit
    description         = Column(Text, nullable=True)
    made_on             = Column(DateTime, nullable=False)
    status              = Column(String, nullable=True)    # posted|pending
    match_status        = Column(String, default="unmatched")  # unmatched|matched|excluded
    matched_invoice_id  = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    matched_expense_id  = Column(Integer, ForeignKey("expenses.id"), nullable=True)
    match_confidence    = Column(Float, nullable=True)
    matched_at          = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    bank_account        = relationship("SaltEdgeBankAccount", back_populates="transactions")
    company             = relationship("Company", foreign_keys=[company_id])

# ── ABSA Direct Feed Models ───────────────────────────────────────────────────

class AbsaConnection(Base):
    """ABSA OAuth connection per company."""
    __tablename__ = "absa_connections"
    id            = Column(Integer, primary_key=True, index=True)
    company_id    = Column(Integer, ForeignKey("companies.id"), unique=True, nullable=False)
    access_token  = Column(Text, nullable=True)      # encrypted
    refresh_token = Column(Text, nullable=True)      # encrypted
    token_expiry  = Column(DateTime, nullable=True)
    scopes        = Column(String, nullable=True)
    connected_at  = Column(DateTime, default=datetime.utcnow)
    last_synced   = Column(DateTime, nullable=True)
    company       = relationship("Company", foreign_keys=[company_id])

class AbsaBankAccount(Base):
    """A bank account linked via ABSA for a company."""
    __tablename__ = "absa_bank_accounts"
    id              = Column(Integer, primary_key=True, index=True)
    company_id      = Column(Integer, ForeignKey("companies.id"))
    absa_account_id = Column(String, nullable=False, unique=True)
    account_number  = Column(String, nullable=True)   # encrypted
    account_name    = Column(String, nullable=True)
    account_type    = Column(String, nullable=True)
    current_balance = Column(Float, nullable=True)
    currency        = Column(String, default="ZAR")
    last_synced     = Column(DateTime, nullable=True)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    company         = relationship("Company", foreign_keys=[company_id])
    transactions    = relationship("AbsaTransaction", back_populates="bank_account", cascade="all, delete-orphan")

class AbsaTransaction(Base):
    """A transaction synced from ABSA."""
    __tablename__ = "absa_transactions"
    id                 = Column(Integer, primary_key=True, index=True)
    company_id         = Column(Integer, ForeignKey("companies.id"))
    bank_account_id    = Column(Integer, ForeignKey("absa_bank_accounts.id"))
    absa_txn_id        = Column(String, nullable=False, unique=True)
    amount             = Column(Float, nullable=False)
    description        = Column(Text, nullable=True)
    reference          = Column(String, nullable=True)
    txn_date           = Column(DateTime, nullable=False)
    running_balance    = Column(Float, nullable=True)
    match_status       = Column(String, default="unmatched")
    matched_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    matched_expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)
    match_confidence   = Column(Float, nullable=True)
    matched_at         = Column(DateTime, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)
    bank_account       = relationship("AbsaBankAccount", back_populates="transactions")
    company            = relationship("Company", foreign_keys=[company_id])

# ── Nedbank Direct Feed Models ────────────────────────────────────────────────

class NedbankConnection(Base):
    """Nedbank OAuth connection per company."""
    __tablename__ = "nedbank_connections"
    id            = Column(Integer, primary_key=True, index=True)
    company_id    = Column(Integer, ForeignKey("companies.id"), unique=True, nullable=False)
    access_token  = Column(Text, nullable=True)      # encrypted
    refresh_token = Column(Text, nullable=True)      # encrypted
    token_expiry  = Column(DateTime, nullable=True)
    scopes        = Column(String, nullable=True)
    connected_at  = Column(DateTime, default=datetime.utcnow)
    last_synced   = Column(DateTime, nullable=True)
    company       = relationship("Company", foreign_keys=[company_id])

class NedbankBankAccount(Base):
    """A bank account linked via Nedbank for a company."""
    __tablename__ = "nedbank_bank_accounts"
    id                  = Column(Integer, primary_key=True, index=True)
    company_id          = Column(Integer, ForeignKey("companies.id"))
    nedbank_account_id  = Column(String, nullable=False, unique=True)
    account_number      = Column(String, nullable=True)   # encrypted
    account_name        = Column(String, nullable=True)
    account_type        = Column(String, nullable=True)
    current_balance     = Column(Float, nullable=True)
    currency            = Column(String, default="ZAR")
    last_synced         = Column(DateTime, nullable=True)
    is_active           = Column(Boolean, default=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    company             = relationship("Company", foreign_keys=[company_id])
    transactions        = relationship("NedbankTransaction", back_populates="bank_account", cascade="all, delete-orphan")

class NedbankTransaction(Base):
    """A transaction synced from Nedbank."""
    __tablename__ = "nedbank_transactions"
    id                 = Column(Integer, primary_key=True, index=True)
    company_id         = Column(Integer, ForeignKey("companies.id"))
    bank_account_id    = Column(Integer, ForeignKey("nedbank_bank_accounts.id"))
    nedbank_txn_id     = Column(String, nullable=False, unique=True)
    amount             = Column(Float, nullable=False)
    description        = Column(Text, nullable=True)
    reference          = Column(String, nullable=True)
    txn_date           = Column(DateTime, nullable=False)
    running_balance    = Column(Float, nullable=True)
    match_status       = Column(String, default="unmatched")
    matched_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    matched_expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)
    match_confidence   = Column(Float, nullable=True)
    matched_at         = Column(DateTime, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)
    bank_account       = relationship("NedbankBankAccount", back_populates="transactions")
    company            = relationship("Company", foreign_keys=[company_id])

# ── Investec Direct Feed ──────────────────────────────────────────────────────
class InvestecConnection(Base):
    """OAuth token + metadata for a company's Investec connection."""
    __tablename__ = "investec_connections"
    id            = Column(Integer, primary_key=True, index=True)
    company_id    = Column(Integer, ForeignKey("companies.id"), unique=True)
    access_token  = Column(Text, nullable=True)    # Fernet-encrypted
    refresh_token = Column(Text, nullable=True)    # Fernet-encrypted
    token_expiry  = Column(DateTime, nullable=True)
    scopes        = Column(String, nullable=True)
    connected_at  = Column(DateTime, nullable=True)
    last_synced   = Column(DateTime, nullable=True)
    company       = relationship("Company", foreign_keys=[company_id])

class InvestecBankAccount(Base):
    """A bank account linked via Investec."""
    __tablename__ = "investec_bank_accounts"
    id                   = Column(Integer, primary_key=True, index=True)
    company_id           = Column(Integer, ForeignKey("companies.id"))
    investec_account_id  = Column(String, unique=True, nullable=False)
    account_number       = Column(Text, nullable=True)   # Fernet-encrypted
    account_name         = Column(String, nullable=True)
    account_type         = Column(String, nullable=True)
    current_balance      = Column(Float, nullable=True)
    currency             = Column(String, default="ZAR")
    last_synced          = Column(DateTime, nullable=True)
    is_active            = Column(Boolean, default=True)
    created_at           = Column(DateTime, default=datetime.utcnow)
    company              = relationship("Company", foreign_keys=[company_id])
    transactions         = relationship("InvestecTransaction", back_populates="bank_account", cascade="all, delete-orphan")

class InvestecTransaction(Base):
    """A transaction synced from Investec."""
    __tablename__ = "investec_transactions"
    id                 = Column(Integer, primary_key=True, index=True)
    company_id         = Column(Integer, ForeignKey("companies.id"))
    bank_account_id    = Column(Integer, ForeignKey("investec_bank_accounts.id"))
    investec_txn_id    = Column(String, nullable=False, unique=True)
    amount             = Column(Float, nullable=False)   # negative = debit
    description        = Column(Text, nullable=True)
    reference          = Column(String, nullable=True)
    txn_date           = Column(DateTime, nullable=False)
    running_balance    = Column(Float, nullable=True)
    match_status       = Column(String, default="unmatched")
    matched_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    matched_expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)
    match_confidence   = Column(Float, nullable=True)
    matched_at         = Column(DateTime, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)
    bank_account       = relationship("InvestecBankAccount", back_populates="transactions")
    company            = relationship("Company", foreign_keys=[company_id])

# ── Standard Bank Direct Feed ─────────────────────────────────────────────────
class StandardBankConnection(Base):
    """OAuth token + metadata for a company's Standard Bank connection."""
    __tablename__ = "standardbank_connections"
    id            = Column(Integer, primary_key=True, index=True)
    company_id    = Column(Integer, ForeignKey("companies.id"), unique=True)
    access_token  = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expiry  = Column(DateTime, nullable=True)
    scopes        = Column(String, nullable=True)
    connected_at  = Column(DateTime, nullable=True)
    last_synced   = Column(DateTime, nullable=True)
    company       = relationship("Company", foreign_keys=[company_id])

class StandardBankBankAccount(Base):
    """A bank account linked via Standard Bank."""
    __tablename__ = "standardbank_bank_accounts"
    id                      = Column(Integer, primary_key=True, index=True)
    company_id              = Column(Integer, ForeignKey("companies.id"))
    standardbank_account_id = Column(String, unique=True, nullable=False)
    account_number          = Column(Text, nullable=True)
    account_name            = Column(String, nullable=True)
    account_type            = Column(String, nullable=True)
    current_balance         = Column(Float, nullable=True)
    currency                = Column(String, default="ZAR")
    last_synced             = Column(DateTime, nullable=True)
    is_active               = Column(Boolean, default=True)
    created_at              = Column(DateTime, default=datetime.utcnow)
    company                 = relationship("Company", foreign_keys=[company_id])
    transactions            = relationship("StandardBankTransaction", back_populates="bank_account", cascade="all, delete-orphan")

class StandardBankTransaction(Base):
    """A transaction synced from Standard Bank."""
    __tablename__ = "standardbank_transactions"
    id                      = Column(Integer, primary_key=True, index=True)
    company_id              = Column(Integer, ForeignKey("companies.id"))
    bank_account_id         = Column(Integer, ForeignKey("standardbank_bank_accounts.id"))
    standardbank_txn_id     = Column(String, nullable=False, unique=True)
    amount                  = Column(Float, nullable=False)
    description             = Column(Text, nullable=True)
    reference               = Column(String, nullable=True)
    txn_date                = Column(DateTime, nullable=False)
    running_balance         = Column(Float, nullable=True)
    match_status            = Column(String, default="unmatched")
    matched_invoice_id      = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    matched_expense_id      = Column(Integer, ForeignKey("expenses.id"), nullable=True)
    match_confidence        = Column(Float, nullable=True)
    matched_at              = Column(DateTime, nullable=True)
    created_at              = Column(DateTime, default=datetime.utcnow)
    bank_account            = relationship("StandardBankBankAccount", back_populates="transactions")
    company                 = relationship("Company", foreign_keys=[company_id])

class CategoryRule(Base):
    """Learned categorisation rules for bank CSV imports."""
    __tablename__ = "category_rules"
    id          = Column(Integer, primary_key=True, index=True)
    company_id  = Column(Integer, ForeignKey("companies.id"), nullable=False)
    keyword     = Column(String(100), nullable=False)   # lowercased, trimmed
    category    = Column(String, nullable=False)
    txn_type    = Column(String, default="any")         # "credit" | "debit" | "any"
    match_count = Column(Integer, default=1)            # how many times rule was confirmed
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    company     = relationship("Company", back_populates="category_rules")


class RecurringInvoice(Base):
    """Template for invoices that are generated automatically on a schedule."""
    __tablename__ = "recurring_invoices"
    id                  = Column(Integer, primary_key=True, index=True)
    company_id          = Column(Integer, ForeignKey("companies.id"), nullable=False)
    client_name         = Column(String, nullable=False)
    client_email        = Column(String, nullable=True)
    description         = Column(Text, nullable=True)
    amount              = Column(Float, nullable=False)   # excl. VAT
    vat_applicable      = Column(Boolean, default=True)
    currency            = Column(String, default="ZAR")
    frequency           = Column(String, nullable=False)  # weekly|monthly|quarterly|annually
    start_date          = Column(DateTime, nullable=False)
    next_run_date       = Column(DateTime, nullable=True)
    last_run_date       = Column(DateTime, nullable=True)
    is_active           = Column(Boolean, default=True)
    invoices_generated  = Column(Integer, default=0)
    created_at          = Column(DateTime, default=datetime.utcnow)
    company             = relationship("Company", back_populates="recurring_invoices")


class CreditNote(Base):
    """Credit note — issued against a paid or sent invoice to reduce the amount owed."""
    __tablename__ = "credit_notes"
    id                  = Column(Integer, primary_key=True, index=True)
    company_id          = Column(Integer, ForeignKey("companies.id"), nullable=False)
    invoice_id          = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    credit_note_number  = Column(String, nullable=False)
    client_name         = Column(String, nullable=False)
    description         = Column(Text, nullable=True)
    amount              = Column(Float, nullable=False)   # excl. VAT
    vat_amount          = Column(Float, default=0)
    total_amount        = Column(Float, nullable=False)   # incl. VAT
    currency            = Column(String, default="ZAR")
    issue_date          = Column(DateTime, default=datetime.utcnow)
    notes               = Column(Text, nullable=True)
    journal_entry_id    = Column(Integer, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    company             = relationship("Company", back_populates="credit_notes")
    invoice             = relationship("Invoice")


class SiteVisit(Base):
    """Anonymous site visit / engagement tracking — no PII stored."""
    __tablename__ = "site_visits"
    id          = Column(Integer, primary_key=True, index=True)
    session_id  = Column(String, nullable=True)   # client-generated UUID (localStorage)
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)
    page        = Column(String, nullable=True)   # tab or route name
    referrer    = Column(String, nullable=True)   # document.referrer (max 500 chars)
    country     = Column(String, nullable=True)   # from IP geo lookup
    city        = Column(String, nullable=True)
    user_agent  = Column(String, nullable=True)   # truncated to 300 chars
    ip_hash     = Column(String, nullable=True)   # first 16 chars of SHA-256 hash

def init_db():
    # Enable WAL mode for SQLite — far more resilient to crashes than the default
    # rollback-journal mode, and safe to run on every startup (no-op for PostgreSQL).
    if DATABASE_URL.startswith("sqlite"):
        import sqlite3 as _sqlite3, re as _re
        db_path = _re.sub(r"^sqlite:///", "", DATABASE_URL)
        try:
            _conn = _sqlite3.connect(db_path)
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.close()
        except Exception as _e:
            import logging as _log
            _log.getLogger("zuzan.db").warning(
                f"Could not set WAL mode on {db_path}: {_e}. "
                "If the server fails to start, check for a stale .db-journal or .db-wal file "
                "in the backend directory and delete it, then restart."
            )

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        import logging as _log
        _log.getLogger("zuzan.db").critical(
            f"Database schema init failed: {exc}\n"
            "Common causes:\n"
            "  • A stale zuzan.db-journal file (delete it and restart)\n"
            "  • DB file is inside a OneDrive/Dropbox folder (move it outside)\n"
            "  • DATABASE_URL env var points to the wrong host\n"
            "  • PostgreSQL connection refused (check credentials and host)"
        )
        raise
    from sqlalchemy import text
    with engine.connect() as conn:
        for sql in [
            "ALTER TABLE expenses ADD COLUMN vat_amount FLOAT DEFAULT 0",
            "ALTER TABLE users ADD COLUMN reset_token VARCHAR",
            "ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP",
            "ALTER TABLE employees ADD COLUMN tax_number VARCHAR",
            "ALTER TABLE employees ADD COLUMN date_of_birth TIMESTAMP",
            "ALTER TABLE employees ADD COLUMN appointment_date TIMESTAMP",
            "ALTER TABLE employees ADD COLUMN address VARCHAR",
            "ALTER TABLE employees ADD COLUMN account_number VARCHAR",
            "ALTER TABLE employees ADD COLUMN branch_code VARCHAR",
            "ALTER TABLE employees ADD COLUMN account_type VARCHAR",
            "ALTER TABLE api_keys ADD COLUMN requests_today INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN email_verify_token VARCHAR",
            "CREATE TABLE IF NOT EXISTS budgets (id SERIAL PRIMARY KEY, company_id INTEGER REFERENCES companies(id), year INTEGER NOT NULL, month INTEGER NOT NULL, category VARCHAR NOT NULL, department VARCHAR, type VARCHAR DEFAULT 'expense', amount FLOAT DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS accounts (id SERIAL PRIMARY KEY, company_id INTEGER REFERENCES companies(id), code VARCHAR NOT NULL, name VARCHAR NOT NULL, type VARCHAR NOT NULL, is_system BOOLEAN DEFAULT FALSE, is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS journal_entries (id SERIAL PRIMARY KEY, company_id INTEGER REFERENCES companies(id), date TIMESTAMP NOT NULL, description TEXT, reference VARCHAR, source VARCHAR, source_id INTEGER, is_reconciled BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS journal_lines (id SERIAL PRIMARY KEY, entry_id INTEGER REFERENCES journal_entries(id) ON DELETE CASCADE, account_id INTEGER REFERENCES accounts(id), debit FLOAT DEFAULT 0, credit FLOAT DEFAULT 0, description VARCHAR)",
            "ALTER TABLE invoices ADD COLUMN currency VARCHAR DEFAULT 'ZAR'",
            "ALTER TABLE invoices ADD COLUMN exchange_rate FLOAT DEFAULT 1",
            "ALTER TABLE invoices ADD COLUMN paid_amount_zar FLOAT",
            "ALTER TABLE companies ADD COLUMN logo_url TEXT",
            "ALTER TABLE purchase_orders ADD COLUMN received_date TIMESTAMP",
            "ALTER TABLE companies ADD COLUMN payroll_pin_hash VARCHAR",
            "ALTER TABLE companies ADD COLUMN cipc_registration_date TIMESTAMP",
            """CREATE TABLE IF NOT EXISTS leave_requests (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                employee_id INTEGER REFERENCES employees(id),
                leave_type VARCHAR NOT NULL,
                start_date TIMESTAMP NOT NULL,
                end_date TIMESTAMP NOT NULL,
                days_requested FLOAT NOT NULL,
                status VARCHAR DEFAULT 'pending',
                reason TEXT,
                submitted_at TIMESTAMP DEFAULT NOW(),
                reviewed_at TIMESTAMP,
                reviewed_by VARCHAR,
                auto_approved BOOLEAN DEFAULT FALSE
            )""",
            """CREATE TABLE IF NOT EXISTS leave_balances (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                employee_id INTEGER REFERENCES employees(id) UNIQUE,
                annual_balance FLOAT DEFAULT 15.0,
                annual_accrued_ytd FLOAT DEFAULT 0.0,
                annual_taken_ytd FLOAT DEFAULT 0.0,
                sick_balance FLOAT DEFAULT 30.0,
                sick_taken_ytd FLOAT DEFAULT 0.0,
                family_balance FLOAT DEFAULT 3.0,
                family_taken_ytd FLOAT DEFAULT 0.0,
                last_accrual_date TIMESTAMP,
                updated_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS fixed_assets (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                asset_number VARCHAR,
                asset_name VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                description TEXT,
                location VARCHAR,
                purchase_date TIMESTAMP NOT NULL,
                cost FLOAT NOT NULL,
                residual_value FLOAT DEFAULT 0.0,
                useful_life_months INTEGER NOT NULL,
                depreciation_method VARCHAR DEFAULT 'straight_line',
                depreciation_rate FLOAT,
                accumulated_depreciation FLOAT DEFAULT 0.0,
                last_depreciation_date TIMESTAMP,
                status VARCHAR DEFAULT 'active',
                disposal_date TIMESTAMP,
                disposal_proceeds FLOAT,
                disposal_gain_loss FLOAT,
                disposal_notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS depreciation_entries (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                asset_id INTEGER REFERENCES fixed_assets(id),
                period VARCHAR NOT NULL,
                amount FLOAT NOT NULL,
                posted_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS subscription_payments (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                company_name VARCHAR NOT NULL,
                owner_email VARCHAR,
                plan VARCHAR NOT NULL,
                billing_cycle VARCHAR DEFAULT 'monthly',
                amount FLOAT NOT NULL,
                payfast_payment_id VARCHAR,
                internal_payment_id INTEGER,
                status VARCHAR DEFAULT 'success',
                payment_date TIMESTAMP DEFAULT NOW(),
                period_start TIMESTAMP,
                period_end TIMESTAMP,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # ── BCEA grade + overtime columns (2026-06) ──────────────────────
            "ALTER TABLE employees ADD COLUMN grade VARCHAR",
            "ALTER TABLE employees ADD COLUMN employment_type VARCHAR DEFAULT 'salaried'",
            "ALTER TABLE employees ADD COLUMN hourly_rate FLOAT",
            "ALTER TABLE payslips ADD COLUMN overtime_hours FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN overtime_amount FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN sunday_hours FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN sunday_amount FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN ph_hours FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN ph_amount FLOAT DEFAULT 0",
            "ALTER TABLE fixed_assets ADD COLUMN sars_category VARCHAR",
            # ── Reversing journal entries (2026-06) ─────────────────────────
            "ALTER TABLE journal_entries ADD COLUMN auto_reverse BOOLEAN DEFAULT FALSE",
            "ALTER TABLE journal_entries ADD COLUMN reversal_date TIMESTAMP",
            "ALTER TABLE journal_entries ADD COLUMN is_reversal_of INTEGER",
            # ── Credit-term expenses (2026-06) ───────────────────────────────
            "ALTER TABLE expenses ADD COLUMN is_on_credit BOOLEAN DEFAULT FALSE",
            # ── On-credit expense payment tracking (2026-06) ─────────────────
            "ALTER TABLE expenses ADD COLUMN paid_at TIMESTAMP",
            # ── Pillar 2: Client Portal columns (2026-06) ────────────────────
            "ALTER TABLE invoices ADD COLUMN portal_token VARCHAR",
            "ALTER TABLE invoices ADD COLUMN portal_token_created_at TIMESTAMP",
            # ── Pillar 3: Stitch Bank Feeds (2026-06) ────────────────────────
            """CREATE TABLE IF NOT EXISTS stitch_connections (
                id SERIAL PRIMARY KEY,
                company_id INTEGER UNIQUE REFERENCES companies(id),
                stitch_user_id VARCHAR,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                token_expiry TIMESTAMP NOT NULL,
                scopes VARCHAR,
                connected_at TIMESTAMP DEFAULT NOW(),
                last_synced TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS stitch_bank_accounts (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                stitch_account_id VARCHAR NOT NULL UNIQUE,
                bank_id VARCHAR,
                account_number VARCHAR,
                account_name VARCHAR,
                account_type VARCHAR,
                current_balance FLOAT,
                available_balance FLOAT,
                currency VARCHAR DEFAULT 'ZAR',
                last_synced TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS stitch_transactions (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                bank_account_id INTEGER REFERENCES stitch_bank_accounts(id) ON DELETE CASCADE,
                stitch_txn_id VARCHAR NOT NULL UNIQUE,
                amount FLOAT NOT NULL,
                description TEXT,
                reference VARCHAR,
                txn_date TIMESTAMP NOT NULL,
                running_balance FLOAT,
                match_status VARCHAR DEFAULT 'unmatched',
                matched_invoice_id INTEGER REFERENCES invoices(id),
                matched_expense_id INTEGER REFERENCES expenses(id),
                match_confidence FLOAT,
                matched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # ── PO cumulative receipt tracking (audit fix 2026-07-02) ────────
            # Added WITHOUT a SQL default so pre-migration rows are NULL and can be
            # backfilled: items on fully received/paid POs were fully delivered.
            # Remaining NULLs (draft/sent/partial POs) become 0. All three statements
            # are idempotent — safe to run on every startup.
            "ALTER TABLE purchase_order_items ADD COLUMN quantity_received FLOAT",
            "UPDATE purchase_order_items SET quantity_received = quantity WHERE quantity_received IS NULL AND purchase_order_id IN (SELECT id FROM purchase_orders WHERE status IN ('received','paid'))",
            "UPDATE purchase_order_items SET quantity_received = 0 WHERE quantity_received IS NULL",
            # ── Salt Edge Bank Feeds (2026-07) ───────────────────────────────
            """CREATE TABLE IF NOT EXISTS saltedge_connections (
                id SERIAL PRIMARY KEY,
                company_id INTEGER UNIQUE REFERENCES companies(id),
                saltedge_customer_id VARCHAR,
                saltedge_connection_id VARCHAR UNIQUE,
                provider_name VARCHAR,
                status VARCHAR DEFAULT 'active',
                connected_at TIMESTAMP DEFAULT NOW(),
                last_synced TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS saltedge_bank_accounts (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                connection_id INTEGER REFERENCES saltedge_connections(id),
                saltedge_account_id VARCHAR NOT NULL UNIQUE,
                name VARCHAR,
                nature VARCHAR,
                balance FLOAT,
                currency_code VARCHAR DEFAULT 'ZAR',
                is_active BOOLEAN DEFAULT TRUE,
                last_synced TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS saltedge_transactions (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                bank_account_id INTEGER REFERENCES saltedge_bank_accounts(id) ON DELETE CASCADE,
                saltedge_txn_id VARCHAR NOT NULL UNIQUE,
                amount FLOAT NOT NULL,
                description TEXT,
                made_on TIMESTAMP NOT NULL,
                status VARCHAR,
                match_status VARCHAR DEFAULT 'unmatched',
                matched_invoice_id INTEGER REFERENCES invoices(id),
                matched_expense_id INTEGER REFERENCES expenses(id),
                match_confidence FLOAT,
                matched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # ── Pillar 2: Client Portal (2026-06) ────────────────────────────
            # portal_token unique index — DO block for PostgreSQL (plain ALTERs for
            # the columns already run above; SQLite fails this harmlessly via the
            # loop's try/except). Moved INTO the list on 2026-07-03: these four
            # statements previously sat after the loop body as bare string
            # expressions and never executed (dead migration code pitfall).
            """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='invoices' AND column_name='portal_token') THEN
                    ALTER TABLE invoices ADD COLUMN portal_token VARCHAR;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='invoices' AND column_name='portal_token_created_at') THEN
                    ALTER TABLE invoices ADD COLUMN portal_token_created_at TIMESTAMP;
                END IF;
                CREATE UNIQUE INDEX IF NOT EXISTS ix_invoices_portal_token ON invoices (portal_token) WHERE portal_token IS NOT NULL;
            END $$""",
            # ── Pillar 1: Multi-User & Roles (2026-06) ──────────────────────
            # invite_tokens / audit_log are also ORM models (create_all covers new
            # installs); kept here for databases created before the models existed.
            """CREATE TABLE IF NOT EXISTS invite_tokens (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                email VARCHAR NOT NULL,
                role VARCHAR NOT NULL DEFAULT 'accountant',
                token VARCHAR NOT NULL UNIQUE,
                invited_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                user_id INTEGER REFERENCES users(id),
                user_email VARCHAR,
                action VARCHAR NOT NULL,
                target_type VARCHAR,
                target_id INTEGER,
                detail TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # Role backfill — idempotent, safe to run on every startup
            "UPDATE users SET role = 'owner' WHERE role IS NULL OR role = ''",
            # ── Performance indexes (2026-07-03) ─────────────────────────────
            # Every report endpoint filters on company_id (+ status/date), and the
            # journal lookups filter on (source, source_id) and account_id. Without
            # these, each dashboard load is a full table scan per table, which
            # degrades linearly as more companies share one database.
            # CREATE INDEX IF NOT EXISTS works on both SQLite and PostgreSQL 9.5+.
            "CREATE INDEX IF NOT EXISTS ix_invoices_company_status ON invoices (company_id, status)",
            "CREATE INDEX IF NOT EXISTS ix_invoices_company_paid_date ON invoices (company_id, paid_date)",
            "CREATE INDEX IF NOT EXISTS ix_expenses_company_date ON expenses (company_id, expense_date)",
            "CREATE INDEX IF NOT EXISTS ix_pos_company_status ON purchase_orders (company_id, status)",
            "CREATE INDEX IF NOT EXISTS ix_po_items_po ON purchase_order_items (purchase_order_id)",
            "CREATE INDEX IF NOT EXISTS ix_journal_entries_company_source ON journal_entries (company_id, source, source_id)",
            "CREATE INDEX IF NOT EXISTS ix_journal_lines_entry ON journal_lines (entry_id)",
            "CREATE INDEX IF NOT EXISTS ix_journal_lines_account ON journal_lines (account_id)",
            "CREATE INDEX IF NOT EXISTS ix_accounts_company_code ON accounts (company_id, code)",
            "CREATE INDEX IF NOT EXISTS ix_payslips_employee ON payslips (employee_id)",
            "CREATE INDEX IF NOT EXISTS ix_employees_company ON employees (company_id)",
            "CREATE INDEX IF NOT EXISTS ix_customers_company ON customers (company_id)",
            "CREATE INDEX IF NOT EXISTS ix_suppliers_company ON suppliers (company_id)",
            "CREATE INDEX IF NOT EXISTS ix_quotes_company ON quotes (company_id)",
            "CREATE INDEX IF NOT EXISTS ix_depreciation_company_period ON depreciation_entries (company_id, period)",
            # ── Auto-categorisation learning (2026-07-03) ─────────────────────
            """CREATE TABLE IF NOT EXISTS category_rules (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                keyword VARCHAR(100) NOT NULL,
                category VARCHAR NOT NULL,
                txn_type VARCHAR DEFAULT 'any',
                match_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_category_rules_company_keyword_type ON category_rules (company_id, keyword, txn_type)",
            "CREATE INDEX IF NOT EXISTS ix_category_rules_company ON category_rules (company_id)",
            "ALTER TABLE companies ADD COLUMN afs_enabled BOOLEAN DEFAULT FALSE",
            "ALTER TABLE companies ADD COLUMN payfast_merchant_id VARCHAR",
            "ALTER TABLE companies ADD COLUMN payfast_merchant_key VARCHAR",
            "ALTER TABLE companies ADD COLUMN payfast_passphrase VARCHAR",
            # ── Site analytics (2026-07) ──────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS site_visits (
                id         SERIAL PRIMARY KEY,
                session_id VARCHAR,
                timestamp  TIMESTAMP DEFAULT NOW(),
                page       VARCHAR,
                referrer   VARCHAR,
                country    VARCHAR,
                city       VARCHAR,
                user_agent VARCHAR,
                ip_hash    VARCHAR
            )""",
            "CREATE INDEX IF NOT EXISTS ix_site_visits_timestamp ON site_visits (timestamp)",
            "CREATE INDEX IF NOT EXISTS ix_site_visits_session ON site_visits (session_id)",
            # ── Billing lifecycle columns (2026-07) ───────────────────────────
            "ALTER TABLE companies ADD COLUMN trial_warning_sent_at TIMESTAMP",
            "ALTER TABLE companies ADD COLUMN trial_expiry_email_sent_at TIMESTAMP",
            "ALTER TABLE companies ADD COLUMN overdue_reminders_enabled BOOLEAN DEFAULT TRUE",
            # ── Recurring invoices (2026-07) ──────────────────────────────────
            """CREATE TABLE IF NOT EXISTS recurring_invoices (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                client_name VARCHAR NOT NULL,
                client_email VARCHAR,
                description TEXT,
                amount FLOAT NOT NULL,
                vat_applicable BOOLEAN DEFAULT TRUE,
                currency VARCHAR DEFAULT 'ZAR',
                frequency VARCHAR NOT NULL,
                start_date TIMESTAMP NOT NULL,
                next_run_date TIMESTAMP,
                last_run_date TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                invoices_generated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_recurring_invoices_company ON recurring_invoices (company_id)",
            "CREATE INDEX IF NOT EXISTS ix_recurring_invoices_next_run ON recurring_invoices (next_run_date)",
            # ── Credit notes (2026-07) ────────────────────────────────────────
            """CREATE TABLE IF NOT EXISTS credit_notes (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                invoice_id INTEGER REFERENCES invoices(id),
                credit_note_number VARCHAR NOT NULL,
                client_name VARCHAR NOT NULL,
                description TEXT,
                amount FLOAT NOT NULL,
                vat_amount FLOAT DEFAULT 0,
                total_amount FLOAT NOT NULL,
                currency VARCHAR DEFAULT 'ZAR',
                issue_date TIMESTAMP DEFAULT NOW(),
                notes TEXT,
                journal_entry_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_credit_notes_company ON credit_notes (company_id)",
            # ── Deferred tax: per-asset SARS wear-and-tear rate override (2026-07-14) ──
            "ALTER TABLE fixed_assets ADD COLUMN wear_and_tear_rate FLOAT",
            # ── Pension / Medical aid on employees + payslips (2026-07) ──────────
            "ALTER TABLE employees ADD COLUMN pension_fund_employee_pct FLOAT DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN pension_fund_employer_pct FLOAT DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN pension_employee_fixed FLOAT DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN pension_employer_fixed FLOAT DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN medical_aid_employee FLOAT DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN medical_aid_employer FLOAT DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN medical_aid_dependants INTEGER DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN pension_employee FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN pension_employer FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN s11f_deduction FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN medical_aid_employee_ded FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN medical_aid_employer_con FLOAT DEFAULT 0",
            "ALTER TABLE payslips ADD COLUMN medical_tax_credit FLOAT DEFAULT 0",
            # ── SARS e@syFile fields on companies (2026-07) ───────────────────
            "ALTER TABLE companies ADD COLUMN paye_ref VARCHAR",
            "ALTER TABLE companies ADD COLUMN sdl_ref VARCHAR",
            "ALTER TABLE companies ADD COLUMN uif_ref VARCHAR",
            "ALTER TABLE companies ADD COLUMN sic7_code VARCHAR",
            "ALTER TABLE companies ADD COLUMN contact_name VARCHAR",
        ]:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()  # Reset connection so next statement starts fresh

        # Backfill: paid invoices missing paid_date get created_at as fallback.
        # Fixes revenue gap between dashboard and management/income-statement endpoints.
        try:
            conn.execute(text(
                "UPDATE invoices SET paid_date = created_at "
                "WHERE status = 'paid' AND paid_date IS NULL"
            ))
            conn.commit()
        except Exception:
            conn.rollback()


        # Backfill: generate portal_token for any invoices missing one
        try:
            import uuid as _uuid
            from database import Invoice as _Inv
            _db2 = SessionLocal()
            _missing = _db2.query(_Inv).filter(_Inv.portal_token == None).all()
            for _inv in _missing:
                _inv.portal_token = str(_uuid.uuid4()).replace("-", "")
                _inv.portal_token_created_at = datetime.utcnow()
            if _missing:
                _db2.commit()
            _db2.close()
        except Exception:
            pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
