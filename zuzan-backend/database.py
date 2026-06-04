from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum

DATABASE_URL = "sqlite:///./zuzan.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
    position=Column(String); department=Column(String)
    gross_salary=Column(Float,nullable=False); start_date=Column(DateTime)
    bank_name=Column(String); bank_account=Column(String)
    is_active=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.utcnow)
    company=relationship("Company",back_populates="employees")
    payslips=relationship("Payslip",back_populates="employee")

class Payslip(Base):
    __tablename__ = "payslips"
    id=Column(Integer,primary_key=True,index=True)
    employee_id=Column(Integer,ForeignKey("employees.id"))
    period=Column(String); gross_salary=Column(Float); paye=Column(Float)
    uif_employee=Column(Float); uif_employer=Column(Float); sdl=Column(Float)
    net_pay=Column(Float); total_cost=Column(Float)
    generated_at=Column(DateTime,default=datetime.utcnow)
    employee=relationship("Employee",back_populates="payslips")

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
    # Migrate: add vat_amount to expenses if missing
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE expenses ADD COLUMN vat_amount FLOAT DEFAULT 0"))
            conn.commit()
        except Exception:
            pass  # Column already exists

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()