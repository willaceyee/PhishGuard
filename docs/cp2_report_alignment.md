# CP2 Report Alignment

This mapping aligns the PhishGuard section draft with the supplied Sunway CP2 final-report template and 2026 rubric. Participant usability testing is postponed. The existing section draft provides material for Chapters 3 and 4, while the institutional template defines the final report structure.

## Required Report Structure

| Template section | PhishGuard content and evidence | Work required |
| --- | --- | --- |
| Cover and integrity declaration | Approved project title, student details, programme, supervisor, semester, date and chosen citation style | Confirm programme, supervisor, semester and submission date. Student reviews and signs the declaration personally. |
| Abstract and keywords | Problem, objectives, implemented method, principal results and contribution | Write last as a single paragraph of 250 to 300 words. Include 83.35% accuracy with sample context and acknowledge any outstanding evaluation objective. |
| 1.1 Background | Cybersecurity awareness, phishing simulation, URL detection and explanations | Adapt proposal material and support the background with four to six sources. |
| 1.2 Problem statement | The specific problem motivating an integrated awareness and detection system | Use the approved proposal and keep the problem traceable to the objectives. |
| 1.3 Research objectives | Approved measurable objectives | Copy the approved objectives accurately before assigning objective numbers to results. |
| 1.4 Scope and limitations | Authorized simulations, lexical URL detection, selected data sources and users | Explain boundaries and justified limitations. |
| 1.5 Research significance | Potential benefit for awareness training and explainable assessment | Support claims about broader impact and sustainability with evidence. |
| 2.1 to 2.4 Literature review | Themed review, comparative table and research gap | Review relevant peer-reviewed literature and derive the gap from its limitations. |
| 3.1 System overview | Draft application architecture and record relationships | Add Figure 3.1 with React, Flask, database, ML bundle, participant routes and email services. Explain the boundaries and data flow in the text. |
| 3.2 Data and input description | User/template/campaign inputs, training sources and final-test sources | Distinguish training, validation, diagnostic and held-out samples. Cite source documentation and give dates, formats and label rules. |
| 3.3 Methodological approach | Simulation workflow, delivery controls, feature extraction, Random Forest, SHAP and risk scoring | Move the method explanations here. Justify choices and document changes from CP1 after comparison with the proposal. |
| 3.4 Tools and technologies | Flask, SQLAlchemy, React, Scikit-learn, SHAP, Mailpit, Gmail SMTP, Pytest, Vitest and GitHub | Create Table 3.1 and explain the capability each tool provides. Record actual versions from the relevant environment. |
| 3.5 Evaluation criteria | Classification metrics, leakage controls, software checks and planned usability measures | Define each measure and its denominator. Distinguish prespecified acceptance targets from reported scores. |
| 4.1 Experimental setup and implementation | Final system, configuration, model parameters and deployment context | Summarize in approximately 200 to 300 words. Verify hardware details and record actual software versions. Reference current screenshots. |
| 4.2 Results | Final confusion matrix, class metrics, interface outcomes and automated verification evidence | Present objective measurements, sample sizes, figure references and Table 4.1 mapping results to the exact objectives. |
| 4.3 Discussion | False negatives, false positives, development history, source differences and explanation scope | Interpret the results against objectives. Add Table 4.2 and a critical comparison with studies reviewed in Chapter 2, accounting for dataset differences. |
| 4.4 Verification and validation | Requirement-to-test mapping, automated results, demonstration evidence and final holdout | Verify test counts from the relevant recorded run. State that participant testing is deferred and human usability outcomes remain pending. |
| 4.5 Limitations | Source coverage, class balance, label noise, lexical inputs, historical scope and postponed usability study | Explain the effect of each limitation on conclusions. |
| 5.1 Conclusion | Findings against each approved objective | Write 250 to 400 words after the results and objective mapping are settled. |
| 5.2 Future work | Improvements arising from Section 4.5 | Justify each proposed direction through an identified limitation. |
| References | Literature and external technical/data sources cited in the report | Choose IEEE or APA and apply it consistently. Repository evidence complements external references. |
| Appendices | Test cases, extended metrics, questionnaire and protocol | Reference each appendix from the main text and keep sensitive data out. |

## Template Formatting

- Use Times New Roman or Arial consistently, with 12-point body text.
- Use 1.5-line spacing in the main text and single spacing in tables.
- Justify body text and follow the template's centered heading and cover treatment.
- Use one-inch margins on all sides.
- Start every chapter on a new page.
- Place page numbers at the bottom center. Use Roman numerals for front matter and Arabic numerals from Chapter 1.
- Number and caption every figure and table and refer to each in the text.
- Declare IEEE or APA on the cover and use the selected style throughout.
- The template gives minimums of 600 words for the background, 1,200 for the literature review and 800 for methodology. Its detailed section guidance also specifies 600 to 800 words for the methodological approach subsection.
- The template expects at least ten peer-reviewed sources and recommends fifteen to twenty. It requests recent sources within five years, with exceptions for seminal work.
- Remove instructional boxes, examples and template placeholders when preparing the submission copy.
- Replace the example semester and date with confirmed project details.
- The template specifies a Turnitin similarity index below 20 percent. This must be checked through the university's submission process.

## Rubric Priorities

The highest performance band requires a clear chain from problem to objectives, method, evidence, discussion and conclusion. A feature inventory alone leaves the justification and evaluation criteria underdeveloped.

The implementation material should explain the reason for major decisions, including recipient approval, credential-free simulation, lexical-only extraction, Random Forest selection, SHAP presentation and the exclusion of HTTPS from the current model inputs. Security, ethics, usability and practical deployment constraints belong in the methodology.

Chapter 4 needs sustained critical discussion and comparison with related research. The final result is 83.35 percent accuracy on a balanced sample of 2,000 URLs. The 225 false negatives, 108 false positives, official-domain legitimate sampling and source timestamps must stay consistent throughout the report. A literature comparison must consider differences in data, class balance, features and evaluation design before interpreting score differences.

The logbook and poster demonstration are separate assessed deliverables. The logbook rubric's highest progress band requires ten or more weeks of updates and justified reflection. The demonstration rubric emphasizes working outcomes, systematic evidence, technical reasoning, questions and answers, and a clear poster. Completing report chapters alone does not supply that evidence.

## Items Requiring Confirmation

The rubric contains conflicting assessment totals. Its labels state Final Report 40 percent and Presentation and Demonstration 50 percent, while the category totals state 50 and 40 percent respectively. The literature-review criterion carries five in the rubric's distribution column, while an instructional box in the report template says ten. Confirm the official allocation with the supervisor or module coordinator before using weights to prioritize work.

The exact approved objectives, programme, supervisor, semester, submission date and chosen citation style must be confirmed from the proposal or the student's current report. These details should not be inferred from template examples.

No participant findings are available for the postponed study. Sections 3.5, 4.4, 4.5 and 5 should reflect this status consistently until sessions are completed.

## Next Authoring Pass

Use the institutional DOCX as the formatting authority and work on a copy. Place the existing section draft into Chapters 3 and 4 using the map above. Add the architecture diagram, tool-justification table and requirement-evidence matrix. Finalize objective mappings after checking the approved proposal, then add the literature comparisons and conclusion. Preserve the original template for reference.
