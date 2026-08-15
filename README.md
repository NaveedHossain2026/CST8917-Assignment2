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

Version A was much faster and more predictable to build than Version B. The Durable Functions orchestrator, activities, and HTTP endpoints were all in one function_app.py file, and errors were easy to diagnose. For example, when the manager-approval event failed with 'str' object has no attribute 'get', the terminal showed a full Python traceback pointing directly to the problem. I fixed it by handling the event payload when it arrived as a JSON string instead of a dictionary. The fix took less than five minutes.

Logic Apps took more time to build and troubleshoot. Although the visual designer looked easier at first, connecting the different services and configuring the workflow was more complicated. I also had more difficulty diagnosing errors.

Overall, Durable Functions gave me more confidence that the workflow was working correctly because I could test and debug the logic directly in my code.

### Testability

Version A had a major advantage in testing. The entire workflow could be tested locally without an Azure subscription. Azurite provided local storage, `func start` ran the orchestration, and `test-durable.http` tested all six required scenarios. Even the timeout scenario could be tested locally by using a shortened one-minute timer.

Version B did not have the same local testing capability. There is no local emulator for Logic Apps or Service Bus, so only the two standalone Azure Functions could be tested locally. The actual Logic App workflow, branching, and Service Bus communication had to be tested using live Azure resources.

This creates a real difference between the approaches. With Durable Functions, I could make changes and test the complete workflow repeatedly on my computer. With Logic Apps, many problems could only be discovered after deploying to Azure.

### Error Handling

Durable Functions gave me more control over errors. I could use Python to handle exceptions and configure retries. When something failed, I could see the error directly in the terminal, which made debugging easier.

Logic Apps also has built-in error handling, such as retries and conditions for what to do when an action fails. However, I found it harder to troubleshoot because a failure could come from the Logic App, Service Bus, Azure Function, or HTTP connection.

Overall, I preferred Durable Functions for error handling because it gave me more control and made it easier to find and fix problems. Logic Apps was easier for basic retry and failure handling because much of it could be configured visually.

### Human Interaction Pattern

This is the area where Durable Functions was clearly better suited to the assignment.

Durable Functions has a built-in `task_any()` pattern that can wait for either a manager's response or a timer to expire. This directly matches the requirement of waiting for human approval or escalating after a timeout. It worked correctly during testing for approval, rejection, and timeout.

Logic Apps does not have an equivalent built-in human-approval waiting pattern in the same way. To solve the problem, I used an `HttpWebhook` action that pauses the workflow and provides a callback URL. A custom Azure Function then emails the manager and converts their response into a POST request to the webhook.


### Observability

Durable Functions provided simple and useful monitoring through statusQueryGetUri. It showed the orchestration status, input, and output as JSON, which made it easy to check all six test scenarios.

Logic Apps has a better visual monitoring experience. Its Run History shows each step, condition, and result, making it easier to understand the workflow.

However, Version B was not as stable, so I could not fully use these monitoring features. This taught me that good monitoring is only helpful when the workflow is working reliably.

### Cost

For the comparison, I assumed the Consumption/serverless tier in Canada Central, around 10 Logic App actions per expense, approximately six Durable Functions executions per run, and a Service Bus Standard tier costing about $10 per month.

At **100 expenses/day** (~3,000/month), Durable Functions would remain almost entirely within the monthly free grant of 1 million executions and 400,000 GB-seconds. Its cost would therefore be close to **$0**, apart from a small amount for storage.

Logic Apps would also have very low execution costs at this volume. With approximately 36,000 actions/month at ~$0.000025 per action, the Logic App itself would cost less than **$1**. However, Version B also requires Service Bus, creating a roughly **$10/month** baseline.

At **10,000 expenses/day** (~300,000/month), the difference becomes much larger. Durable Functions would exceed the free grant but would still cost only around **$5-10/month** under these assumptions. Logic Apps would perform around 3.6 million actions/month, resulting in approximately **$90** in action charges. Adding roughly $10 for Service Bus brings the total to around **$100/month**.

| | 100/day | 10,000/day |
|---|---|---|
| **Durable Functions** | ~$0-2/mo | ~$5-10/mo |
| **Logic Apps + Service Bus** | ~$11/mo | ~$100/mo |

Therefore, at higher volumes, Durable Functions is significantly more cost-effective for this workflow.

## Recommendation

For a production version of this expense approval workflow, I would choose Azure Durable Functions. The workflow has several steps, such as validation, automatic approval, manager approval, waiting for a response, handling timeouts, and sending notifications. Durable Functions is a good fit because it can pause and resume the workflow while keeping its state. The manager approval and timeout were also easier to implement with Durable Functions.

I also found Durable Functions easier to develop and debug. Since the workflow was written in Python, I had more control over the logic. When an error happened, the Python traceback helped me quickly find the problem. The statusQueryGetUri also made it easy to check the workflow status and results.

I would choose Logic Apps when the main goal is connecting different services and creating workflows visually. Its Run History makes it easy to see what happened at each step, and its built-in connectors can reduce the amount of code needed.

## References
Microsoft Learn. Durable Functions overview. https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview

Microsoft Learn. Human interaction in Durable Functions — external events. https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-external-events

Microsoft Learn. Durable timers. https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-timers

Microsoft Learn. Logic Apps overview. https://learn.microsoft.com/en-us/azure/logic-apps/logic-apps-overview

Microsoft Learn. Service Bus messaging overview. https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-messaging-overview

## AI Disclosure

AI tools, including Claude by Anthropic, were used during this project to help write code, fix errors, draft the comparison analysis and slides, and solve Azure Portal issues, following the assignment’s AI policy. I personally tested and verified all code and rewrote the analysis in my own words based on my experience building both versions


Overall, I would choose Durable Functions for this workflow because it provides more control, easier debugging, and better support for manager approval and timeouts. I would choose Logic Apps when visual design, easy service integration, and monitoring are more important than having detailed control over the code.
