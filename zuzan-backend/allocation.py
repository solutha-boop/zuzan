"""
allocation.py — smart allocation of bank statement lines to the chart of accounts.

The aim: a client who keeps their own books should only ever have to answer
"what was this?" once per merchant, and ZuZan does the rest.

How a suggestion is made, in order:
  1. Fingerprint the narrative. "POS Purchase ENGEN SANDTON 485462*1234 14 Nov"
     -> full key "engen sandton", merchant key "engen". Dates, card numbers,
     references and bank prefixes are noise; the merchant is the signal.
  2. The company's own memory (AllocationMemory), learned from every import:
       - a merchant that always went to one account          -> GREEN (auto)
       - a "mixed" merchant (Engen = fuel OR a cold drink)  -> AMBER, the account
         whose usual amount is closest to this one is pre-selected
       - an amount far outside what was seen before           -> AMBER
  3. A built-in South African merchant dictionary (Eskom, Vodacom, SANRAL,
     bank fees ...). Only the unambiguous bank-fee / interest lines are GREEN.
  4. Optional AI suggestion (Claude) for anything still unknown — always AMBER.
  5. Nothing found -> RED: the client decides, and ZuZan learns it.

Learning happens server-side when the import is posted (companies.import_bank_statement
calls learn_many), so what is learned is exactly what went into the books.

Endpoints (company-scoped):
  POST   /allocation/suggest        suggestions for a batch of bank lines
  POST   /allocation/learn          teach explicitly (e.g. from a future bank feed)
  GET    /allocation/memory         what ZuZan has learned
  DELETE /allocation/memory/{id}    forget one learned allocation
"""
import json
import logging
import math
import os
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from database import AllocationMemory, CategoryRule, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/allocation")

GREEN, AMBER, RED = "green", "amber", "red"

# ── 1. FINGERPRINTING ─────────────────────────────────────────────────────────

# Narrative prefixes SA banks put in front of the merchant/beneficiary (FNB, ABSA,
# Standard Bank, Nedbank, Capitec, Discovery, Investec, TymeBank). Longest first.
_PREFIXES = [
    r"recurring card purchase", r"pos (?:local |int(?:ernationa)?l )?purchase", r"card purchase",
    r"purchase", r"debit order", r"acb debit(?: external)?", r"magtape debit", r"debicheck(?: debit)?",
    r"(?:fnb )?app payment (?:to|from)", r"banking app payment(?: (?:to|from))?",
    r"internet (?:pmt|payment|banking)(?: (?:to|from|transfer))?", r"ib (?:payment|transfer) (?:to|from)",
    r"digital payment(?: (?:dt|cr))?", r"immediate (?:trf|transfer|payment)(?: (?:cr|dr))?",
    r"eft (?:credit|debit|payment)(?: (?:to|from))?", r"scheduled (?:pymt|payment) to", r"send money(?: to)?",
    r"cashsend", r"real ?time transfer(?: (?:to|from))?", r"credit transfer", r"(?:adt )?cash deposit",
    r"deposit", r"transfer (?:to|from)", r"payment (?:to|from|received)", r"pmt (?:to|from)",
    r"(?:cr|dr) transfer", r"inward (?:swift|eft)",
]
_PREFIX_RX = re.compile(r"^(?:" + "|".join(_PREFIXES) + r")\b\s*")
_TRANSFER_RX = re.compile(r"\b(?:payment|pmt|transfer|trf|send money|cashsend|eft|deposit)\b")
_MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
           "january", "february", "march", "april", "june", "july", "august", "september",
           "october", "november", "december"}
_DROP = {"pty", "ltd", "cc", "co", "za", "inc", "ref", "reference", "no", "nr", "the", "inv", "invoice"}
# First words too generic to identify a merchant on their own -> key uses two words.
_GENERIC = {"mr", "mrs", "ms", "dr", "my", "sa", "monthly", "service", "annual", "card", "cash", "debit",
            "credit", "online", "app", "int", "interest", "fee", "fees", "account", "acc", "bank", "pick",
            "city", "new", "south", "african", "sms", "notific", "dept", "department", "municipality"}


def fingerprint(description: str):
    """Return (full_key, merchant_key, display_name) for a bank narrative.

    full_key     first four meaningful words  ("engen quickshop sandton")
    merchant_key the merchant on its own       ("engen"); two words for person-to-person
                 payments and generic first words ("john smith", "monthly account")
    """
    raw = (description or "").lower()
    d = re.sub(r"\d+\*+\d+|x{3,}\d+|\*+\d+", " ", raw)          # card masks 485462*1234, xxxx1234
    d = re.sub(r"[^a-z0-9 ]+", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    is_transfer = bool(_TRANSFER_RX.search(d))
    for _ in range(3):                                             # "ACB DEBIT: EXTERNAL DEBIT ORDER ..."
        nd = _PREFIX_RX.sub("", d).strip()
        if nd == d or not nd:
            break
        d = nd
    words = [w for w in d.split()
             if len(w) >= 2 and not any(ch.isdigit() for ch in w) and w not in _MONTHS and w not in _DROP]
    if not words:                                                  # nothing left — fall back to the letters we had
        words = [w for w in re.sub(r"[^a-z ]+", " ", raw).split() if len(w) >= 2][:4] or ["unknown"]
    if (re.search(r"\bcash dep(?:osit)?\b", raw) and not re.match(r"^\W*(?:fee|fees|charge|charges)\b", raw)
            and words[:2] != ["cash", "deposit"]):
        # cash deposits are one "merchant", whatever the branch
        words = ["cash", "deposit"] + [w for w in words if w not in ("cash", "deposit", "dep")]
    full = " ".join(words[:4])
    if len(words) >= 2 and (is_transfer or words[0] in _GENERIC or len(words[0]) < 3):
        merchant = " ".join(words[:2])
    else:
        merchant = words[0]
    display = " ".join(w.capitalize() for w in words[:3])
    return full, merchant, display


# ── 3. SOUTH AFRICAN MERCHANT DICTIONARY ──────────────────────────────────────
# (phrases, txn_type, account, vat, sure, small)
#   phrases  matched as whole words against the full key (and the raw narrative for fees)
#   account  DEFAULT_COA "{code} - {name}" value
#   vat      typical VAT treatment (fuel is zero-rated in SA; bank fees and telecoms carry VAT)
#   sure     True only where a wrong answer is near-impossible -> may be GREEN
#   small    (threshold, account) — below the threshold the line is probably something else
#            bought at the same merchant (a cold drink at the garage shop)
_SUNDRY = "6370 - Sundry Expenses"
_DICTIONARY = [
    (("monthly account fee", "account fee", "service fee", "monthly fee", "admin fee", "notific", "sms notification",
      "cash handling", "card fee", "atm fee", "transaction fee", "bank charges", "statement fee",
      "management fee", "overdraft fee", "honouring fee", "unpaid fee", "cash dep fee", "byc debit"),
     "debit", "6360 - Bank Charges", True, True, None),
    (("debit interest", "interest on overdraft", "overdraft interest", "int on overdraft", "loan interest"),
     "debit", "7200 - Interest Expense", False, True, None),
    (("credit interest", "interest earned", "int pymt", "interest received", "interest capitalised", "interest"),
     "credit", "4210 - Interest Income", False, True, None),
    (("engen", "shell", "sasol", "caltex", "bp", "totalenergies", "astron", "puma energy", "puma"),
     "debit", "6510 - Fuel and Oil", False, False, (150.0, _SUNDRY)),
    (("vodacom", "mtn", "cell c", "cellc", "telkom mobile"),
     "debit", "6420 - Cellphone Expenses", True, False, None),
    (("telkom",), "debit", "6410 - Telephone Landline", True, False, None),
    (("afrihost", "webafrica", "rain", "vox", "cool ideas", "coolideas", "openserve", "vumatel", "frogfoot",
      "mweb", "axxess", "octotel", "starlink"),
     "debit", "6430 - Internet Fibre", True, False, None),
    (("eskom", "city power", "city of", "municipality", "joburg water", "johannesburg water",
      "ekurhuleni", "tshwane", "ethekwini", "nelson mandela bay", "prepaid electricity", "electricity",
      "prepaid elec"),
     "debit", "6220 - Electricity and Water", True, False, None),
    (("sanral", "e toll", "etoll", "n3tc", "bakwena", "trac", "toll"),
     "debit", "6540 - Toll Fees", True, False, None),
    (("flysafair", "airlink", "saa", "kulula", "lift airline", "flylift", "british airways", "emirates",
      "qatar airways", "cemair"),
     "debit", "6560 - Air Travel", True, False, None),
    (("booking com", "airbnb", "protea hotel", "city lodge", "tsogo", "southern sun", "sun international",
      "road lodge"),
     "debit", "6570 - Accommodation", True, False, None),
    (("santam", "outsurance", "hollard", "king price", "miway", "budget insurance", "dial direct",
      "first for women", "discovery insure", "old mutual insure", "mutual federal"),
     "debit", "6810 - Business Insurance", True, False, None),
    (("discovery health", "bonitas", "medshield", "fedhealth", "momentum health", "bestmed", "gems"),
     "debit", "6140 - Medical Aid Contributions", False, False, None),
    (("microsoft", "google workspace", "gsuite", "adobe", "zoom", "dropbox", "canva", "github", "slack",
      "openai", "anthropic", "aws", "amazon web services", "xero", "sage", "quickbooks", "intuit"),
     "debit", "6350 - Computer Software", True, False, None),
    (("facebook", "meta", "fb", "google ads", "googleads", "linkedin", "tiktok"),
     "debit", "6620 - Digital Marketing", True, False, None),
    (("cipc",), "debit", "6750 - CIPC Annual Return", False, False, None),
]


def _has_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def dictionary_lookup(full: str, raw: str, txn_type: str):
    """(account, vat, sure, small, phrase) for the first dictionary hit, else None."""
    norm_raw = re.sub(r"\s+", " ", re.sub(r"[^a-z ]+", " ", (raw or "").lower())).strip()
    # The bank's own charges: FNB prefixes them with "#", other banks start the line with FEE / FEES /
    # CHARGE ("FEE: CASH DEPOSIT", "CHARGES: IMMEDIATE PAYMENT").
    if txn_type == "debit" and ((raw or "").lstrip().startswith("#") or re.match(r"^(fee|fees|charge|charges)\b", norm_raw)):
        return "6360 - Bank Charges", True, True, None, "bank fee"
    for phrases, ttype, account, vat, sure, small in _DICTIONARY:
        if ttype != txn_type:
            continue
        for p in phrases:
            if _has_phrase(full, p) or (sure and _has_phrase(norm_raw, p)):
                return account, vat, sure, small, p
    return None


# ── 2. LEARNED MEMORY ─────────────────────────────────────────────────────────

def _is_allocation(category) -> bool:
    cat = (category or "").strip()
    return " - " in cat and cat.split(" - ", 1)[0].strip().isdigit()


def _bump(db: Session, company_id: int, level: str, key: str, txn_type: str, account: str,
          amount: Optional[float], has_vat: bool, times: int = 1):
    row = db.query(AllocationMemory).filter(
        AllocationMemory.company_id == company_id, AllocationMemory.key_level == level,
        AllocationMemory.key == key[:120], AllocationMemory.txn_type == txn_type,
        AllocationMemory.account == account[:160],
    ).first()
    if row is None:
        row = AllocationMemory(company_id=company_id, key_level=level, key=key[:120], txn_type=txn_type,
                               account=account[:160], count=0, amount_n=0, log_sum=0.0, vat_yes=0)
        db.add(row)
    row.count = (row.count or 0) + times
    if has_vat:
        row.vat_yes = (row.vat_yes or 0) + times
    if amount and amount > 0:
        row.amount_n = (row.amount_n or 0) + 1
        row.log_sum = (row.log_sum or 0.0) + math.log(amount)
        row.amount_min = amount if row.amount_min is None else min(row.amount_min, amount)
        row.amount_max = amount if row.amount_max is None else max(row.amount_max, amount)
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def learn(db: Session, company_id: int, description: str, amount, txn_type: str, account: str,
          has_vat: bool = False) -> bool:
    """Record one confirmed allocation. Ignores anything that isn't a '{code} - {name}' account."""
    if txn_type not in ("debit", "credit") or not _is_allocation(account):
        return False
    full, merchant, _ = fingerprint(description)
    if merchant == "unknown":                      # nothing recognisable to learn from (e.g. digits only)
        return False
    amt = float(amount or 0)
    _bump(db, company_id, "full", full, txn_type, account.strip(), amt, has_vat)
    _bump(db, company_id, "merchant", merchant, txn_type, account.strip(), amt, has_vat)
    return True


def learn_many(db: Session, company_id: int, items) -> int:
    """items: iterables of objects/dicts with description, amount, type, category, has_vat."""
    n = 0
    for it in items:
        g = (lambda k, d=None: it.get(k, d)) if isinstance(it, dict) else (lambda k, d=None: getattr(it, k, d))
        if learn(db, company_id, g("description", ""), g("amount", 0), g("type", ""),
                 g("category", "") or g("account", ""), bool(g("has_vat", False))):
            n += 1
    return n


def _seed_from_category_rules(db: Session, company_id: int):
    """One-off: carry the old keyword rules (category_rules.py) into the new memory so
    clients don't lose what they taught ZuZan before. Only rules that point at a real
    '{code} - {name}' account are carried; their amounts are unknown."""
    for r in db.query(CategoryRule).filter(CategoryRule.company_id == company_id).all():
        if not _is_allocation(r.category):
            continue
        types = ("debit", "credit") if r.txn_type not in ("debit", "credit") else (r.txn_type,)
        full, merchant, _ = fingerprint(r.keyword)
        for t in types:
            times = max(1, int(r.match_count or 1))
            _bump(db, company_id, "full", full, t, r.category.strip(), None, False, times)
            _bump(db, company_id, "merchant", merchant, t, r.category.strip(), None, False, times)


def _typical(row) -> Optional[float]:
    return math.exp(row.log_sum / row.amount_n) if row.amount_n else None


def _rand(x) -> str:
    return f"R{x:,.0f}".replace(",", " ")


def _plain(account: str) -> str:
    return account.split(" - ", 1)[1] if " - " in account else account


def decide(rows, amount: float, level: str, display: str):
    """Pick an account from this merchant's learned rows -> (account, confidence, reason, alternatives, vat)."""
    rows = [r for r in rows if (r.count or 0) > 0]
    if not rows:
        return None
    total = sum(r.count for r in rows)
    rows.sort(key=lambda r: -r.count)
    top = rows[0]
    alts = [r.account for r in rows[1:4]]
    consistent = len(rows) == 1 or (total >= 5 and top.count / total >= 0.9)

    if consistent:
        pick = top
        unusual = (pick.amount_n or 0) >= 3 and amount > 0 and pick.amount_max and pick.amount_min and (
            amount > pick.amount_max * 3 or amount < pick.amount_min / 3)
        if unusual:
            conf = AMBER
            reason = (f"{display} usually goes to {_plain(pick.account)}, but {_rand(amount)} is unusual "
                      f"(normally {_rand(pick.amount_min)} – {_rand(pick.amount_max)}). Please check.")
        elif level == "full" or total >= 2:
            conf = GREEN
            reason = f"You always put {display} in {_plain(pick.account)}."
        else:
            conf = AMBER
            reason = f"Last time a similar {display} line went to {_plain(pick.account)}."
    else:
        # Mixed merchant: the account whose typical amount is closest to this one wins.
        def dist(r):
            t = _typical(r)
            return abs(math.log(amount) - math.log(t)) if (t and amount > 0) else 99.0
        scored = sorted(rows, key=lambda r: (dist(r), -r.count))
        pick = scored[0]
        alts = [r.account for r in scored[1:4]]
        conf = AMBER
        t = _typical(pick)
        if t and dist(pick) < 99:
            reason = (f"{display} is sometimes {', sometimes '.join(_plain(r.account) for r in scored[:3])}. "
                      f"Picked {_plain(pick.account)} because {_rand(amount)} is close to your usual {_rand(t)}.")
        else:
            reason = f"{display} is sometimes {', sometimes '.join(_plain(r.account) for r in scored[:3])}."
    vat = (pick.vat_yes or 0) * 2 >= (pick.count or 1)
    return pick.account, conf, reason, alts, vat


# ── 4. OPTIONAL AI SUGGESTION ─────────────────────────────────────────────────

def _ai_suggest(unknown: list, accounts: List[str]) -> dict:
    """unknown: [{"k": idx, "text": full_key, "type": debit|credit, "amount": float}].
    Returns {idx: (account, vat)}. Silent no-op without ANTHROPIC_API_KEY or on any error.
    Only the cleaned fingerprint is sent (no card numbers, references or dates)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or not unknown or not accounts:
        return {}
    allowed = set(accounts)
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=key, timeout=20.0)
        lines = "\n".join(f'{u["k"]}|{u["type"]}|{u["amount"]:.2f}|{u["text"]}' for u in unknown[:80])
        prompt = (
            "You are an experienced South African bookkeeper allocating bank statement lines for a small business.\n"
            "Each line is: id|debit (money out) or credit (money in)|amount in ZAR|merchant or payee.\n"
            "Pick the single best account for each line from this chart of accounts (use the text exactly):\n"
            + "\n".join(accounts) +
            "\n\nAlso say whether the amount most likely includes 15% VAT (fuel, interest, salaries, medical aid "
            "and SARS payments do not). If you cannot tell what a line is, use null for the account.\n"
            'Reply with JSON only: [{"id": <id>, "account": "<account or null>", "vat": true|false}]\n\n'
            "Lines:\n" + lines
        )
        resp = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=2000,
                                      messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in resp.content)
        m = re.search(r"\[.*\]", text, re.S)
        out = {}
        for item in json.loads(m.group(0) if m else "[]"):
            acct = item.get("account")
            if isinstance(acct, str) and acct in allowed:
                out[int(item.get("id"))] = (acct, bool(item.get("vat")))
        return out
    except Exception as e:  # never let the AI layer break an import
        logger.warning(f"AI allocation suggestion skipped: {e}")
        return {}


# ── SUGGEST ───────────────────────────────────────────────────────────────────

class LineIn(BaseModel):
    id:          Optional[str] = None
    description: str
    amount:      float = 0.0
    type:        str                      # debit | credit


class SuggestRequest(BaseModel):
    transactions: List[LineIn]
    accounts:     Optional[List[str]] = None   # the client's live "{code} - {name}" list (DEFAULT_COA + custom)
    use_ai:       bool = True


def suggest_lines(db: Session, company_id: int, lines: List[LineIn], accounts: Optional[List[str]] = None,
                  use_ai: bool = True):
    allowed = set(accounts) if accounts else None
    ok = (lambda a: allowed is None or a in allowed)

    if not db.query(AllocationMemory.id).filter(AllocationMemory.company_id == company_id).first():
        _seed_from_category_rules(db, company_id)

    fps = [fingerprint(l.description) for l in lines]
    fulls = {f[0] for f in fps}
    merchants = {f[1] for f in fps}
    mem = {}
    if fulls or merchants:
        q = db.query(AllocationMemory).filter(AllocationMemory.company_id == company_id)
        for r in q.filter(AllocationMemory.key.in_(list(fulls | merchants))).all():
            if ok(r.account):
                mem.setdefault((r.key_level, r.key, r.txn_type), []).append(r)

    out, unknown = [], []
    for i, (l, (full, merchant, display)) in enumerate(zip(lines, fps)):
        amount = abs(float(l.amount or 0))
        s = {"id": l.id, "fingerprint": full, "group_key": f"{l.type}:{merchant}", "merchant": display,
             "account": None, "confidence": RED, "reason": "ZuZan hasn't seen this one before — what was it?",
             "alternatives": [], "has_vat": False, "source": "none"}
        picked = None
        full_rows = mem.get(("full", full, l.type))
        if full_rows:
            picked = decide(full_rows, amount, "full", display)
            # A full-key match that is still mixed may be settled better by the broader merchant history.
        if picked is None or picked[1] != GREEN:
            m_rows = mem.get(("merchant", merchant, l.type))
            if m_rows:
                alt = decide(m_rows, amount, "merchant", display)
                if picked is None or (alt and alt[1] == GREEN):
                    picked = alt
        if picked:
            s.update(account=picked[0], confidence=picked[1], reason=picked[2],
                     alternatives=picked[3], has_vat=picked[4], source="learned")
        else:
            hit = dictionary_lookup(full, l.description, l.type)
            if hit and ok(hit[0]):
                account, vat, sure, small, phrase = hit
                if small and amount and amount < small[0] and ok(small[1]):
                    s.update(account=small[1], alternatives=[account], has_vat=True, confidence=AMBER,
                             reason=f"{display} — a small amount like {_rand(amount)} is usually something from "
                                    f"the shop, not {_plain(account)}.", source="dictionary")
                else:
                    alts = [small[1]] if small and ok(small[1]) else []
                    s.update(account=account, has_vat=vat, alternatives=alts, source="dictionary",
                             confidence=GREEN if sure else AMBER,
                             reason=(f"Looks like {_plain(account).lower()}." if sure else
                                     f"{display} is usually {_plain(account)}. Tap to confirm."))
            else:
                unknown.append({"k": i, "text": full, "type": l.type, "amount": amount})
        out.append(s)

    if use_ai and unknown and accounts:
        for k, (account, vat) in _ai_suggest(unknown, accounts).items():
            if 0 <= k < len(out):
                out[k].update(account=account, has_vat=vat, confidence=AMBER, source="ai",
                              reason=f"ZuZan's best guess for {out[k]['merchant']} is {_plain(account)}. "
                                     f"Tap to confirm.")

    counts = {c: sum(1 for s in out if s["confidence"] == c) for c in (GREEN, AMBER, RED)}
    total = len(out)
    return {"suggestions": out,
            "summary": {**counts, "total": total,
                        "auto_rate": round(100 * counts[GREEN] / total) if total else 0}}


@router.post("/suggest")
def suggest(body: SuggestRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if len(body.transactions) > 5000:
        raise HTTPException(status_code=400, detail="Too many lines in one request (max 5000).")
    res = suggest_lines(db, current_user.company_id, body.transactions, body.accounts, body.use_ai)
    db.commit()     # persists the one-off seed from the old category rules, if it ran
    return res


class LearnItem(BaseModel):
    description: str
    amount:      float = 0.0
    type:        str
    account:     str
    has_vat:     bool = False


class LearnRequest(BaseModel):
    items: List[LearnItem]


@router.post("/learn")
def learn_endpoint(body: LearnRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    n = learn_many(db, current_user.company_id, [i.dict() for i in body.items])
    db.commit()
    return {"learned": n}


@router.get("/memory")
def list_memory(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(AllocationMemory)
              .filter(AllocationMemory.company_id == current_user.company_id,
                      AllocationMemory.key_level == "merchant")
              .order_by(AllocationMemory.count.desc()).all())
    return [{"id": r.id, "merchant": r.key, "type": r.txn_type, "account": r.account, "times": r.count,
             "typical_amount": round(_typical(r), 2) if _typical(r) else None,
             "amount_min": r.amount_min, "amount_max": r.amount_max} for r in rows]


@router.delete("/memory/{memory_id}")
def forget(memory_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Forget a learned merchant→account link (and the matching full-key rows)."""
    row = db.query(AllocationMemory).filter(AllocationMemory.id == memory_id,
                                            AllocationMemory.company_id == current_user.company_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    acct, ttype, merchant = row.account, row.txn_type, row.key
    db.delete(row)
    for r in db.query(AllocationMemory).filter(AllocationMemory.company_id == current_user.company_id,
                                               AllocationMemory.key_level == "full",
                                               AllocationMemory.txn_type == ttype,
                                               AllocationMemory.account == acct).all():
        if fingerprint(r.key)[1] == merchant:
            db.delete(r)
    db.commit()
    return {"forgotten": memory_id}
