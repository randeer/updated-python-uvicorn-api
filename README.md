# updated-python-uvicorn-api

A small FastAPI app providing utilities to manage per-user folders, create text files, and generate Kubernetes template files and MySQL user/databases for WordPress. Designed as a lightweight API for automating user workspace provisioning and templated k8s manifests.

Features
- POST /create_text_file/ — write a user text file locally
- POST /create_folder/ — create users/user_<userID> and record user in DB
- POST /push_data_db/ — insert a user into MySQL (async aiomysql)
- POST /push_data_db/create_wordpress_db/ — create a DB and MySQL user for a WordPress instance
- POST /copy_template_folder/ — copy k8s-template into a user's folder
- POST /update_template_files/ — populate YAML templates with user values
- POST /create_k8s_objects/ — apply k8s manifests (requires kubectl and kubeconfig)

Quickstart (local)
1. Create a Python 3.11 venv and install deps:
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install -r requirements.txt  # (or pip install fastapi uvicorn aiomysql pyyaml)

2. Set environment variables for DB access (recommended):
   DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

3. Run the app:
   uvicorn copilot_main:app --host 0.0.0.0 --port 8000

Usage notes
- Endpoints expect JSON matching the UserInfo model: {"username","email","userID","userDomain"} or FolderInfo: {"userID"}.
- Many operations (DB, kubectl) require reachable services and correct credentials. In CI, tests run inside the runner and cannot be reached externally.

Security & maintenance
- Do NOT commit secrets. Use environment variables or a secrets manager.
- The original main.py contains hardcoded credentials; prefer copilot_main.py which reads DB config from env and uses safer async subprocess handling.

License
- MIT (adjust as needed).
