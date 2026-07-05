"""
ZuZan Email Service — uses Resend API (https://resend.com)
Requires env var: RESEND_API_KEY
Optional env vars: FROM_EMAIL, FRONTEND_URL, BACKEND_URL, SUPPORT_EMAIL
"""

import os
import logging
import httpx

logger = logging.getLogger("zuzan.email")

RESEND_API_KEY  = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL         = os.environ.get("FROM_EMAIL",         "ZuZan <Zuzan@solutha.co.za>")
FROM_SUPPORT_EMAIL = os.environ.get("FROM_SUPPORT_EMAIL", "ZuZan <support@solutha.co.za>")
FRONTEND_URL       = os.environ.get("FRONTEND_URL",       "https://zuzan-app.onrender.com")
BACKEND_URL        = os.environ.get("BACKEND_URL",        "https://zuzan-backend.onrender.com")
SUPPORT_EMAIL      = os.environ.get("SUPPORT_EMAIL",      "support@solutha.co.za")

PLAN_DETAILS = {
    "starter": {
        "name": "Starter",
        "price_monthly": 399,
        "price_annual":  3990,
        "features": [
            "2 users",
            "20 invoices/month",
            "Invoicing & Quotes",
            "Expense Tracking",
            "Payroll (PAYE/UIF/SDL)",
            "Basic P&L Report",
            "Email Support",
        ],
    },
    "professional": {
        "name": "Professional",
        "price_monthly": 899,
        "price_annual":  8990,
        "features": [
            "5 users",
            "50 invoices/month",
            "Everything in Starter",
            "Double-entry General Ledger",
            "Trial Balance & Journal Viewer",
            "Balance Sheet Reconciliation",
            "Advanced Reports",
            "Priority Support",
        ],
    },
    "business": {
        "name": "Business",
        "price_monthly": 1499,
        "price_annual":  14990,
        "features": [
            "20 users",
            "Unlimited Invoices",
            "Everything in Professional",
            "Budgeting vs Actuals",
            "Cash Flow Forecast",
            "Department Budgets",
            "API Access",
            "Dedicated Account Manager",
        ],
    },
}

# ── Shared CSS / layout ────────────────────────────────────────────────────────
def _opt_out_line(footer_email: str, transactional: bool = False) -> str:
    """Return an ECTA-compliant opt-out footer line."""
    if not footer_email:
        return ""
    import urllib.parse
    subject = urllib.parse.quote(f"Opt out of Zuzan emails: {footer_email}")
    unsubscribe_url = f"mailto:{SUPPORT_EMAIL}?subject={subject}"
    if transactional:
        return (
            f"<p style='color:#bbb;font-size:11px;margin:8px 0 0;'>"
            f"This is a service email sent because an action was performed on your account or on your behalf. "
            f"To stop receiving service emails, "
            f"<a href='{unsubscribe_url}' style='color:#C8401A;'>opt out here</a>."
            f"</p>"
        )
    return (
        f"<p style='color:#bbb;font-size:11px;margin:8px 0 0;'>"
        f"You received this email because you signed up for Zuzan or a Zuzan user added your address. "
        f"To opt out of future emails, "
        f"<a href='{unsubscribe_url}' style='color:#C8401A;'>click here</a>."
        f"</p>"
    )


def _wrap(body: str, footer_email: str = "", transactional: bool = False) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f0ece6;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#FAF7F2;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <!-- Header -->
    <div style="background:#C8401A;padding:24px 32px;text-align:center;">
      <h1 style="color:#fff;margin:0;font-size:28px;letter-spacing:1px;">ZuZan</h1>
      <p style="color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;">SA Bookkeeping &amp; Payroll</p>
    </div>
    <!-- Body -->
    <div style="padding:32px;">
      {body}
    </div>
    <!-- Footer -->
    <div style="background:#f0ece6;padding:20px 32px;text-align:center;">
      <p style="color:#aaa;font-size:12px;margin:0;">ZuZan — Built for South African SMEs</p>
      {"<p style='color:#aaa;font-size:12px;margin:4px 0 0;'>This email was sent to " + footer_email + "</p>" if footer_email else ""}
      <p style="color:#aaa;font-size:12px;margin:4px 0 0;">
        Need help? Chat with the <strong>AI Assistant</strong> in the app or email
        <a href="mailto:{SUPPORT_EMAIL}" style="color:#C8401A;">{SUPPORT_EMAIL}</a>
      </p>
      {_opt_out_line(footer_email, transactional)}
    </div>
  </div>
</body>
</html>"""


def _btn(text: str, url: str) -> str:
    return f'<div style="text-align:center;margin:28px 0;"><a href="{url}" style="background:#C8401A;color:#fff;padding:14px 36px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px;">{text}</a></div>'


# ── Core send ──────────────────────────────────────────────────────────────────
def send_email(to: str, subject: str, html: str, from_email: str = None) -> bool:
    if not RESEND_API_KEY:
        logger.warning(f"[EMAIL skipped — no RESEND_API_KEY] To: {to} | {subject}")
        return False
    sender = from_email or FROM_EMAIL
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"from": sender, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info(f"Email sent → {to} | {subject} | from: {sender}")
            return True
        logger.error(f"Resend {resp.status_code}: {resp.text}")
        return False
    except Exception as exc:
        logger.error(f"Email send failed: {exc}")
        return False


# ── 1. Email verification ──────────────────────────────────────────────────────
def send_verification_email(first_name: str, email: str, token: str):
    verify_url = f"{BACKEND_URL}/auth/verify-email/{token}"
    body = f"""
      <h2 style="color:#1a1a1a;margin:0 0 12px;">Hi {first_name}, please verify your email</h2>
      <p style="color:#555;line-height:1.7;margin:0 0 8px;">
        You're almost ready to use ZuZan. Click the button below to confirm your email address.
      </p>
      <p style="color:#888;font-size:13px;margin:0 0 24px;">This link expires in 24 hours.</p>
      {_btn("Verify Email Address", verify_url)}
      <p style="color:#aaa;font-size:12px;text-align:center;">
        If you didn't create a ZuZan account, you can safely ignore this email.
      </p>
    """
    send_email(email, "Verify your ZuZan email address", _wrap(body, email, transactional=True))


# ── 2. Welcome / subscription confirmation ─────────────────────────────────────
def send_welcome_email(
    first_name: str,
    email: str,
    company_name: str,
    plan: str,
    billing_cycle: str,
    trial_ends_str: str,
):
    info  = PLAN_DETAILS.get(plan, PLAN_DETAILS["starter"])
    price = info.get(f"price_{billing_cycle}", info["price_monthly"])
    cycle_label   = "per month" if billing_cycle == "monthly" else "per year"
    features_html = "".join(
        f"<li style='padding:5px 0;color:#444;'>✓ &nbsp;{f}</li>"
        for f in info["features"]
    )

    body = f"""
      <h2 style="color:#1a1a1a;margin:0 0 8px;">Welcome to ZuZan, {first_name}!</h2>
      <p style="color:#555;line-height:1.7;margin:0 0 24px;">
        Your account for <strong>{company_name}</strong> is set up and ready to go.
        Here are your subscription details:
      </p>

      <!-- Plan card -->
      <div style="background:#fff;border-radius:8px;padding:24px;border:1px solid #e0d9d0;margin-bottom:24px;">
        <p style="color:#C8401A;font-weight:bold;font-size:13px;margin:0 0 4px;text-transform:uppercase;letter-spacing:.5px;">{info['name']} Plan</p>
        <p style="font-size:26px;font-weight:bold;color:#1a1a1a;margin:0 0 4px;">
          R{price:,} <span style="font-size:14px;color:#888;font-weight:normal;">{cycle_label}</span>
        </p>
        <p style="color:#C8401A;font-size:13px;margin:0 0 16px;">
          ✨ 14-day free trial — no charge until {trial_ends_str}
        </p>
        <ul style="margin:0;padding-left:0;list-style:none;border-top:1px solid #f0ece6;padding-top:12px;">
          {features_html}
        </ul>
      </div>

      <!-- Support box -->
      <div style="background:#fff8f6;border-radius:8px;padding:20px;border-left:4px solid #C8401A;margin-bottom:24px;">
        <p style="color:#C8401A;font-weight:bold;margin:0 0 8px;">💬 &nbsp;Need Help?</p>
        <p style="color:#555;line-height:1.7;margin:0 0 8px;">
          Your <strong>first point of contact</strong> is the ZuZan AI Assistant — tap the 🤖 button
          in the app for instant answers on VAT, PAYE, UIF, invoicing, and more.
        </p>
        <p style="color:#555;line-height:1.7;margin:0;">
          For account or billing queries, email us at
          <a href="mailto:{SUPPORT_EMAIL}" style="color:#C8401A;">{SUPPORT_EMAIL}</a>
        </p>
      </div>

      {_btn("Open ZuZan", FRONTEND_URL)}
    """
    send_email(
        email,
        f"Welcome to ZuZan — Your {info['name']} plan is active",
        _wrap(body, email),  # welcome = marketing, no transactional flag
        from_email=FROM_SUPPORT_EMAIL,
    )


# ── 3. Admin new-signup notification ──────────────────────────────────────────
def send_admin_signup_notification(
    admin_email: str,
    first_name: str,
    last_name: str,
    user_email: str,
    company_name: str,
    plan: str,
    billing_cycle: str,
):
    import os
    dashboard_url = f"{BACKEND_URL}/admin"
    info = PLAN_DETAILS.get(plan, PLAN_DETAILS["starter"])
    body = f"""
      <h2 style="color:#1a1a1a;margin:0 0 16px;">🎉 New ZuZan Sign-Up</h2>
      <div style="background:#fff;border-radius:8px;padding:20px;border:1px solid #e0d9d0;margin-bottom:20px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr><td style="padding:8px 0;color:#888;width:140px;">Name</td><td style="padding:8px 0;color:#1a1a1a;font-weight:bold;">{first_name} {last_name}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">Email</td><td style="padding:8px 0;"><a href="mailto:{user_email}" style="color:#C8401A;">{user_email}</a></td></tr>
          <tr><td style="padding:8px 0;color:#888;">Company</td><td style="padding:8px 0;color:#1a1a1a;">{company_name}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">Plan</td><td style="padding:8px 0;color:#C8401A;font-weight:bold;">{info['name']} ({billing_cycle})</td></tr>
        </table>
      </div>
      {_btn("View Admin Dashboard", dashboard_url)}
    """
    send_email(admin_email, f"New sign-up: {company_name} ({info['name']} plan)", _wrap(body))


# ── 4. Password reset ──────────────────────────────────────────────────────────
def send_password_reset_email(first_name: str, email: str, reset_code: str):
    body = f"""
      <h2 style="color:#1a1a1a;margin:0 0 12px;">Password Reset Request</h2>
      <p style="color:#555;line-height:1.7;margin:0 0 24px;">
        Hi {first_name}, use the code below to reset your ZuZan password.
        It expires in <strong>30 minutes</strong>.
      </p>
      <div style="text-align:center;margin:0 0 28px;">
        <div style="display:inline-block;background:#1a1a1a;color:#fff;font-size:32px;
                    font-weight:bold;letter-spacing:10px;padding:20px 40px;
                    border-radius:8px;font-family:monospace;">
          {reset_code}
        </div>
      </div>
      <p style="color:#888;font-size:13px;text-align:center;">
        Enter this code in the ZuZan app to set a new password.<br>
        If you didn't request a reset, you can safely ignore this email.
      </p>
    """
    send_email(email, "Your ZuZan password reset code", _wrap(body, email, transactional=True))


# ── 5. Purchase Order to supplier ─────────────────────────────────────────────
def send_po_email(supplier_email: str, supplier_name: str, po: dict, company_name: str):
    """Send a formatted PO to a supplier."""
    items_rows = "".join(
        f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #E8E0D5;">{it['description']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E8E0D5;text-align:right;">{it['quantity']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E8E0D5;text-align:right;">R{it['unit_price']:.2f}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E8E0D5;text-align:right;font-weight:600;">R{it['total']:.2f}</td>
        </tr>"""
        for it in po.get("items", [])
    )
    delivery = f"<p style='color:#555;margin:0 0 8px;'><strong>Delivery date:</strong> {po['delivery_date']}</p>" if po.get("delivery_date") else ""
    notes = f"<p style='color:#555;margin:16px 0 0;'><strong>Notes:</strong> {po['notes']}</p>" if po.get("notes") else ""
    vat_row = f"<tr><td colspan='3' style='padding:6px 12px;text-align:right;color:#555;'>VAT (15%):</td><td style='padding:6px 12px;text-align:right;color:#555;'>R{po['vat_amount']:.2f}</td></tr>" if po.get("vat_amount", 0) > 0 else ""
    body = f"""
      <h2 style="color:#1a1a1a;margin:0 0 4px;">Purchase Order — {po['po_number']}</h2>
      <p style="color:#888;margin:0 0 20px;font-size:13px;">From <strong>{company_name}</strong></p>
      <p style="color:#555;margin:0 0 8px;">Dear <strong>{supplier_name}</strong>,</p>
      <p style="color:#555;margin:0 0 20px;">Please find our purchase order below. Kindly confirm receipt and expected delivery.</p>
      {delivery}
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px;">
        <thead>
          <tr style="background:#f0ece6;">
            <th style="padding:10px 12px;text-align:left;font-weight:600;color:#1a1a1a;">Description</th>
            <th style="padding:10px 12px;text-align:right;font-weight:600;color:#1a1a1a;">Qty</th>
            <th style="padding:10px 12px;text-align:right;font-weight:600;color:#1a1a1a;">Unit Price</th>
            <th style="padding:10px 12px;text-align:right;font-weight:600;color:#1a1a1a;">Total</th>
          </tr>
        </thead>
        <tbody>{items_rows}</tbody>
        <tfoot>
          <tr><td colspan='3' style='padding:8px 12px;text-align:right;color:#555;'>Subtotal:</td><td style='padding:8px 12px;text-align:right;color:#555;'>R{po['subtotal']:.2f}</td></tr>
          {vat_row}
          <tr style="background:#f0ece6;"><td colspan='3' style='padding:10px 12px;text-align:right;font-weight:700;color:#1a1a1a;'>Total:</td><td style='padding:10px 12px;text-align:right;font-weight:700;color:#1a1a1a;'>R{po['total_amount']:.2f}</td></tr>
        </tfoot>
      </table>
      {notes}
      <p style="color:#888;font-size:12px;margin:24px 0 0;">Please reply to this email to confirm or raise any queries.</p>
    """
    send_email(supplier_email, f"Purchase Order {po['po_number']} from {company_name}", _wrap(body, supplier_email, transactional=True))


def send_invite_email(invitee_email: str, company_name: str, inviter_name: str, role: str, token: str):
    """Send a team invitation email with accept link."""
    role_labels = {
        "admin":      "Admin",
        "accountant": "Accountant",
        "payroll":    "Payroll Manager",
        "employee":   "Employee",
    }
    role_label = role_labels.get(role, role.title())
    accept_url = f"{FRONTEND_URL}/accept-invite/{token}"
    body = f"""
      <h2 style="color:#1a1a1a;margin:0 0 4px;">You've been invited to join <strong>{company_name}</strong> on ZuZan</h2>
      <p style="color:#888;margin:0 0 20px;font-size:13px;">Sent by {inviter_name}</p>
      <p style="color:#555;margin:0 0 16px;">
        <strong>{inviter_name}</strong> has invited you to collaborate on <strong>{company_name}</strong>
        with the role of <strong>{role_label}</strong>.
      </p>
      <p style="color:#555;margin:0 0 8px;">Click the button below to create your account and get started:</p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{accept_url}"
           style="background:#C8401A;color:#fff;padding:14px 36px;border-radius:8px;
                  text-decoration:none;font-weight:bold;font-size:15px;display:inline-block;">
          Accept Invitation
        </a>
      </div>
      <p style="color:#888;font-size:12px;margin:0 0 4px;">
        Or copy this link into your browser:<br>
        <a href="{accept_url}" style="color:#C8401A;">{accept_url}</a>
      </p>
      <p style="color:#aaa;font-size:11px;margin:16px 0 0;">
        This invitation expires in 48 hours. If you weren't expecting this, you can ignore it safely.
      </p>
    """
    send_email(
        invitee_email,
        f"You've been invited to join {company_name} on ZuZan",
        _wrap(body, invitee_email, transactional=True),
        from_email=FROM_SUPPORT_EMAIL,
    )


def send_invoice_email(
    client_email: str,
    client_name: str,
    company_name: str,
    invoice_number: str,
    description: str,
    total_amount: float,
    currency: str,
    due_date: str,
    portal_token: str,
    portal_url_base: str = None,
):
    """Send a branded invoice email with a portal link and Pay Now button."""
    import os as _os
    base = portal_url_base or _os.environ.get("FRONTEND_URL", "https://zuzan-app.onrender.com")
    portal_url = f"{base}/portal/{portal_token}"

    cur_sym = {"ZAR": "R", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " ")
    due_str = due_date if due_date else "On receipt"

    body = f"""
      <h2 style="color:#1a1a1a;margin:0 0 4px;">Invoice from <strong>{company_name}</strong></h2>
      <p style="color:#888;margin:0 0 24px;font-size:13px;">{invoice_number}</p>

      <table style="width:100%;border-collapse:collapse;margin:0 0 20px;font-size:14px;">
        <tr>
          <td style="padding:10px 0;color:#555;border-bottom:1px solid #eee;">Invoice Number</td>
          <td style="padding:10px 0;text-align:right;font-weight:600;color:#1a1a1a;border-bottom:1px solid #eee;">{invoice_number}</td>
        </tr>
        <tr>
          <td style="padding:10px 0;color:#555;border-bottom:1px solid #eee;">Description</td>
          <td style="padding:10px 0;text-align:right;color:#1a1a1a;border-bottom:1px solid #eee;">{description or "-"}</td>
        </tr>
        <tr>
          <td style="padding:10px 0;color:#555;border-bottom:1px solid #eee;">Amount Due</td>
          <td style="padding:10px 0;text-align:right;font-weight:700;font-size:16px;color:#1a1a1a;border-bottom:1px solid #eee;">{cur_sym}{total_amount:,.2f}</td>
        </tr>
        <tr>
          <td style="padding:10px 0;color:#555;">Due Date</td>
          <td style="padding:10px 0;text-align:right;font-weight:600;color:#C8401A;">{due_str}</td>
        </tr>
      </table>

      <p style="color:#555;margin:0 0 8px;">Dear {client_name},</p>
      <p style="color:#555;margin:0 0 24px;">
        Please find your invoice above. You can view the full invoice and pay securely online using the button below.
      </p>

      <div style="text-align:center;margin:32px 0;">
        <a href="{portal_url}"
           style="background:#C8401A;color:#fff;padding:14px 36px;border-radius:8px;
                  text-decoration:none;font-weight:bold;font-size:15px;display:inline-block;">
          View &amp; Pay Invoice
        </a>
      </div>

      <p style="color:#888;font-size:12px;margin:0 0 4px;">
        Or copy this link into your browser:<br>
        <a href="{portal_url}" style="color:#C8401A;">{portal_url}</a>
      </p>
      <p style="color:#aaa;font-size:11px;margin:20px 0 0;">
        If you have any questions about this invoice, please reply to this email.
      </p>
    """

    send_email(
        client_email,
        f"Invoice {invoice_number} from {company_name} — {cur_sym}{total_amount:,.2f} due {due_str}",
        _wrap(body, client_email, transactional=True),
    )
