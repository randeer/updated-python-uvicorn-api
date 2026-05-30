from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import aiomysql
import logging
import os
from pathlib import Path
import shutil
import yaml
import asyncio
from typing import List, Dict, Any

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS - keep permissive by default but encourage restricting in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGINS", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB config from environment (safer than hardcoding). Provide sensible defaults for local dev.
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "docker.lala-1992.xyz"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "db": os.getenv("DB_NAME", "myapidb"),
    "port": int(os.getenv("DB_PORT", "3306")),
}

class UserInfo(BaseModel):
    username: str
    email: str
    userID: int
    userDomain: str

class FolderInfo(BaseModel):
    userID: int

# Helper: get async connection
async def get_connection():
    try:
        conn = await aiomysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            db=DB_CONFIG["db"],
            port=DB_CONFIG["port"],
        )
        return conn
    except Exception as e:
        logger.error("Failed to connect to DB: %s", e)
        raise

# Insert user using parameterized queries
async def insert_into_database(user_info: UserInfo) -> Dict[str, Any]:
    conn = None
    try:
        logger.info("Connecting to DB to insert user %s", user_info.userID)
        conn = await get_connection()
        async with conn.cursor() as cur:
            sql_check = "SELECT 1 FROM users WHERE userID = %s LIMIT 1"
            await cur.execute(sql_check, (user_info.userID,))
            existing = await cur.fetchone()
            if existing:
                return {"message": f"Username with userID {user_info.userID} already exists."}

            sql_insert = "INSERT INTO users (username, userID, email, domain_name) VALUES (%s, %s, %s, %s)"
            await cur.execute(sql_insert, (user_info.username, user_info.userID, user_info.email, user_info.userDomain))
            await conn.commit()
            return {"message": "User inserted successfully."}
    except aiomysql.Error as e:
        logger.exception("Database error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

# Create wordpress DB and user. userID is integer (validated by Pydantic) so using it to form identifiers is safe.
async def create_wordpress_db(user_info: UserInfo) -> Dict[str, Any]:
    conn = None
    try:
        logger.info("Creating wordpress DB for user %s", user_info.userID)
        conn = await get_connection()
        async with conn.cursor() as cur:
            db_name = f"user{user_info.userID}"
            # Create DB
            await cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")

            # Create user and grant - use a generated password (in a real system generate securely)
            db_username = f"user{user_info.userID}"
            db_password = f"password{user_info.userID}"

            # Creating SQL identifiers requires interpolation; userID is an int so this is safe here.
            await cur.execute(f"CREATE USER IF NOT EXISTS '{db_username}'@'%' IDENTIFIED BY '{db_password}'")
            await cur.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_username}'@'%'")
            await cur.execute("FLUSH PRIVILEGES")
            await conn.commit()

            return {
                "message": "WordPress database and user created successfully.",
                "db_name": db_name,
                "db_username": db_username,
                "db_password": db_password,
                "db_hostname": DB_CONFIG["host"],
            }
    except aiomysql.Error as e:
        logger.exception("Database error while creating wordpress DB")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@app.post("/push_data_db/create_wordpress_db/")
async def create_wordpress_db_endpoint(user_info: UserInfo):
    return await create_wordpress_db(user_info)

@app.post("/push_data_db/")
async def push_data_db(user_info: UserInfo):
    return await insert_into_database(user_info)

@app.post("/create_folder/")
async def create_folder(user_info: UserInfo):
    parent_folder = "users"
    folder_name = f"user_{user_info.userID}"
    full_path = os.path.join(parent_folder, folder_name)
    try:
        Path(parent_folder).mkdir(exist_ok=True)
        Path(full_path).mkdir(exist_ok=True)
        logger.info("Created folder %s", full_path)

        response = await insert_into_database(user_info)
        return {"message": f"Folder '{full_path}' created successfully and {response['message']}"}
    except Exception as e:
        logger.exception("Failed to create folder")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create_text_file/")
async def create_text_file(user_info: UserInfo):
    filename = f"user_{user_info.userID}.txt"
    file_content = (
        f"Username: {user_info.username}\n"
        f"Email: {user_info.email}\n"
        f"UserID: {user_info.userID}\n"
        f"Domainname: {user_info.userDomain}"
    )
    try:
        # write file
        with open(filename, "w", encoding="utf-8") as f:
            f.write(file_content)
        logger.info("Wrote file %s", filename)

        response = await insert_into_database(user_info)
        return {"message": f"Text file '{filename}' created and {response['message']}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create text file")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/copy_template_folder/")
async def copy_template_folder(folder_info: FolderInfo):
    parent_folder = "users"
    user_folder = f"user_{folder_info.userID}"
    full_path = os.path.join(parent_folder, user_folder)
    template_folder = "k8s-template"
    try:
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"User folder '{full_path}' not found")
        dst_folder = os.path.join(full_path, os.path.basename(template_folder))
        # remove if exists to ensure a clean copy
        if os.path.exists(dst_folder):
            shutil.rmtree(dst_folder)
        shutil.copytree(template_folder, dst_folder)
        logger.info("Copied %s to %s", template_folder, dst_folder)
        return {"message": f"Template folder copied to '{dst_folder}' successfully"}
    except FileNotFoundError as e:
        logger.error(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to copy template folder")
        raise HTTPException(status_code=500, detail=str(e))

# Update template files safely
async def update_template_files(user_info: UserInfo) -> Dict[str, Any]:
    parent_folder = "users"
    user_folder = f"user_{user_info.userID}"
    template_folder = os.path.join(parent_folder, user_folder, "k8s-template")

    paths = {
        "issuer": os.path.join(template_folder, "issuer_template.yml"),
        "namespace": os.path.join(template_folder, "namespace-template.yaml"),
        "pvc": os.path.join(template_folder, "persistentvolumeclaim-template.yaml"),
        "configmap": os.path.join(template_folder, "configmap-template.yml"),
        "wordpress": os.path.join(template_folder, "wordpress-template.yml"),
        "service": os.path.join(template_folder, "service-template.yml"),
        "ingress": os.path.join(template_folder, "ingress-template.yml"),
        "certificate": os.path.join(template_folder, "certificate-template.yml"),
        "mysql": os.path.join(template_folder, "mysql-template.yaml"),
        "mysqlservice": os.path.join(template_folder, "mysql-service-template.yaml"),
    }

    updated = []
    try:
        for key, file_path in paths.items():
            if not os.path.exists(file_path):
                logger.warning("Template missing: %s", file_path)
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Replace safe placeholders
            content = content.replace("{{ userID }}", str(user_info.userID))
            content = content.replace("{{ email }}", user_info.email)
            content = content.replace("{{ userDomain }}", user_info.userDomain)

            # Parse and dump back as YAML to normalize formatting
            try:
                yaml_content = yaml.safe_load(content)
            except Exception:
                # If it's not strictly YAML (e.g., templated fragments), just write replaced content
                yaml_content = None

            if yaml_content is not None:
                with open(file_path, "w", encoding="utf-8") as f:
                    yaml.dump(yaml_content, f, default_flow_style=False)
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

            updated.append(file_path)
            logger.info("Updated template: %s", file_path)

        return {"message": "Template files updated", "updated_files": updated}
    except FileNotFoundError as e:
        logger.error("Template file not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update template files")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update_template_files/")
async def update_template_files_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

# Run kubectl commands asynchronously so the event loop is not blocked
async def run_command(cmd: str) -> Dict[str, str]:
    logger.info("Running command: %s", cmd)
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8").strip(),
        "stderr": stderr.decode("utf-8").strip(),
    }

async def create_k8s_objects_async(user_id: int) -> List[Dict[str, str]]:
    kubeconfig = os.getenv("KUBECONFIG_PATH", "kube-config")
    base_path = f"users/user_{user_id}/k8s-template"
    cmds = [
        f"kubectl apply -f {base_path}/namespace-template.yaml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/configmap-template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/persistentvolumeclaim-template.yaml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/issuer_template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/wordpress-template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/service-template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/certificate-template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/ingress-template.yml --kubeconfig={kubeconfig}",
    ]

    results = []
    for cmd in cmds:
        try:
            res = await run_command(cmd)
            results.append(res)
        except Exception as e:
            logger.exception("Command failed: %s", cmd)
            results.append({"cmd": cmd, "error": str(e)})
    return results

@app.post("/create_k8s_objects/")
async def create_k8s_objects_endpoint(folder_info: FolderInfo):
    results = await create_k8s_objects_async(folder_info.userID)
    return {"message": "Kubernetes objects processed", "details": results}

if __name__ == "__main__":
    # Run with uvicorn when executed directly
    uvicorn.run("copilot_main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
