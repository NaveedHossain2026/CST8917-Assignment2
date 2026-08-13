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

## Comparison Analysis 

### Development Experience

Version A was much faster and more predictable to build than Version B. The Durable Functions orchestrator, activities, and HTTP endpoints were all in one `function_app.py` file, and errors were easy to diagnose. For example, when the manager-approval event failed with `'str' object has no attribute 'get'`, the terminal showed a full Python traceback pointing directly to the problem. I fixed it by handling the event payload when it arrived as a JSON string instead of a dictionary. The fix took less than five minutes.

Version B was more difficult, especially when working with the Logic App itself. The Service Bus infrastructure and Azure Functions deployed successfully using Bicep and `func azure functionapp publish`. However, manually creating the Logic App as raw JSON caused several problems, including Bicep quoting errors, Azure Functions connector restrictions, `$connections` schema mismatches, and differences between the JSON expected by the code view and the actual workflow definition.

The most frustrating issue was that replacing the entire workflow through code view could remove the *value* portion of existing connection references. This meant actions that had worked in the designer could stop working after a code-view replacement. Eventually, rebuilding the workflow through the Logic App designer proved much more reliable. This was surprising, because I expected the visual/declarative platform to be easier to work with than the code-first approach.

### Testability

Version A had a major advantage in testing. The entire workflow could be tested locally without an Azure subscription. Azurite provided local storage, `func start` ran the orchestration, and `test-durable.http` tested all six required scenarios. Even the timeout scenario could be tested locally by using a shortened one-minute timer.

Version B did not have the same local testing capability. There is no local emulator for Logic Apps or Service Bus, so only the two standalone Azure Functions could be tested locally. The actual Logic App workflow, branching, and Service Bus communication had to be tested using live Azure resources.

This creates a real difference between the approaches. With Durable Functions, I could make changes and test the complete workflow repeatedly on my laptop. With Logic Apps, many problems could only be discovered after deploying to Azure.

### Error Handling

Durable Functions provided clearer error messages. When something failed, the Python exception and full stack trace showed exactly where the problem occurred. This made debugging much faster.

Logic Apps provided useful built-in features such as retry policies and the `HttpWebhook` action's `TimedOut` status, which made timeout handling relatively clean once everything was configured correctly. However, getting the workflow configured correctly was the difficult part.

Errors such as *"The API connection name must be provided in the action inputs"* were technically correct but not very helpful. During the project, similar messages were caused by different problems, including missing connection values, stale designer state, and connection references being reset during code-view replacement. As a result, troubleshooting often required trial and error rather than following a clear error message.

### Human Interaction Pattern

This is the area where Durable Functions was clearly better suited to the assignment.

Durable Functions has a built-in `task_any()` pattern that can wait for either a manager's response or a timer to expire. This directly matches the requirement of waiting for human approval or escalating after a timeout. It worked correctly during testing for approval, rejection, and timeout.

Logic Apps does not have an equivalent built-in human-approval waiting pattern in the same way. To solve the problem, I used an `HttpWebhook` action that pauses the workflow and provides a callback URL. A custom Azure Function then emails the manager and converts their response into a POST request to the webhook.

This solution works and is documented in `DESIGN-NOTES.md`, but it required building an additional component that Durable Functions provided as part of the orchestration model. That represents a meaningful difference in development effort.

### Observability

Durable Functions provided simple and useful observability through `statusQueryGetUri`. It returned the orchestration status, input, and output as structured JSON, which made it easy to verify all six test scenarios.

Logic Apps has a strong visual run-history experience. Its condition branches and individual action results can be easier for non-developers to understand. However, because Version B never reached the same level of stable execution, I could not take full advantage of those features. This was also an important lesson: good observability is only useful once the workflow is running reliably.

### Cost


At **100 expenses/day** (~3,000/month), Durable Functions would remain almost entirely within the monthly free grant of 1 million executions and 400,000 GB-seconds. Its cost would therefore be close to **$0**, apart from a small amount for storage.

Logic Apps would also have very low execution costs at this volume. With approximately 36,000 actions/month at ~$0.000025 per action, the Logic App itself would cost less than **$1**. However, Version B also requires Service Bus, creating a roughly **$10/month** baseline.

At **10,000 expenses/day** (~300,000/month), the difference becomes much larger. Durable Functions would exceed the free grant but would still cost only around **$5-10/month** under these assumptions. Logic Apps would perform around 3.6 million actions/month, resulting in approximately **$90** in action charges. Adding roughly $10 for Service Bus brings the total to around **$100/month**.

| | 100/day | 10,000/day |
|---|---|---|
| **Durable Functions** | ~$0-2/mo | ~$5-10/mo |
| **Logic Apps + Service Bus** | ~$11/mo | ~$100/mo |

Therefore, at higher volumes, Durable Functions is significantly more cost-effective for this workflow.
