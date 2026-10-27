import types, asyncio, datetime as dt
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import Invoice, InvoiceStatus, Expense, AbsaTransaction
import bank_direct_feeds as BF


def _inv(co, no, total, status=InvoiceStatus.sent, cur="ZAR", rate=1.0, paid=None, due=True, client="Acme Trading"):
    now = dt.datetime.utcnow()
    i = Invoice(company_id=co.id, invoice_number=no, client_name=client, amount=total, vat_amount=0, total_amount=total, status=status,
                currency=cur, exchange_rate=rate, paid_amount_zar=paid, issue_date=now, due_date=now if due else None)
    db.add(i); db.commit(); db.refresh(i); return i


def test_direct_feed_automatch_needs_the_amount_to_agree():
    co = company("bfC", "general")
    inv = _inv(co, "P1", 1000, client="Zeta Corporation")
    # same client name in the narrative but a very different amount: not a match any more
    assert BF._auto_match(100, "ZETA CORPORATION EFT", co.id, db)[0] is None
    assert BF._auto_match(1000, "ZETA CORPORATION EFT", co.id, db)[0] == inv.id
    part = _inv(co, "P2", 2000, InvoiceStatus.partial, paid=800, client="Beta Ltd")
    assert BF._auto_match(1200, "BETA LTD", co.id, db)[0] == part.id


def test_a_transaction_can_only_be_matched_to_the_companys_own_invoice():
    a = company("bfD1", "general"); b = company("bfD2", "general")
    inv_a = _inv(a, "A1", 500); mine = _inv(b, "B1", 500)
    with pytest.raises(HTTPException) as e:
        BF.check_match_owner(db, b.id, invoice_id=inv_a.id)
    assert e.value.status_code == 404
    BF.check_match_owner(db, b.id, invoice_id=mine.id)          # own invoice is fine


def test_same_amount_for_a_different_client_is_not_auto_matched():
    co = company("bfD", "general")
    inv = _inv(co, "Q1", 5000, client="Gamma Foods")
    assert BF._auto_match(5000, "SOME OTHER PAYER 123", co.id, db)[0] is None      # amount alone is coincidence
    assert BF._auto_match(5000, "GAMMA FOODS EFT", co.id, db)[0] == inv.id
    assert BF._auto_match(5000, "PAYMENT Q1", co.id, db)[0] == inv.id              # invoice number is enough


def test_part_deposits_match_by_invoice_number_or_client_and_ties_are_not_guessed():
    co = company("bfE", "general")
    inv = _inv(co, "PD1", 10000, client="Delta Steel")
    assert BF._auto_match(4000, "DEP PD1", co.id, db)[0] == inv.id                 # invoice number named
    assert BF._auto_match(4000, "DELTA STEEL DEPOSIT", co.id, db)[0] is None       # client name alone is not enough for a part amount
    assert BF._auto_match(4000, "UNKNOWN PAYER", co.id, db)[0] is None             # no evidence
    assert BF._auto_match(12000, "DEP PD1", co.id, db)[0] is None                  # more than is owed
    _inv(co, "PD2", 10000, client="Delta Steel")
    assert BF._auto_match(4000, "DEP PD1 PD2", co.id, db)[0] is None               # names two invoices equally: ambiguous
    assert BF._auto_match(4000, "DEP PD2", co.id, db)[0] is not None
