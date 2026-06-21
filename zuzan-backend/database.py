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
    sent="sent"
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
    cipc_registration_date=Column(DateTime,nullable=True)   # Company anniversary for CIPC AR reminder
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
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="invoices")

class Expense(Base):
    __tablename__ = "expenses"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    vendor=Column(String,nullable=False); description=Column(Text)
    amount=Column(Float,nullable=False); vat_amount=Column(Float,default=0); category=Column(String)
    expense_date=Column(DateTime,default=datetime.utcnow)
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
    gross_salary=Column(Float,nullable=False); start_date=Column(DateTime)
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

def init_db():
    Base.metadata.create_all(bind=engine)
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
        ]:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()  # Reset connection so next statement starts fresh


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
