"""
Small standalone Azure Function that bridges the Logic App's HTTP Webhook
action to an actual human clicking a link in an email. See
../DESIGN-NOTES.md for why this exists.

Two endpoints:

  POST /api/notify-manager
      Called by the Logic App's webhook "subscribe" request. Body:
        { manager_email, employee_name, amount, description, callbackUrl }
      Sends the manager an email with Approve / Reject links. Each link
      points back to /api/decide with the decision and the original
      callbackUrl baked in as query params.

  GET /api/decide?approved=true|false&callback=<url-encoded callbackUrl>&comment=...
      The manager lands here after clicking a link. This POSTs
      {"approved": bool, "comment": str} to the Logic App's callback URL
      (which resumes the paused workflow run), then shows a simple
      confirmation page.
"""

import json
import logging
import os
import urllib.parse

import azure.functions as func
import requests

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
FROM_EMAIL = os.environ.get("NOTIFICATION_FROM_EMAIL", "expenses@yourcompany.example")

# Base URL of THIS function app, used to build the approve/reject links.
# Set this app setting after deployment, e.g. https://<your-app>.azurewebsites.net
RELAY_BASE_URL = os.environ.get("RELAY_BASE_URL", "http://localhost:7071")


@app.route(route="notify-manager", methods=["POST"])
def notify_manager(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    manager_email = payload.get("manager_email")
    callback_url = payload.get("callbackUrl")
    if not manager_email or not callback_url:
        return func.HttpResponse(
            json.dumps({"error": "manager_email and callbackUrl are required"}),
            status_code=400,
            mimetype="application/json",
        )

    encoded_callback = urllib.parse.quote(callback_url, safe="")
    approve_link = f"{RELAY_BASE_URL}/api/decide?approved=true&callback={encoded_callback}"
    reject_link = f"{RELAY_BASE_URL}/api/decide?approved=false&callback={encoded_callback}"

    subject = f"Expense approval needed: {payload.get('employee_name', 'an employee')}"
    body_text = (
        f"{payload.get('employee_name', 'An employee')} submitted an expense "
        f"of ${payload.get('amount')} for \"{payload.get('description')}\".\n\n"
        f"Approve: {approve_link}\n"
        f"Reject:  {reject_link}\n"
    )

    if SENDGRID_API_KEY:
        try:
            resp = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": manager_email}]}],
                    "from": {"email": FROM_EMAIL},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body_text}],
                },
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logging.error(f"Failed to send manager approval email: {exc}")
            return func.HttpResponse(
                json.dumps({"error": "Failed to send email"}),
                status_code=502,
                mimetype="application/json",
            )
    else:
        # Local/dev fallback: log instead of sending a real email so you can
        # test the relay's callback wiring without a SendGrid key.
        logging.info(f"[MANAGER EMAIL to {manager_email}]\n{body_text}")

    return func.HttpResponse(
        json.dumps({"sent": True, "to": manager_email}),
        status_code=200,
        mimetype="application/json",
    )


@app.route(route="decide", methods=["GET"])
def decide(req: func.HttpRequest) -> func.HttpResponse:
    approved = req.params.get("approved", "").lower() == "true"
    callback_url = req.params.get("callback")
    comment = req.params.get("comment", "")

    if not callback_url:
        return func.HttpResponse("Missing callback URL.", status_code=400)

    decoded_callback = urllib.parse.unquote(callback_url)

    try:
        resp = requests.post(
            decoded_callback,
            json={"approved": approved, "comment": comment},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logging.error(f"Failed to relay decision to callback URL: {exc}")
        return func.HttpResponse(
            "Something went wrong submitting your decision. "
            "Please contact IT.",
            status_code=502,
        )

    outcome_word = "approved" if approved else "rejected"
    return func.HttpResponse(
        f"<html><body style='font-family:sans-serif'>"
        f"<h2>Thanks!</h2><p>You {outcome_word} this expense. "
        f"You can close this tab.</p></body></html>",
        status_code=200,
        mimetype="text/html",
    )
