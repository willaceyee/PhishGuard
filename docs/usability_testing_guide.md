# PhishGuard Usability Testing Guide

This guide prepares a controlled usability study for PhishGuard. It standardizes
how sessions are conducted so administrator and end-user feedback can be compared
and reported without collecting names, personal email addresses, or real
credentials. The study is not complete until genuine participants perform the
tasks and their anonymous results are recorded.

## Study Scope

- Recruit six to eight volunteers, aiming for at least three administrator-role
  participants and three end-user-role participants.
- Use participant codes such as `A01` and `E01`; do not record names or email
  addresses.
- Use a disposable database, reserved `example.test` addresses, and local Mailpit
  delivery. Do not send simulation messages to real inboxes during this study.
- Use only test credentials supplied by the facilitator. Participants must not
  enter a personal password.
- Allow approximately 20 to 30 minutes for each session.

If the final sample is smaller or unevenly split, report the actual numbers and
do not describe the sample as representative of all users.

## Before Each Session

1. Start the backend, frontend, and Mailpit services.
2. Load a fresh disposable evidence database.
3. Confirm that the administrator test account can sign in.
4. Confirm that the reserved test recipients are approved for local delivery.
5. Open the application at the starting screen for the participant's role.
6. Prepare a timer and a copy of `usability_results_template.csv`.
7. Assign the next anonymous participant code.

Do not record the screen, voice, or participant image unless separate approval
and explicit participant consent have been obtained.

## Consent Script

Read this statement before beginning:

> You are invited to test the usability of PhishGuard, a controlled phishing
> simulation and awareness-training application. Participation is voluntary. You
> may skip a question or stop at any time. Please use only the test information
> provided during this session and do not enter personal credentials. We will
> record an anonymous participant code, task outcomes, completion times, errors,
> assistance, ratings, and comments. We will not record your name or personal
> email address. Do you understand this information and agree to participate?

If the participant agrees, enter `yes` in `consent_confirmed` on that
participant's `QUESTIONNAIRE` row. If the participant does not agree, end the
session and do not create a participant record.

## Facilitator Rules

- Read each task exactly as written and do not demonstrate the solution first.
- Start timing after the task is read and stop when the participant says the task
  is complete or chooses to stop.
- Do not help unless the participant asks or cannot continue. Record every hint
  or intervention as assistance.
- Ask the participant to think aloud, but do not correct their interpretation.
- Use `success` when the goal is completed without facilitator intervention,
  `partial` when the goal is completed with assistance or only partly completed,
  and `failure` when the goal is not completed.
- Record observable errors without judging the participant.
- Administer the questionnaire after all assigned tasks.
- Record task observations on the matching task rows. Record the six ratings and
  anonymous comments once on the participant's `QUESTIONNAIRE` row.

## Administrator Tasks

| ID | Task shown to the participant | Completion condition |
| --- | --- | --- |
| A1 | Sign in using the administrator test account. | The administration dashboard is displayed. |
| A2 | Add a fictional user with a reserved `example.test` email address. | The user appears in the user list with no personal information. |
| A3 | Create or edit a simulation email template. | The template library shows the saved subject and content. |
| A4 | Create a campaign, select the test template, and assign the approved test user. | The campaign shows the selected template and assigned recipient. |
| A5 | Review the campaign and user analytics. Identify the highest click-through result and the user who should receive additional coaching. | The participant identifies the displayed values and explains the choice. |
| A6 | Submit `http://secure-account-verify.example.test/login?session=confirm` for detection and explain the strongest SHAP factor. | A result is displayed and the participant describes one factor in their own words. |
| A7 | Sign out of the administrator account. | The login screen is displayed. |

Do not ask participants to enable Gmail delivery or send to a real address. If
delivery must be demonstrated, use only the approved local Mailpit recipient.

## End User Tasks

| ID | Task shown to the participant | Completion condition |
| --- | --- | --- |
| E1 | Open the prepared simulation message in Mailpit and follow its training link. | The controlled awareness page opens. |
| E2 | Review the awareness page and identify two phishing warning signs. | The participant correctly describes two displayed indicators. |
| E3 | Complete the five-question awareness quiz. | A quiz result is displayed. |
| E4 | Review the prepared URL detection result and explain what the strongest SHAP factor means. | The participant explains the factor in their own words. |

## Post-Task Questionnaire

Give the participant `usability_questionnaire.md`. Record each one-to-five rating
in the CSV. Keep written comments anonymous and remove any personal information
the participant includes accidentally.

## Analysis for the Report

Report administrator and end-user results separately, followed by the combined
results. Include:

- participant count by role;
- successful, partial, and failed task counts;
- task success rate, calculated as successful tasks divided by attempted tasks;
- median completion time for successful tasks;
- mean ratings for ease, clarity, explanation helpfulness, readability,
  confidence, and overall satisfaction;
- the most common errors and assistance requests;
- anonymized positive and negative comments; and
- interface changes made in response to the findings.

Use the existing acceptance targets: at least 80% successful task completion,
median task completion under two minutes, mean ease and clarity ratings of at
least 4/5, and no critical issue that prevents login, dashboard interpretation,
training, quiz completion, or logout.

Mark the Phase 7 usability-testing checklist item complete only after real
sessions have been conducted and the anonymized results have been reviewed.
