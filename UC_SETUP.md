# UC05 Setup Guide

1. Copy agent/, config/, .github/ into customer_platform_demo.
2. Replace service_catalog.json, dependency_graph.json, test_mappings.json.
3. Create venv.
4. pip install -r requirements.txt
5. python -m unittest discover -s tests -v
6. git add .
7. git commit -m "Add UC05"
8. git push origin main
9. Create feature branch and push changes to trigger workflow.
