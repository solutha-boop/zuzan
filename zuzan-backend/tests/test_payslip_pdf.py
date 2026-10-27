import io, types, zipfile, asyncio
import pytest
from fastapi import HTTPException
from tests.helpers import *
import payroll as P


def _body(resp):
    async def collect():
        return b"".join([c async for c in resp.body_iterator])
    return asyncio.run(collect())


def _setup(name):
    co = company(name, "general")
    e = emp(co, "E1", 25000)
    run(co, period="2026-09")
    return co, e, slip(e)


def test_payslip_pdf_is_a_real_pdf_with_the_same_numbers_as_html():
    co, e, s = _setup("pdfco")
    pdf = P._payslip_pdf(s, e, "Pdf Co (Pty) Ltd")
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1500
    html = P._payslip_html(s, e, "Pdf Co (Pty) Ltd")
    # HTML still shows every row and the net pay
    for needle in ("Basic Salary", "PAYE (Income Tax)", "Total Deductions", P._fmt_zar(s.net_pay or 0)):
        assert needle in html, needle
    # PDF text (when pypdf is available) carries the same figures
    try:
        from pypdf import PdfReader
    except Exception:
        return
    text = " ".join(pg.extract_text() for pg in PdfReader(io.BytesIO(pdf)).pages)
    assert P._pdf_zar(s.net_pay) in text and "PAYE (Income Tax)" in text and "Total Deductions" in text


def test_download_all_zip_contains_pdfs_and_html_is_still_available():
    co, e, s = _setup("pdfzip")
    user = types.SimpleNamespace(company_id=co.id, id=1)
    r = P.download_all_payslips(s.period, format="pdf", db=db, current_user=user)
    names = zipfile.ZipFile(io.BytesIO(_body(r))).namelist()
    assert names and all(n.endswith(".pdf") for n in names), names
    r2 = P.download_all_payslips(s.period, format="html", db=db, current_user=user)
    names2 = zipfile.ZipFile(io.BytesIO(_body(r2))).namelist()
    assert all(n.endswith(".html") for n in names2)


def test_single_employee_pdf_endpoint_and_company_scoping():
    co, e, s = _setup("pdfone")
    user = types.SimpleNamespace(company_id=co.id, id=1)
    r = P.download_employee_payslip_pdf(s.period, e.id, db=db, current_user=user)
    assert r.media_type == "application/pdf" and r.body[:5] == b"%PDF-"
    assert "attachment" in r.headers["content-disposition"]
    other = company("pdfother", "general")
    with pytest.raises(HTTPException) as ex:
        P.download_employee_payslip_pdf(s.period, e.id, db=db, current_user=types.SimpleNamespace(company_id=other.id, id=1))
    assert ex.value.status_code == 404
    with pytest.raises(HTTPException) as ex2:
        P.download_employee_payslip_pdf("2020-01", e.id, db=db, current_user=user)
    assert ex2.value.status_code == 404


def test_unusual_characters_do_not_break_the_pdf():
    co, e, s = _setup("pdfodd")
    e.first_name = "Zoë <&> Ngcobo"; db.commit()
    assert P._payslip_pdf(s, e, "Müller & Sons <Pty>")[:5] == b"%PDF-"
