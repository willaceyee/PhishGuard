# Phase 5 Machine-Learning Detection Guide

Phase 5 implements an offline phishing URL classifier using lexical URL features, a Random Forest model, and SHAP explanations.

## Safety boundary

Feature extraction never connects to a submitted URL. It performs no HTTP request, DNS lookup, WHOIS query, page download, or browser navigation. Only the URL text is analyzed.

The prediction API requires an administrator JWT. This prevents the endpoint from becoming an unrestricted public scanning service.

## Development dataset

Generate the deterministic demonstration dataset from `backend`:

```powershell
.\venv\Scripts\python.exe -m app.ml.prepare_demo_data
```

This creates `ml_model/data/demo_urls.csv` with 300 benign and 300 phishing-like synthetic examples. All hosts use reserved example namespaces or documentation IP addresses.

The dataset is only a pipeline fixture. It is deliberately separable and therefore produces unrealistically strong metrics. Do not cite its accuracy as the system's final evaluation.

For final evaluation, use a documented real-world dataset and record:

- source and collection period;
- class definitions and label quality;
- license and ethical-use conditions;
- duplicate-removal method;
- train, validation, and test split strategy;
- class distribution and potential sources of bias.

## URL features

The extractor produces 19 deterministic features:

- URL, hostname, path, and query lengths;
- digit, dot, hyphen, at-sign, and percent counts;
- subdomain count and path depth;
- query-parameter and suspicious-keyword counts;
- HTTPS usage;
- IP-hostname, explicit-port, punycode, and known-shortener flags;
- Shannon character entropy.

## Training

Run from `backend`:

```powershell
.\venv\Scripts\python.exe -m app.ml.train
```

Training uses a deterministic stratified 75/25 split and a 300-tree `RandomForestClassifier` with balanced class weights. It writes:

- `ml_model/artifacts/phishguard_url_model.joblib`;
- `ml_model/artifacts/metrics.json`.

The binary model is ignored by Git because serialized model files should be rebuilt from the documented pipeline or managed as versioned deployment artifacts.

## Prediction API

`POST /api/detection/predict`

The endpoint requires an administrator bearer token.

```json
{
  "url": "https://portal.example/account"
}
```

The response includes:

- `prediction`: `phishing` or `legitimate`;
- `phishing_probability` and `confidence`;
- the 19 extracted features;
- five highest-impact SHAP factors;
- each factor's value, SHAP impact, and risk direction.

SHAP factors explain this model's decision for the submitted feature vector. They do not prove that a URL is malicious, and users should treat the output as decision support rather than a definitive verdict.

## Automated tests

Tests generate and train a temporary model rather than relying on the ignored local artifact. Coverage includes feature extraction, invalid URL rejection, authentication, missing-model behavior, prediction structure, and SHAP output.
