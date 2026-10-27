import types, asyncio, datetime as dt, pytest
from fastapi import HTTPException
from tests.helpers import *
from database import FixedAsset, DepreciationEntry, Account, JournalLine, JournalEntry
import fixed_assets as FA


def U(co): return types.SimpleNamespace(company_id=co.id, id=1, role="owner")
def A(c): return asyncio.run(c)


def bal(co, code):
    acc = db.query(Account).filter_by(company_id=co.id, code=code).first()
    if not acc: return 0.0
    rows = db.query(JournalLine).join(JournalEntry, JournalLine.entry_id == JournalEntry.id).filter(
        JournalEntry.company_id == co.id, JournalLine.account_id == acc.id).all()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in rows), 2)


def months_ago(n):
    t = dt.datetime.utcnow(); y, m = t.year, t.month - n
    while m < 1: y, m = y - 1, m + 12
    return f"{y}-{m:02d}-01"


def mk(co, cost=12000, life=12, resid=0, when=None, **kw):
    return A(FA.create_asset(FA.AssetCreate(asset_name=kw.pop("name", "Thing"), category="Office Equipment", purchase_date=when or months_ago(3),
                                            cost=cost, residual_value=resid, useful_life_months=life, **kw), U(co), db))


def depr(co): return A(FA.run_depreciation_manual(U(co), db))


def test_catch_up_depreciation_is_correct_idempotent_and_hits_the_ledger():
    co = company("fa1", "general")
    a = mk(co)                                                          # R12,000 over 12 months, bought 3 months ago
    assert bal(co, "1500") == 12000
    r = depr(co)
    assert r["assets_depreciated"] == 4 and r["total_depreciation"] == 4000      # 3 past months + this one
    assert depr(co)["assets_depreciated"] == 0                                    # second run adds nothing
    assert bal(co, "5800") == 4000 and bal(co, "1510") == -4000 and unbal(co) == 0
    d = A(FA.list_assets(U(co), db))[0]
    assert d["accumulated_depreciation"] == 4000 and d["carrying_value"] == 8000


def test_residual_value_is_never_depreciated_below():
    co = company("fa2", "general")
    mk(co, cost=10000, life=3, resid=1000, when=months_ago(6))                    # 3000/mo but only 9000 depreciable
    depr(co)
    d = A(FA.list_assets(U(co), db))[0]
    assert d["accumulated_depreciation"] == 9000 and d["carrying_value"] == 1000
    assert depr(co)["total_depreciation"] == 0


def test_diminishing_balance_reduces_each_month():
    co = company("fa3", "general")
    mk(co, cost=12000, life=60, when=months_ago(1), depreciation_method="diminishing_balance", depreciation_rate=0.24)
    depr(co)
    first = round(12000 * 0.24 / 12, 2); second = round((12000 - first) * 0.24 / 12, 2)
    assert A(FA.list_assets(U(co), db))[0]["accumulated_depreciation"] == round(first + second, 2)


def test_disposal_gain_loss_writeoff_and_vat():
    co = company("fa4", "general")
    a = mk(co); depr(co)                                                          # CV 8,000
    r = A(FA.dispose_asset(a["id"], FA.DisposalData(disposal_date=dt.date.today().isoformat(), disposal_proceeds=9000), U(co), db))
    assert r["gain_loss"] == 1000 and bal(co, "1500") == 0 and bal(co, "1510") == 0 and bal(co, "4900") == -1000
    b = mk(co, name="B"); depr(co)
    r = A(FA.dispose_asset(b["id"], FA.DisposalData(disposal_date=dt.date.today().isoformat(), disposal_proceeds=5000), U(co), db))
    assert r["gain_loss"] == -3000 and bal(co, "6800") == 3000
    c = mk(co, name="C"); depr(co)
    r = A(FA.dispose_asset(c["id"], FA.DisposalData(disposal_date=dt.date.today().isoformat(), is_write_off=True), U(co), db))
    assert r["gain_loss"] == -8000 and r["status"] == "written_off"
    d = mk(co, name="D"); depr(co)                                                # VAT-inclusive sale: 11,500 = 10,000 + 1,500 VAT
    before = bal(co, "2100")
    r = A(FA.dispose_asset(d["id"], FA.DisposalData(disposal_date=dt.date.today().isoformat(), disposal_proceeds=11500, proceeds_include_vat=True), U(co), db))
    assert r["gain_loss"] == 2000 and bal(co, "2100") == before - 1500
    assert unbal(co) == 0


def test_disposal_and_creation_validation():
    co = company("fa5", "general")
    a = mk(co)
    today = dt.date.today().isoformat()
    bad = [lambda: A(FA.dispose_asset(a["id"], FA.DisposalData(disposal_date="2000-01-01", disposal_proceeds=1), U(co), db)),     # before purchase
           lambda: A(FA.dispose_asset(a["id"], FA.DisposalData(disposal_date=today, disposal_proceeds=-5), U(co), db)),
           lambda: A(FA.dispose_asset(a["id"], FA.DisposalData(disposal_date="not-a-date"), U(co), db)),
           lambda: mk(co, cost=0), lambda: mk(co, cost=-5), lambda: mk(co, life=0), lambda: mk(co, cost=1000, resid=2000),
           lambda: mk(co, when="31/12/2025"), lambda: mk(co, depreciation_method="diminishing_balance", depreciation_rate=1.5)]
    for i, f in enumerate(bad):
        with pytest.raises(HTTPException) as e: f()
        assert e.value.status_code == 400, (i, e.value.status_code)
    A(FA.dispose_asset(a["id"], FA.DisposalData(disposal_date=today, disposal_proceeds=100), U(co), db))
    with pytest.raises(HTTPException): A(FA.dispose_asset(a["id"], FA.DisposalData(disposal_date=today), U(co), db))          # twice
    with pytest.raises(HTTPException): A(FA.update_asset(a["id"], FA.AssetUpdate(location="x"), U(co), db))                   # edit disposed
    assert db.query(FixedAsset).filter_by(company_id=co.id).count() == 1


def test_disposal_charges_the_depreciation_that_was_never_run():
    co = company("fa6", "general")
    a = mk(co, when=months_ago(5))                                                # nobody ever ran depreciation
    r = A(FA.dispose_asset(a["id"], FA.DisposalData(disposal_date=dt.date.today().isoformat(), disposal_proceeds=0, is_write_off=True), U(co), db))
    assert r["accumulated_depreciation"] >= 5000, r["accumulated_depreciation"]  # at least the 5 full months before the disposal month
    assert bal(co, "1500") == 0 and bal(co, "1510") == 0 and unbal(co) == 0


def test_journal_failure_on_creation_does_not_leave_an_asset_without_its_entry(monkeypatch):
    import journal
    co = company("fa7", "general")
    monkeypatch.setattr(journal, "post_asset_acquisition", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(HTTPException): mk(co)
    assert db.query(FixedAsset).filter_by(company_id=co.id).count() == 0


def test_company_isolation():
    a = company("fa8a", "general"); b = company("fa8b", "general")
    x = mk(a)
    for f in (lambda: A(FA.update_asset(x["id"], FA.AssetUpdate(location="q"), U(b), db)),
              lambda: A(FA.dispose_asset(x["id"], FA.DisposalData(disposal_date=dt.date.today().isoformat()), U(b), db))):
        with pytest.raises(HTTPException) as e: f()
        assert e.value.status_code == 404
    assert A(FA.list_assets(U(b), db)) == [] and depr(b)["assets_depreciated"] == 0


def test_deferred_tax_numbers():
    co = company("fa9", "general")
    mk(co, cost=36000, life=60, when=months_ago(12), sars_category="Computers — desktops / laptops")   # SARS: 3 years
    depr(co)
    dtx = A(FA.get_deferred_tax(U(co), db))
    row = dtx["assets"][0]
    allowance = round(36000 / 36, 2)                                              # R1,000 a month for tax
    assert row["monthly_tax_allowance"] == allowance
    months = 12
    assert row["accumulated_allowance"] == months * 1000 and row["tax_base"] == 36000 - 12000
    cv = round(36000 - 13 * (36000 / 60), 2)                                       # 13 accounting charges (12 past months + this one)
    assert row["accounting_carrying_value"] == cv
    # tax base 24,000 vs CV 28,200 → DTL on the 4,200 difference at 27%
    assert row["deferred_tax_type"] == "DTL" and row["deferred_tax"] == round((cv - 24000) * 0.27, 2)
    assert dtx["summary"]["net_type"] == "DTL"
    A(FA.dispose_asset(A(FA.list_assets(U(co), db))[0]["id"], FA.DisposalData(disposal_date=dt.date.today().isoformat(), is_write_off=True), U(co), db))
    assert A(FA.get_deferred_tax(U(co), db))["assets"] == []                       # disposed assets drop out


# ───────── SARS special allowances (s12B / s12BA / s12C) ─────────
def _fa(cat, bought, cost=100000, **kw):
    return FixedAsset(asset_name="X", category="Plant & Machinery", sars_category=cat, purchase_date=bought, cost=cost,
                      residual_value=0, useful_life_months=60, accumulated_depreciation=0, **kw)

C12 = "Manufacturing plant — new/unused (s12C)"


def test_s12c_new_plant_is_40_20_20_20_by_tax_year_and_not_pro_rated():
    a = _fa(C12, dt.datetime(2026, 3, 15))                       # first used in the 2026/27 tax year
    at = lambda y, m, d: FA.tax_allowance_to_date(a, dt.datetime(y, m, d))
    assert at(2026, 3, 31) == 40000                              # whole first-year allowance although only 16 days in use
    assert at(2027, 2, 28) == 40000 and at(2027, 3, 1) == 60000 and at(2028, 3, 1) == 80000
    assert at(2029, 3, 1) == 100000 and at(2035, 1, 1) == 100000     # stops at 100%
    late = _fa(C12, dt.datetime(2026, 2, 28))                    # last day of the previous tax year -> already year 2 on 1 March
    assert FA.tax_allowance_to_date(late, dt.datetime(2026, 3, 1)) == 60000


def test_s12c_used_plant_is_20_percent_for_five_years():
    a = _fa("Manufacturing plant — used (s12C)", dt.datetime(2026, 6, 1))
    assert [FA.tax_allowance_to_date(a, dt.datetime(2026 + i, 6, 1)) for i in range(6)] == [20000, 40000, 60000, 80000, 100000, 100000]


def test_solar_100_percent_normally_and_125_percent_only_for_assets_first_used_1mar2023_to_28feb2025():
    k = "Solar PV panels (≤1 MW, s12BA)"
    inside, edge_in, edge_out, after = (_fa(k, dt.datetime(2024, 6, 1)), _fa(k, dt.datetime(2025, 2, 28)),
                                        _fa(k, dt.datetime(2025, 3, 1)), _fa(k, dt.datetime(2026, 5, 1)))
    now = dt.datetime(2026, 10, 24)
    assert FA.tax_allowance_to_date(inside, now) == 125000 and FA.tax_allowance_to_date(edge_in, now) == 125000
    assert FA.tax_allowance_to_date(edge_out, now) == 100000 and FA.tax_allowance_to_date(after, now) == 100000
    assert FA.tax_allowance_to_date(_fa(k, dt.datetime(2023, 2, 28)), now) == 100000     # before the window
    assert FA._calc_tax_base(inside, now)["tax_base"] == 0                               # the extra 25% never makes the tax base negative


def test_large_solar_and_wind_are_50_30_20_and_an_explicit_rate_still_wins():
    big = _fa("Solar PV panels (>1 MW, s12B)", dt.datetime(2026, 5, 1))
    assert [FA.tax_allowance_to_date(big, dt.datetime(2026 + i, 6, 1)) for i in range(4)] == [50000, 80000, 100000, 100000]
    wind = _fa("Wind energy equipment", dt.datetime(2026, 5, 1))
    assert FA.tax_allowance_to_date(wind, dt.datetime(2026, 10, 1)) == 50000
    over = _fa(C12, dt.datetime(2026, 3, 15), wear_and_tear_rate=10.0)
    assert FA.tax_allowance_to_date(over, dt.datetime(2026, 10, 1)) is None              # override -> monthly straight-line path


def test_register_deferred_tax_uses_the_schedule_and_matches_the_afs_note():
    import financial_statements as FS
    co = company("fa10", "general")
    a = mk(co, cost=100000, life=60, when="2025-06-01", sars_category=C12)
    A(FA.run_depreciation_manual(U(co), db))
    asset = db.query(FixedAsset).get(a["id"])
    when = dt.datetime(2026, 2, 28)
    row = FA._calc_tax_base(asset, when)
    assert row["rate_source"] == "sars_schedule" and row["allowance_schedule_pct"] == [40.0, 20.0, 20.0, 20.0]
    assert row["tax_base"] == 60000                                                      # 100,000 less the 40% first-year allowance
    # AFS as at the same date: carrying = 100,000 - 8 months x 1,666.67; (86,666.67 - 60,000) x 27% = 7,200
    assert abs(FS._deferred_tax_balance(db, co.id, when) - 7200.0) < 0.05


def test_building_allowances_are_5_percent_over_20_years_and_table_exposes_schedules():
    t = {c["name"]: c for c in A(FA.get_wear_tear_table())["categories"]}
    for k in ("Commercial buildings (s13quin)", "Industrial / Manufacturing buildings", "Residential rental property", "Hotel buildings"):
        assert t[k]["years"] == 20
    assert t[C12]["schedule_pct"] == [40.0, 20.0, 20.0, 20.0] and t["Wind energy equipment"]["schedule_pct"] == [50.0, 30.0, 20.0]
