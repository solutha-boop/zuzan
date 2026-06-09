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
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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
    plan=Column(Enum(PlanType),default=PlanType.starter)
    billing_cycle=Column(Enum(BillingCycle),default=BillingCycle.monthly)
    subscription_status=Column(Enum(SubscriptionStatus),default=SubscriptionStatus.trial)
    trial_ends=Column(DateTime); payroll_enabled=Column(Boolean,default=False)
    payroll_employees=Column(Integer,default=0)
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
    status=Column(Enum(InvoiceStatus),default=InvoiceStatus.draft)
    issue_date=Column(DateTime,default=datetime.utcnow); due_date=Column(DateTime)
    paid_date=Column(DateTime,nullable=True); notes=Column(Text)
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
    notes=Column(Text)
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

class Payment(Base):
    __tablename__ = "payments"
    id=Column(Integer,primary_key=True,index=True)
    company_id=Column(Integer,ForeignKey("companies.id"))
    amount=Column(Float,nullable=False); currency=Column(String,default="ZAR")
    plan=Column(String); billing_cycle=Column(String)
    payfast_id=Column(String,nullable=True); status=Column(String,default="pending")
    payment_method=Column(String); created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="payments")

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
        ]:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()  # Reset connection so next migration can run

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()