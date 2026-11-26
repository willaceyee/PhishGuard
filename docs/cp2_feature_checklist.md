# CP2 Feature Checklist

## Phase 1: Project Setup

- [x] Create project folder structure
- [x] Create and publish GitHub repository
- [x] Set up Flask backend
- [x] Set up React frontend
- [x] Draft database schema
- [x] Create README.md

## Phase 2: Core Backend

- [x] Admin login API
- [x] User management API
- [x] Campaign API
- [x] Template API

## Phase 3: Simulation

- [x] Generate tracking link
- [x] Record click event
- [x] Fake landing page
- [x] Redirect to training page

## Phase 4: Training

- [x] Awareness content page
- [x] Quiz module
- [x] Store quiz result

## Phase 5: ML Detection

- [x] Prepare URL dataset
- [x] Extract URL features
- [x] Train Random Forest model
- [x] Save model
- [x] Create prediction API
- [x] Add SHAP explanation

## Phase 6: Dashboard

- [x] Show campaign statistics
- [x] Show click-through rate
- [x] Show quiz score
- [x] Show training completion
- [x] Show user risk score

## Phase 7: Testing and Report

- [x] Unit testing
- [x] Integration testing
- [ ] Usability testing
- [x] Model evaluation
- [x] Final report screenshots

**Usability testing** is still pending because it requires real participants. See
[`usability_testing_guide.md`](usability_testing_guide.md).

**Model evaluation** was completed on 2026-11-26 with a single final untouched
test:

- **Data:** 1,000 phishing and 1,000 legitimate URLs, all with source timestamps
  after the approved 2026-09-01 cutoff (PhishTank verification time and Common
  Crawl capture time). None appears in the model's development data.
- **Results:** 83.35% accuracy, 0.887 ROC-AUC. The model missed 225 phishing URLs
  and wrongly flagged 108 legitimate ones.
- **Verification:** the report was checked against the approved protocol before
  this item was ticked.
- **Details:** [`phase5_ml_detection.md`, result D](phase5_ml_detection.md#d-final_untouched_evaluationjson-the-final-untouched-test)
  and [`final_model_evaluation_plan.md`](final_model_evaluation_plan.md).

Synthetic pipeline metrics and the earlier development results are not final
evidence.
