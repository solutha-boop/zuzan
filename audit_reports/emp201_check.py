"""EMP201 compliance check for ZuZan.
Usage: python emp201_check.py [path/to/zuzan.db] [YYYY-MM-DD as 'today']
Opens the DB read-only and prints JSON with per-company EMP201 totals for the prior month.
"""
import sqlite3, sys, json
from datetime import date

db = sys.argv[1] if len(sys.argv) > 1 else r"C:\Zuzan\zuzan-backend\zuzan.db"
today = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
period = f"{y:04d}-{m:02d}"

con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

companies = con.execute("""
    SELECT c.id, c.name, c.payroll_enabled,
           (SELECT COUNT(*) FROM employees e WHERE e.company_id=c.id AND e.is_active=1) AS active_emps
    FROM companies c ORDER BY c.id""").fetchall()

rows = {r["company_id"]: r for r in con.execute("""
    SELECT e.company_id,
           COUNT(DISTINCT p.employee_id)        AS employees,
           COALESCE(SUM(p.gross_salary),0)      AS gross,
           COALESCE(SUM(p.paye),0)              AS paye,
           COALESCE(SUM(p.uif_employee),0)      AS uif_ee,
           COALESCE(SUM(p.uif_employer),0)      AS uif_er,
           COALESCE(SUM(p.sdl),0)               AS sdl,
           SUM(CASE WHEN COALESCE(p.paye,0)=0 AND COALESCE(p.gross_salary,0)>0 THEN 1 ELSE 0 END) AS zero_paye_slips
    FROM payslips p JOIN employees e ON e.id=p.employee_id
    WHERE p.period=? GROUP BY e.company_id""", (period,))}

latest = {r["company_id"]: r["latest"] for r in con.execute("""
    SELECT e.company_id, MAX(p.period) AS latest
    FROM payslips p JOIN employees e ON e.id=p.employee_id GROUP BY e.company_id""")}

out = {"today": today.isoformat(), "period": period, "companies": []}
for c in companies:
    r = rows.get(c["id"])
    rec = {"company_id": c["id"], "name": c["name"], "payroll_enabled": bool(c["payroll_enabled"]),
           "active_employees": c["active_emps"], "latest_payslip_period": latest.get(c["id"]),
           "payroll_run": r is not None, "warnings": []}
    if r:
        tot = r["paye"] + r["uif_ee"] + r["uif_er"] + r["sdl"]
        rec.update(employees=r["employees"], gross=round(r["gross"], 2), paye=round(r["paye"], 2),
                   uif_employee=round(r["uif_ee"], 2), uif_employer=round(r["uif_er"], 2),
                   uif=round(r["uif_ee"] + r["uif_er"], 2), sdl=round(r["sdl"], 2), total_due=round(tot, 2))
        if r["paye"] == 0 and r["gross"] > 0:
            rec["warnings"].append("Zero PAYE on non-zero gross (company total) — possible tax calc bug")
        elif r["zero_paye_slips"]:
            rec["warnings"].append(f"{r['zero_paye_slips']} payslip(s) with zero PAYE on non-zero gross (may be below tax threshold)")
    else:
        relevant = c["payroll_enabled"] or c["active_emps"] > 0
        if relevant:
            rec["warnings"].append(f"No payslips for {period} — payroll not run")
    out["companies"].append(rec)

print(json.dumps(out, indent=2))
