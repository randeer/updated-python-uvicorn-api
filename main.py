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
import subprocess

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# MySQL database configuration
db_config = {
    'host': 'docker.lala-1992.xyz',
    'user': 'root',
    'password': 'rashmikamanawadu',
    'db': 'myapidb',
    'port': 3306
}

class UserInfo(BaseModel):
    username: str
    email: str
    userID: int
    userDomain: str

async def insert_into_database(user_info: UserInfo):
    conn = None
    try:
        logger.info(f"Attempting to connect to database with config: {db_config}")
        conn = await aiomysql.connect(**db_config)
        logger.info("Database connection established")
        
        async with conn.cursor() as cursor:
            # Check if userID already exists
            sql_check = "SELECT * FROM users WHERE userID = %s"
            await cursor.execute(sql_check, (user_info.userID,))
            existing_user = await cursor.fetchone()
            if existing_user is not None:
                return {"message": f"Username with userID {user_info.userID} already exists."}
            # Insert new user
            sql_insert = "INSERT INTO users (username, userID, email, domain_name) VALUES (%s, %s, %s, %s)"
            await cursor.execute(sql_insert, (user_info.username, user_info.userID, user_info.email, user_info.userDomain))
            await conn.commit()
            return {"message": "User inserted successfully."}
    except aiomysql.Error as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")

async def create_wordpress_db(user_info: UserInfo):
    conn = None
    try:
        logger.info(f"Attempting to connect to database with config: {db_config}")
        conn = await aiomysql.connect(**db_config)
        logger.info("Database connection established")
        
        async with conn.cursor() as cursor:
            # Create database
            db_name = f"user{user_info.userID}"
            sql_create_db = f"CREATE DATABASE IF NOT EXISTS {db_name}"
            await cursor.execute(sql_create_db)
            
            # Create user and grant privileges
            db_username = f"user{user_info.userID}"
            db_password = f"password{user_info.userID}"
            sql_create_user = f"CREATE USER IF NOT EXISTS '{db_username}'@'%' IDENTIFIED BY '{db_password}'"
            await cursor.execute(sql_create_user)
            
            sql_grant_privileges = f"GRANT ALL PRIVILEGES ON {db_name}.* TO '{db_username}'@'%'"
            await cursor.execute(sql_grant_privileges)
            
            await cursor.execute("FLUSH PRIVILEGES")
            
            await conn.commit()
            
            return {
                "message": f"WordPress database and user created successfully.",
                "db_name": db_name,
                "db_username": db_username,
                "db_password": db_password,
                "db_hostname": "docker.lala-1992.xyz"
            }
    except aiomysql.Error as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")

@app.post("/push_data_db/create_wordpress_db/")
async def create_wordpress_db_endpoint(user_info: UserInfo):
    try:
        result = await create_wordpress_db(user_info)
        return result
    except HTTPException as he:
        logger.error(f"HTTP exception in create_wordpress_db: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in create_wordpress_db: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create WordPress database: {str(e)}")

@app.post("/create_folder/")
async def create_folder(user_info: UserInfo):
    parent_folder = "users"  # The name of the pre-existing folder
    folder_name = f"user_{user_info.userID}"
    full_path = os.path.join(parent_folder, folder_name)
    
    try:
        # Ensure the parent folder exists
        Path(parent_folder).mkdir(exist_ok=True)
        
        # Create the user folder inside the parent folder
        Path(full_path).mkdir(exist_ok=True)
        logger.info(f"Folder '{full_path}' created successfully")
        
        # You can optionally insert the user info into the database here as well
        response = await insert_into_database(user_info)
        
        return {"message": f"Folder '{full_path}' created successfully and {response['message']}"}
    except Exception as e:
        logger.error(f"Failed to create folder: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create folder: {str(e)}")

@app.post("/create_text_file/")
async def create_text_file(user_info: UserInfo):
    filename = f"user_{user_info.userID}.txt"
    file_content = f"Username: {user_info.username}\nEmail: {user_info.email}\nUserID: {user_info.userID}\nDomainname: {user_info.userDomain}"
    try:
        # Write to text file
        with open(filename, 'w') as file:
            file.write(file_content)
        logger.info(f"Text file '{filename}' created")
        
        # Insert into database asynchronously
        response = await insert_into_database(user_info)
        return {"message": f"Text file '{filename}' created and {response['message']}"}
    except HTTPException as he:
        logger.error(f"HTTP exception: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in create_text_file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create file or insert into database: {str(e)}")

@app.post("/push_data_db/")
async def push_data_db(user_info: UserInfo):
    try:
        response = await insert_into_database(user_info)
        return response
    except HTTPException as he:
        logger.error(f"HTTP exception in push_data_db: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in push_data_db: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to insert into database: {str(e)}")

class FolderInfo(BaseModel):
    userID: int

@app.post("/copy_template_folder/")
async def copy_template_folder(folder_info: FolderInfo):
    parent_folder = "users"
    user_folder = f"user_{folder_info.userID}"
    full_path = os.path.join(parent_folder, user_folder)
    template_folder = "k8s-template"
    
    try:
        # Check if the user folder exists
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"User folder '{full_path}' not found")
        
        # Copy the entire k8s-template folder to the user folder
        dst_folder = os.path.join(full_path, os.path.basename(template_folder))
        shutil.copytree(template_folder, dst_folder)
        
        logger.info(f"Copied {template_folder} to {dst_folder}")
        return {"message": f"Template folder copied to '{dst_folder}' successfully"}
    except FileNotFoundError as e:
        logger.error(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to copy template folder: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to copy template folder: {str(e)}")

async def update_template_files(user_info: UserInfo):
    parent_folder = "users"
    user_folder = f"user_{user_info.userID}"
    template_folder = os.path.join(parent_folder, user_folder, "k8s-template")
    issuer_template_file = os.path.join(template_folder, "issuer_template.yml")
    namespace_template_file = os.path.join(template_folder, "namespace-template.yaml")
    pvc_template_file = os.path.join(template_folder, "persistentvolumeclaim-template.yaml")
    configmap_template_file = os.path.join(template_folder, "configmap-template.yml")
    wordpress_template_file = os.path.join(template_folder, "wordpress-template.yml")
    service_template_file = os.path.join(template_folder, "service-template.yml")
    ingress_template_file = os.path.join(template_folder, "ingress-template.yml")
    certificate_template_file = os.path.join(template_folder, "certificate-template.yml")
    mysql_template_file = os.path.join(template_folder, "mysql-template.yaml")
    mysqlservice_template_file = os.path.join(template_folder, "mysql-service-template.yaml")
    
    try:
        # Update issuer_template.yml
        with open(issuer_template_file, 'r') as file:
            issuer_content = file.read()
        
        issuer_content = issuer_content.replace('{{ userID }}', str(user_info.userID))
        issuer_content = issuer_content.replace('{{ email }}', user_info.email)
        
        issuer_yaml_content = yaml.safe_load(issuer_content)
        
        with open(issuer_template_file, 'w') as file:
            yaml.dump(issuer_yaml_content, file, default_flow_style=False)
        
        logger.info(f"Issuer template file '{issuer_template_file}' updated successfully")

        # Update namespace-template.yaml
        with open(namespace_template_file, 'r') as file:
            namespace_content = file.read()
        
        namespace_content = namespace_content.replace('{{ userID }}', str(user_info.userID))
        
        namespace_yaml_content = yaml.safe_load(namespace_content)
        
        with open(namespace_template_file, 'w') as file:
            yaml.dump(namespace_yaml_content, file, default_flow_style=False)
        
        logger.info(f"Namespace template file '{namespace_template_file}' updated successfully")

        # Update persistentvolumeclaim-template.yaml
        with open(pvc_template_file, 'r') as file:
            pvc_content = file.read()
        
        pvc_content = pvc_content.replace('{{ userID }}', str(user_info.userID))
        
        pvc_yaml_content = yaml.safe_load(pvc_content)
        
        with open(pvc_template_file, 'w') as file:
            yaml.dump(pvc_yaml_content, file, default_flow_style=False)
        
        logger.info(f"PersistentVolumeClaim template file '{pvc_template_file}' updated successfully")

        # Update configmap-template.yml
        with open(configmap_template_file, 'r') as file:
            configmap_content = file.read()
        
        configmap_content = configmap_content.replace('{{ userID }}', str(user_info.userID))
        configmap_content = configmap_content.replace('{{ userDomain }}', user_info.userDomain)
        
        configmap_yaml_content = yaml.safe_load(configmap_content)
        
        with open(configmap_template_file, 'w') as file:
            yaml.dump(configmap_yaml_content, file, default_flow_style=False)
        
        logger.info(f"ConfigMap template file '{configmap_template_file}' updated successfully")

        # Update wordpress-template.yml
        with open(wordpress_template_file, 'r') as file:
            wordpress_content = file.read()
        
        wordpress_content = wordpress_content.replace('{{ userID }}', str(user_info.userID))
        
        wordpress_yaml_content = yaml.safe_load(wordpress_content)
        
        with open(wordpress_template_file, 'w') as file:
            yaml.dump(wordpress_yaml_content, file, default_flow_style=False)
        
        logger.info(f"WordPress template file '{wordpress_template_file}' updated successfully")

        # Update service-template.yml
        with open(service_template_file, 'r') as file:
            service_content = file.read()
        
        service_content = service_content.replace('{{ userID }}', str(user_info.userID))
        
        service_yaml_content = yaml.safe_load(service_content)
        
        with open(service_template_file, 'w') as file:
            yaml.dump(service_yaml_content, file, default_flow_style=False)
        
        logger.info(f"Service template file '{service_template_file}' updated successfully")

        # Update ingress-template.yml
        with open(ingress_template_file, 'r') as file:
            ingress_content = file.read()
        
        ingress_content = ingress_content.replace('{{ userID }}', str(user_info.userID))
        ingress_content = ingress_content.replace('{{ userDomain }}', user_info.userDomain)
        
        ingress_yaml_content = yaml.safe_load(ingress_content)
        
        with open(ingress_template_file, 'w') as file:
            yaml.dump(ingress_yaml_content, file, default_flow_style=False)
        
        logger.info(f"Ingress template file '{ingress_template_file}' updated successfully")

        # Update certificate-template.yml
        with open(certificate_template_file, 'r') as file:
            certificate_content = file.read()
        
        certificate_content = certificate_content.replace('{{ userID }}', str(user_info.userID))
        certificate_content = certificate_content.replace('{{ userDomain }}', user_info.userDomain)
        
        certificate_yaml_content = yaml.safe_load(certificate_content)
        
        with open(certificate_template_file, 'w') as file:
            yaml.dump(certificate_yaml_content, file, default_flow_style=False)
        
        logger.info(f"Certificate template file '{certificate_template_file}' updated successfully")

        # Update mysql-template.yml
        with open(mysql_template_file, 'r') as file:
            mysql_content = file.read()
        
        mysql_content = mysql_content.replace('{{ userID }}', str(user_info.userID))
        
        mysql_yaml_content = yaml.safe_load(mysql_content)
        
        with open(mysql_template_file, 'w') as file:
            yaml.dump(mysql_yaml_content, file, default_flow_style=False)
        
        logger.info(f"Mysql template file '{mysql_template_file}' updated successfully")

        # Update mysql-service-template.yml
        with open(mysqlservice_template_file, 'r') as file:
            mysqlservice_content = file.read()
        
        mysqlservice_content = mysqlservice_content.replace('{{ userID }}', str(user_info.userID))
        
        mysqlservice_yaml_content = yaml.safe_load(mysqlservice_content)
        
        with open(mysqlservice_template_file, 'w') as file:
            yaml.dump(mysqlservice_yaml_content, file, default_flow_style=False)
        
        logger.info(f"Mysql-service template file '{mysqlservice_template_file}' updated successfully")

        return {"message": "Template files updated successfully"}

    except FileNotFoundError as e:
        logger.error(f"Template file not found: {str(e)}")
        raise HTTPException(status_code=404, detail=f"Template file not found: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to update template files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update template files: {str(e)}")
    
async def create_k8s_objects(user_id: int):
    kubeconfig = "kube-config"
    base_path = f"users/user_{user_id}/k8s-template"
    commands = [
        f"kubectl apply -f {base_path}/namespace-template.yaml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/configmap-template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/persistentvolumeclaim-template.yaml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/issuer_template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/wordpress-template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/service-template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/certificate-template.yml --kubeconfig={kubeconfig}",
        f"kubectl apply -f {base_path}/ingress-template.yml --kubeconfig={kubeconfig}"
    ]
    
    results = []
    for cmd in commands:
        try:
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            results.append(f"Command '{cmd}' executed successfully: {result.stdout}")
        except subprocess.CalledProcessError as e:
            error_message = f"Command '{cmd}' failed with error: {e.stderr}"
            logger.error(error_message)
            results.append(error_message)
    
    return results


@app.post("/update_template_file/")
async def update_template_file_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

@app.post("/update_template_files/")
async def update_template_files_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

@app.post("/update_template_files/")
async def update_template_files_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

@app.post("/update_template_files/")
async def update_template_files_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

@app.post("/update_template_files/")
async def update_template_files_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

@app.post("/update_template_files/")
async def update_template_files_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

@app.post("/update_template_files/")
async def update_template_files_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

@app.post("/update_template_files/")
async def update_template_files_endpoint(user_info: UserInfo):
    return await update_template_files(user_info)

@app.post("/create_k8s_objects/")
async def create_k8s_objects_endpoint(folder_info: FolderInfo):
    try:
        results = await create_k8s_objects(folder_info.userID)
        return {"message": "Kubernetes objects created", "details": results}
    except Exception as e:
        logger.error(f"Failed to create Kubernetes objects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create Kubernetes objects: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)