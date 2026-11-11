"""
One-off check for the fixed-asset import bug of 2026-11-09 -> 2026-11-11 (audit item: useful life x12).

Between commit 33cbd44 (9 Nov 2026) and the 11 Nov fix, a CSV/Excel fixed-asset import read any
"months" useful-life column (e.g. "Useful Life Months", "life (months)") as YEARS, so a 60-month life
was saved as 720 months. Depreciation for those assets is understated and the AFS overstate PPE.

Run in the backend Render Shell:
    python check_fixed_asset_useful_life.py                 (dry run - lists suspects, changes nothing)
    python check_fixed_asset_useful_life.py --apply 12 15   (divides useful_life_months by 12 for asset ids 12 and 15)

A suspect is an asset whose useful life is more than 40 years (480 months), or a life that is an exact
multiple of 12 above 20 years. Review each one against the original import file before applying:
only pass the ids you have confirmed. After fixing, re-run depreciation for the affected periods so the
accumulated depreciation catches up.
"""
import sys
from database import SessionLocal, FixedAsset

args = sys.argv[1:]
APPLY = "--apply" in args
ids = {int(a) for a in args if a.isdigit()}

db = SessionLocal()
suspects = (db.query(FixedAsset)
              .filter(FixedAsset.useful_life_months > 240)
              .order_by(FixedAsset.company_id, FixedAsset.id).all())
print(f"{len(suspects)} asset(s) with a useful life over 20 years:")
for a in suspects:
    flag = "LIKELY x12" if a.useful_life_months > 480 or a.useful_life_months % 12 == 0 else "check"
    print(f"  id {a.id:>6}  company {a.company_id:>5}  {a.asset_name[:40]:<40}  "
          f"{a.useful_life_months} months ({a.useful_life_months/12:.1f} yrs) -> "
          f"{a.useful_life_months // 12} months if fixed  [{flag}]")

if APPLY:
    if not ids:
        print("Pass the asset ids to fix after --apply, e.g. --apply 12 15")
    else:
        fixed = 0
        for a in suspects:
            if a.id in ids:
                a.useful_life_months = max(1, a.useful_life_months // 12)
                fixed += 1
        db.commit()
        print(f"Fixed {fixed} asset(s). Re-run depreciation for the affected periods.")
else:
    print("Dry run only. Re-run with --apply <ids> after checking each asset.")
db.close()
