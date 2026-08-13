import json
import logging
from datetime import timedelta

import azure.functions as func
import azure.durable_functions as df

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

VALID_CATEGORIES = {"travel", "meals", "supplies", "equipment", "software", "other"}
AUTO_APPROVE_THRESHOLD = 100

# NOTE: kept short for local testing so you can actually watch the timeout
# fire without waiting around. Bump this up (e.g. 1440 for 24h) for a
# production-realistic value and say so in the README.
MANAGER_TIMEOUT_MINUTES = 1


# ---------------------------------------------------------------------------
# Client function: HTTP-triggered entry point that starts an orchestration
# ---------------------------------------------------------------------------
@app.route(route="expenses", methods=["POST"])
@app.durable_client_input(client_name="client")
async def submit_expense(
    req: func.HttpRequest, client: df.DurableOrchestrationClient
) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    instance_id = await client.start_new("expense_orchestrator", client_input=body)
    logging.info(f"Started orchestration with ID = '{instance_id}'.")

    # Returns 202 with statusQueryGetUri, sendEventPostUri, etc. so you can
    # poll the orchestration status from Postman/curl/test-durable.http
    return client.create_check_status_response(req, instance_id)


# ---------------------------------------------------------------------------
# Orchestrator: validation -> auto-approve OR human-interaction (timer race)
# -> notification
# ---------------------------------------------------------------------------
@app.orchestration_trigger(context_name="context")
def expense_orchestrator(context: df.DurableOrchestrationContext):
    expense = context.get_input()

    validation_result = yield context.call_activity("validate_expense", expense)
    if not validation_result["valid"]:
        yield context.call_activity(
            "send_notification",
            {
                "expense": expense,
                "outcome": "rejected",
                "reason": validation_result["reason"],
            },
        )
        return {"status": "validation_error", "reason": validation_result["reason"]}

    amount = float(expense["amount"])

    if amount < AUTO_APPROVE_THRESHOLD:
        outcome = "approved"
        reason = "auto-approved: under $100 threshold"
    else:
        # --- Human Interaction pattern ---
        # Race the manager's decision (external event) against a durable
        # timer. Whichever completes first wins; the loser is cancelled.
        deadline = context.current_utc_datetime + timedelta(
            minutes=MANAGER_TIMEOUT_MINUTES
        )
        timer_task = context.create_timer(deadline)
        approval_event_task = context.wait_for_external_event("ManagerDecision")

        winner = yield context.task_any([approval_event_task, timer_task])

        if winner == approval_event_task:
            timer_task.cancel()
            decision = approval_event_task.result
            # Depending on SDK/extension version, the event payload can come
            # back as a JSON string instead of an already-parsed dict.
            if isinstance(decision, str):
                decision = json.loads(decision)
            if decision.get("approved"):
                outcome = "approved"
                reason = f"approved by manager ({expense.get('manager_email')})"
            else:
                outcome = "rejected"
                comment = decision.get("comment", "no comment provided")
                reason = f"rejected by manager: {comment}"
        else:
            outcome = "escalated"
            reason = (
                f"no manager response within {MANAGER_TIMEOUT_MINUTES} minute(s); "
                "auto-approved and escalated"
            )

    yield context.call_activity(
        "send_notification",
        {"expense": expense, "outcome": outcome, "reason": reason},
    )

    return {"status": outcome, "reason": reason}


# ---------------------------------------------------------------------------
# Activity: validation
# ---------------------------------------------------------------------------
@app.activity_trigger(input_name="expense")
def validate_expense(expense: dict) -> dict:
    required_fields = [
        "employee_name",
        "employee_email",
        "amount",
        "category",
        "description",
        "manager_email",
    ]
    missing = [f for f in required_fields if not expense.get(f)]
    if missing:
        return {
            "valid": False,
            "reason": f"Missing required field(s): {', '.join(missing)}",
        }

    if expense["category"] not in VALID_CATEGORIES:
        return {
            "valid": False,
            "reason": (
                f"Invalid category '{expense['category']}'. "
                f"Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
            ),
        }

    try:
        amount = float(expense["amount"])
    except (TypeError, ValueError):
        return {"valid": False, "reason": "Amount must be a number"}

    if amount <= 0:
        return {"valid": False, "reason": "Amount must be greater than zero"}

    return {"valid": True, "reason": None}


# ---------------------------------------------------------------------------
# Activity: notification
# ---------------------------------------------------------------------------
@app.activity_trigger(input_name="payload")
def send_notification(payload: dict) -> dict:
    expense = payload["expense"]
    outcome = payload["outcome"]
    reason = payload["reason"]

    # TODO: swap this for a real email call (SendGrid / Azure Communication
    # Services / Logic App connector). Logged for local dev visibility.
    logging.info(
        f"[EMAIL to {expense.get('employee_email')}] "
        f"Your expense '{expense.get('description')}' "
        f"(${expense.get('amount')}) was {outcome.upper()}. Reason: {reason}"
    )
    return {"sent": True, "to": expense.get("employee_email"), "outcome": outcome}


# ---------------------------------------------------------------------------
# HTTP endpoint simulating a manager approving/rejecting an expense
# ---------------------------------------------------------------------------
@app.route(route="expenses/{instance_id}/decision", methods=["POST"])
@app.durable_client_input(client_name="client")
async def manager_decision(
    req: func.HttpRequest, client: df.DurableOrchestrationClient
) -> func.HttpResponse:
    instance_id = req.route_params.get("instance_id")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    if "approved" not in body:
        return func.HttpResponse(
            json.dumps({"error": "Body must include boolean field 'approved'"}),
            status_code=400,
            mimetype="application/json",
        )

    instance_status = await client.get_status(instance_id)
    if instance_status is None:
        return func.HttpResponse(
            json.dumps(
                {"error": f"No orchestration instance found with ID '{instance_id}'"}
            ),
            status_code=404,
            mimetype="application/json",
        )

    await client.raise_event(instance_id, "ManagerDecision", body)

    return func.HttpResponse(
        json.dumps({"message": f"Decision submitted for instance '{instance_id}'"}),
        status_code=202,
        mimetype="application/json",
    )
