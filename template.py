import joblib


bundle = joblib.load("artifact/churn_model.joblib")
print(bundle['metadata']['features'])