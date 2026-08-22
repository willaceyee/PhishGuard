# Administrator Workspace Guide

The React application exposes the backend modules through five sidebar pages.

## Recommended operating sequence

1. Start the Flask backend and React frontend.
2. Sign in with the bootstrapped administrator account.
3. Add employees on the **Users** page.
4. Create controlled message content on the **Templates** page.
5. Create a campaign on the **Campaigns** page.
6. Open **Recipients & links**, select users, and assign them.
7. Copy each generated tracking link for use only in the authorized exercise.
8. Review clicks, submissions, training, quizzes, and risk on **Overview**.

PhishGuard does not send email during this phase. Administrators control how simulation links are delivered and must obtain organizational authorization.

## Users

The page supports creating and deleting users. A user assigned to a campaign cannot be deleted until the campaign relationship is removed, preserving analytics integrity.

## Templates

Create a template name, subject, category, and message body. Templates used by a campaign cannot be deleted.

## Campaigns and simulation links

Campaign creation requires an existing template. After creation:

- select **Recipients & links**;
- check one or more users;
- assign the selected users;
- copy the unique tracking URL shown for each recipient.

Opening a link follows the controlled flow:

```text
Tracking link → simulated landing page → awareness training → quiz
```

The simulated form never transmits or stores entered credential values.

## URL detection

Enter an HTTP or HTTPS URL on the **Detection** page. The backend analyzes the URL text offline and returns:

- legitimate or phishing prediction;
- phishing probability and confidence;
- five highest-impact SHAP factors;
- observed feature values and risk direction.

The detector does not visit or resolve the destination. Current development-model results must not be treated as definitive because real-world validation is still pending.
