"""allocation.py: merchant fingerprinting, learning, traffic-light suggestions, and the bank-import hooks."""
import asyncio, types, datetime as dt, uuid
from tests.helpers import *
from database import AllocationMemory, Account, AccountType, JournalEntry, JournalLine, Expense, CategoryRule
import allocation as A, companies as CO, journal as J

FUEL = "6510 - Fuel and Oil"
SUNDRY = "6370 - Sundry Expenses"
ACCOUNTS = [FUEL, SUNDRY, "6360 - Bank Charges", "6420 - Cellphone Expenses", "4120 - Sales - Services",
            "4210 - Interest Income", "3400 - Drawings", "2210 - Long-term Loan", "7200 - Interest Expense"]


def co():
    return company(f"alloc-{uuid.uuid4().hex[:8]}", "general")


def line(desc, amt, t="debit", i=None):
    return A.LineIn(id=i or desc, description=desc, amount=amt, type=t)


def sug(c, lines):
    return A.suggest_lines(db, c.id, lines, ACCOUNTS, use_ai=False)["suggestions"]


# ── fingerprinting ────────────────────────────────────────────────────────────

def test_fingerprint_strips_bank_noise():
    assert A.fingerprint("POS Purchase ENGEN SANDTON 485462*1234 14 Nov")[:2] == ("engen sandton", "engen")
    assert A.fingerprint("CARD PURCHASE ENGEN ROSEBANK 4587*2231 03 DEC")[1] == "engen"
    assert A.fingerprint("ACB DEBIT:EXTERNAL VODACOM 77412236")[1] == "vodacom"
    assert A.fingerprint("Recurring Card Purchase: Netflix.com 12/11")[1] == "netflix"
    # person-to-person payments keep two words so different Johns don't merge
    assert A.fingerprint("IB PAYMENT TO JOHN SMITH PLUMBING INV4432")[1] == "john smith"
    assert A.fingerprint("FNB App Payment To John Deere Parts")[1] == "john deere"
    assert A.fingerprint("#Monthly Account Fee")[1] == "monthly account"
    assert A.fingerprint("12345 6789")[0]          # never empty


# ── dictionary + traffic lights ───────────────────────────────────────────────

def test_dictionary_bank_fee_green_fuel_amber_and_small_amount_shop():
    c = co()
    s = {x["id"]: x for x in sug(c, [line("#Monthly Account Fee", 69), line("FEE: CASH DEPOSIT", 45),
                                     line("POS Purchase ENGEN SANDTON 4854*1234 14 Nov", 850, i="fuel"),
                                     line("POS Purchase ENGEN SANDTON 4854*1234 14 Nov", 32, i="drink"),
                                     line("Credit Interest", 12.5, "credit"),
                                     line("Mystery Traders 0021", 400)])}
    assert s["#Monthly Account Fee"]["confidence"] == "green" and s["#Monthly Account Fee"]["account"] == "6360 - Bank Charges"
    assert s["FEE: CASH DEPOSIT"]["account"] == "6360 - Bank Charges"
    assert s["fuel"]["account"] == FUEL and s["fuel"]["confidence"] == "amber" and s["fuel"]["has_vat"] is False
    assert s["drink"]["account"] == SUNDRY and FUEL in s["drink"]["alternatives"]
    assert s["Credit Interest"]["account"] == "4210 - Interest Income"
    assert s["Mystery Traders 0021"]["confidence"] == "red" and s["Mystery Traders 0021"]["account"] is None


def test_learns_after_one_confirmation_across_dates_and_cards():
    c = co()
    A.learn(db, c.id, "IB PAYMENT TO JABU PLUMBING INV 4432", 1800, "debit", "6260 - Repairs and Maintenance", True)
    db.commit()
    s = A.suggest_lines(db, c.id, [line("IB PAYMENT TO JABU PLUMBING INV 4519", 2100)], None, use_ai=False)["suggestions"][0]
    assert s["account"] == "6260 - Repairs and Maintenance" and s["confidence"] == "green" and s["has_vat"] is True


def test_merchant_level_needs_two_confirmations_for_green():
    c = co()
    A.learn(db, c.id, "CARD PURCHASE VODACOM SANDTON 4587*2231", 500, "debit", "6420 - Cellphone Expenses")
    db.commit()
    other_branch = line("CARD PURCHASE VODACOM MENLYN 4587*2231", 520)
    assert sug(c, [other_branch])[0]["confidence"] == "amber"
    A.learn(db, c.id, "CARD PURCHASE VODACOM ROSEBANK 4587*2231", 480, "debit", "6420 - Cellphone Expenses")
    db.commit()
    assert sug(c, [other_branch])[0]["confidence"] == "green"


def test_mixed_merchant_tie_broken_by_amount():
    c = co()
    for amt in (780, 920, 850):
        A.learn(db, c.id, f"POS Purchase ENGEN SANDTON 4854*1234", amt, "debit", FUEL)
    for amt in (28, 35, 41):
        A.learn(db, c.id, f"POS Purchase ENGEN SANDTON 4854*1234", amt, "debit", SUNDRY)
    db.commit()
    big, small = sug(c, [line("POS Purchase ENGEN SANDTON 9999*1111 01 Dec", 810, i="b"),
                         line("POS Purchase ENGEN SANDTON 9999*1111 01 Dec", 30, i="s")])
    assert big["account"] == FUEL and big["confidence"] == "amber" and SUNDRY in big["alternatives"]
    assert small["account"] == SUNDRY and small["confidence"] == "amber"
    assert "sometimes" in big["reason"]


def test_unusual_amount_downgrades_to_amber():
    c = co()
    for amt in (500, 510, 495):
        A.learn(db, c.id, "DEBIT ORDER VODACOM 7741", amt, "debit", "6420 - Cellphone Expenses")
    db.commit()
    assert sug(c, [line("DEBIT ORDER VODACOM 8812", 505)])[0]["confidence"] == "green"
    s = sug(c, [line("DEBIT ORDER VODACOM 8812", 9800)])[0]
    assert s["confidence"] == "amber" and "unusual" in s["reason"]


def test_deleted_account_is_not_suggested():
    c = co()
    A.learn(db, c.id, "Payment to Old Supplier", 100, "debit", "6999 - Gone Account")
    A.learn(db, c.id, "Payment to Old Supplier", 100, "debit", "6999 - Gone Account")
    db.commit()
    assert sug(c, [line("Payment to Old Supplier", 100)])[0]["account"] is None


def test_old_category_rules_are_carried_over():
    c = co()
    db.add(CategoryRule(company_id=c.id, keyword="pos purchase woolworths 4587*2231 14 nov",
                        category="6310 - Stationery and Office Supplies", txn_type="debit", match_count=3))
    db.add(CategoryRule(company_id=c.id, keyword="something", category="Travel", txn_type="debit"))  # bare label: ignored
    db.commit()
    s = A.suggest_lines(db, c.id, [line("POS PURCHASE WOOLWORTHS 1111*2222 02 DEC", 250)], None, use_ai=False)
    assert s["suggestions"][0]["account"] == "6310 - Stationery and Office Supplies"
    assert s["suggestions"][0]["confidence"] == "green"


# ── bank import: posting + learning ──────────────────────────────────────────

def _import(c, txns):
    user = types.SimpleNamespace(company_id=c.id, id=1, role="owner")
    return asyncio.run(CO.import_bank_statement(CO.BankImportRequest(bank="fnb", transactions=txns), current_user=user, db=db))


def _bal(c, code):
    a = db.query(Account).filter_by(company_id=c.id, code=code).first()
    return (a, sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id))) if a else (None, 0)


def test_import_learns_and_routes_balance_sheet_and_income_accounts():
    c = co()
    T = CO.BankTransaction
    today = dt.date.today().isoformat()
    r = _import(c, [
        T(date=today, description="POS Purchase ENGEN SANDTON 4854*1234", amount=850, type="debit", category=FUEL),
        T(date=today, description="IB PAYMENT TO OWNER JOHN", amount=5000, type="debit", category="3400 - Drawings"),
        T(date=today, description="NEDBANK LOAN REPAYMENT", amount=3000, type="debit", category="2210 - Long-term Loan"),
        T(date=today, description="CREDIT INTEREST", amount=12.5, type="credit", category="4210 - Interest Income"),
    ])
    assert r["expenses_created"] == 1 and r["transfers_recorded"] == 2 and r["credits_recorded"] == 1, r
    assert r["learned"] == 4
    # drawings / loan are journals, not expenses
    assert db.query(Expense).filter_by(company_id=c.id).count() == 1
    acct, bal = _bal(c, "3400")
    assert acct.type == AccountType.equity and abs(bal - 5000) < 0.01
    # 2210 in the picker is a loan; the ledger's 2210 is UIF Payable -> must not land there
    uif, uif_bal = _bal(c, "2210")
    assert abs(uif_bal) < 0.01
    loan, loan_bal = _bal(c, "2410")
    assert loan.type == AccountType.liability and abs(loan_bal - 3000) < 0.01
    # allocated income goes to the chosen revenue account, not 4000
    inc, inc_bal = _bal(c, "4210")
    assert inc.type == AccountType.revenue and abs(inc_bal + 12.5) < 0.01
    assert unbal(c) == 0
    # re-import is a duplicate for the transfers too
    r2 = _import(c, [T(date=today, description="IB PAYMENT TO OWNER JOHN", amount=5000, type="debit", category="3400 - Drawings")])
    assert r2["transfers_skipped"] == 1 and r2["transfers_recorded"] == 0
    # and next month's statement is now recognised
    s = sug(c, [line("IB PAYMENT TO OWNER JOHN", 5000)])[0]
    assert s["account"] == "3400 - Drawings" and s["confidence"] == "green"


def test_cost_of_sales_pick_creates_cogs_account():
    c = co()
    T = CO.BankTransaction
    _import(c, [T(date=dt.date.today().isoformat(), description="MAKRO STOCK", amount=1150, type="debit",
                  category="5010 - Purchases")])
    acct = db.query(Account).filter_by(company_id=c.id, code="5010").first()
    assert acct is not None and acct.type == AccountType.cogs
