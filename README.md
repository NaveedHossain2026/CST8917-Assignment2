# Assignment 2: Compare & Contrast — Dual Implementation of an Expense Approval Workflow

**Student Name**: Naveed Hossain             **Student ID**: 0410818822 
**Course**: CST8917 - Serverless Applications
**Date**: August 14 2026

## Version A Summary

Version A uses **Azure Durable Functions**. An HTTP function receives the expense and starts the workflow. The orchestrator checks the amount, validates the request, and handles approval.

- Under **$100** → automatically approved.
- **$100 or more** → waits for a manager decision or a 1-minute timer.
- Manager responds first → uses their decision.
- Timer finishes first → automatically approves and marks it as escalated.
- A second HTTP endpoint lets the manager submit their decision.

For testing, the timeout was set to 1 minute instead of the 24 hours we would use in production. Notifications were logged to the console instead of sending real emails.

The main challenges were **VS Code Restricted Mode** hiding the testing buttons and the manager's response sometimes arriving as a string instead of an object. Both were fixed, and **all six required test scenarios passed**.


## Version B Summary

Version B uses **Logic Apps and Service Bus**. I successfully deployed the queue, topic, and three filtered subscriptions. A separate Azure Function handles validation using the same rules as Version A.

The Logic App was built in the **visual designer**. It receives the message, parses it, calls the validation function, and then decides what to do based on the expense amount.

The main challenge is that I hit an error I couldn't resolve in time when calling the validation function. The Logic App returned an InvalidProtocolResponse error related to the upload request.

