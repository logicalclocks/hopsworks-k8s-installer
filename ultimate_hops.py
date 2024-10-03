#!/usr/bin/env python3

import os
import sys
import requests
from datetime import datetime
import uuid
import getpass
import subprocess
import json
import yaml

# Utility functions
def print_colored(message, color):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "magenta": "\033[95m", "cyan": "\033[96m",
        "white": "\033[97m", "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{message}{colors['reset']}")

def run_command(command, verbose=True):
    if verbose:
        print_colored(f"Running command: {command}", "cyan")
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if verbose:
        print(result.stdout)
    return result.returncode == 0, result.stdout

def get_user_input(prompt, options=None):
    while True:
        response = input(prompt).strip()
        if options is None or response.lower() in options:
            return response
        else:
            print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "red")

HOPSWORKS_LOGO = """
 _   _                                      _        
| | | |                                    | |       
| |_| | ___  _ __  _____      _____  _ __  | | _____ 
|  _  |/ _ \\| '_ \\/ __\\ \\ /\\ / / _ \\| '__| | |/ / __|
| | | | (_) | |_) \\__ \\\\ V  V / (_) | |    |   <\\__ \\
\\_| |_/\\___/| .__/|___/ \\_/\\_/ \\___/|_|    |_|\\_\\___/
            | |                                      
            |_|                                      
"""

SERVER_URL = "https://magiclex--hopsworks-installation-hopsworks-installation.modal.run/"
STARTUP_LICENSE_URL = "https://www.hopsworks.ai/startup-license"
EVALUATION_LICENSE_URL = "https://www.hopsworks.ai/evaluation-license"
HOPSWORKS_HELM_REPO_URL = "https://nexus.hops.works/repository/hopsworks-helm/"
NEXUS_USER = "deploy"  # Replace with your Nexus username
NEXUS_PASSWORD = "t4Jkky7ZsVYU"  # Replace with your Nexus password

def check_requirements():
    print_colored("Checking system requirements...", "blue")
    requirements = [("helm", "helm version"), ("kubectl", "kubectl version --client")]
    for tool, command in requirements:
        success, _ = run_command(command, verbose=False)
        if not success:
            print_colored(f"✗ {tool} is not installed or not configured properly", "red")
            sys.exit(1)
    print_colored("All system requirements are met.", "green")

def get_user_info():
    print_colored("\nPlease provide the following information:", "blue")
    name = input("Your name: ")
    email = input("Your email address: ")
    company = input("Your company name: ")
    
    print_colored("\nPlease choose a license agreement:", "blue")
    print("1. Startup Software License")
    print("2. Evaluation Agreement")
    
    choice = get_user_input("Enter 1 or 2: ", ["1", "2"])
    license_type = "Startup" if choice == "1" else "Evaluation"
    license_url = STARTUP_LICENSE_URL if choice == "1" else EVALUATION_LICENSE_URL
    
    print_colored(f"\nPlease review the {license_type} License Agreement at:", "blue")
    print_colored(license_url, "blue")
    
    agreement = get_user_input("\nDo you agree to the terms and conditions? (yes/no): ", ["yes", "no"]).lower() == "yes"
    return name, email, company, license_type, agreement

def send_user_data(name, email, company, license_type, agreed_to_license):
    print_colored("\nSending user data...", "blue")
    installation_id = str(uuid.uuid4())
    data = {
        "name": name, "email": email, "company": company,
        "license_type": license_type, "agreed_to_license": agreed_to_license,
        "installation_id": installation_id,
        "action": "install_hopsworks",
        "installation_date": datetime.now().isoformat()
    }
    try:
        response = requests.post(SERVER_URL, json=data)
        response.raise_for_status()
        print_colored("User data sent successfully.", "green")
        return True, installation_id
    except requests.exceptions.RequestException as e:
        print_colored(f"Failed to communicate with server: {e}", "red")
        return False, None

def select_cloud_provider():
    print_colored("\nSelect your cloud provider:", "blue")
    print("1. OVH")
    # Add more cloud providers here as they become available
    
    choice = get_user_input("Enter the number of your cloud provider: ", ["1"])
    if choice == "1":
        return "OVH"
    # Add more conditions for other cloud providers
    
    return None

def setup_kubeconfig():
    print_colored("\nSetting up kubeconfig...", "blue")
    default_path = os.path.expanduser("~/Downloads/kubeconfig.yml")
    kubeconfig_path = input(f"Enter the path to your kubeconfig file (default: {default_path}): ").strip() or default_path
    kubeconfig_path = os.path.expanduser(kubeconfig_path)
    
    if not os.path.exists(kubeconfig_path):
        print_colored(f"The file {kubeconfig_path} does not exist. Please check the path and try again.", "red")
        sys.exit(1)
    
    os.environ["KUBECONFIG"] = kubeconfig_path
    print_colored(f"KUBECONFIG environment variable set to: {kubeconfig_path}", "blue")
    
    try:
        os.chmod(kubeconfig_path, 0o600)
    except Exception as e:
        print_colored(f"Failed to update kubeconfig file permissions: {str(e)}", "yellow")
        print_colored(f"Please manually run: chmod 600 {kubeconfig_path}", "yellow")
    
    success, _ = run_command("kubectl get nodes")
    if not success:
        print_colored("Failed to set up kubeconfig. Please check the file and try again.", "red")
        sys.exit(1)
    print_colored("Kubeconfig setup successful.", "green")

def setup_secrets(namespace="hopsworks"):
    print_colored("\nSetting up secrets...", "blue")
    
    # Docker registry credentials
    print_colored("Setting up Docker registry credentials...", "blue")
    docker_server = input("Enter Docker registry server (e.g., docker.hops.works): ")
    docker_username = input("Enter Docker registry username: ")
    docker_password = getpass.getpass("Enter Docker registry password: ")
    docker_email = input("Enter Docker registry email: ")
    
    run_command(f"kubectl create secret docker-registry regcred "
                f"--namespace={namespace} "
                f"--docker-server={docker_server} "
                f"--docker-username={docker_username} "
                f"--docker-password={docker_password} "
                f"--docker-email={docker_email} "
                f"--dry-run=client -o yaml | kubectl apply -f -")
    
    print_colored("Docker registry secret 'regcred' created/updated successfully.", "green")
    
    # Object storage credentials
    print_colored("\nSetting up object storage credentials...", "blue")
    access_key = input("Enter your object storage access key: ")
    secret_key = getpass.getpass("Enter your object storage secret key: ")
    
    run_command(f"kubectl create secret generic object-store-credentials "
                f"--namespace={namespace} "
                f"--from-literal=access-key-id={access_key} "
                f"--from-literal=secret-access-key={secret_key} "
                f"--dry-run=client -o yaml | kubectl apply -f -")
    
    print_colored("Secret 'object-store-credentials' created/updated successfully.", "green")

    # OVH credentials secret
    print_colored("\nCreating OVH credentials secret...", "blue")
    run_command(f"kubectl create secret generic ovh-credentials "
                f"--namespace={namespace} "
                f"--from-literal=access-key-id={access_key} "
                f"--from-literal=secret-access-key={secret_key} "
                f"--dry-run=client -o yaml | kubectl apply -f -")
    print_colored("Secret 'ovh-credentials' created/updated successfully.", "green")

    return access_key, secret_key

def generate_values_file(config):
    print_colored("\nGenerating values.ovh.yaml file...", "blue")
    values = {
        "global": {
            "_hopsworks": {
                "storageClassName": config.get("storage_class", None),
                "cloudProvider": "OVH",
                "managedDockerRegistery": {
                    "enabled": True,
                    "domain": config["docker_registry"]["domain"],
                    "namespace": config["docker_registry"]["namespace"],
                    "credHelper": {
                        "enabled": False,
                        "secretName": ""
                    }
                },
                "managedObjectStorage": {
                    "enabled": True,
                    "s3": {
                        "bucket": {
                            "name": config["object_storage"]["bucket_name"]
                        },
                        "region": config["object_storage"]["region"],
                        "endpoint": config["object_storage"]["endpoint"],
                        "secret": {
                            "name": "ovh-credentials",
                            "access_key_id": "access-key-id",
                            "secret_access_key": "secret-access-key"
                        }
                    }
                },
                "minio": {
                    "enabled": False
                }
            }
        },
        "hopsworks": {
            "variables": {
                "docker_operations_managed_docker_secrets": "ovhregcred",
                "docker_operations_image_pull_secrets": "regcred,ovhregcred"
            },
            "dockerRegistry": {
                "preset": {
                    "usePullPush": False,
                    "secrets": ["regcred", "ovhregcred"]
                }
            }
        },
        "hopsfs": {
            "objectStorage": {
                "enabled": True,
                "provider": "S3",
                "s3": {
                    "bucket": {
                        "name": config["object_storage"]["bucket_name"]
                    },
                    "region": config["object_storage"]["region"],
                    "endpoint": config["object_storage"]["endpoint"],
                    "signingRegion": config["object_storage"]["region"]
                }
            }
        },
        "rondb": {
            "restoreFromBackup": {
                "backupId": None,
                "objectStorageProvider": "s3",
                "excludeDatabases": [],
                "excludeTables": [],
                "s3": {
                    "keyCredentialsSecret": {
                        "name": "ovh-credentials",
                        "key": "access-key-id"
                    },
                    "secretCredentialsSecret": {
                        "name": "ovh-credentials",
                        "key": "secret-access-key"
                    },
                    "bucketName": config["object_storage"]["bucket_name"],
                    "region": config["object_storage"]["region"],
                    "serverSideEncryption": "aws:kms"
                }
            },
            "backups": {
                "enabled": True,
                "schedule": "0 3 * * mon",
                "s3": {
                    "bucketName": config["object_storage"]["bucket_name"],
                    "region": config["object_storage"]["region"],
                    "endpoint": config["object_storage"]["endpoint"],
                    "signingRegion": config["object_storage"]["region"],
                    "keyCredentialsSecret": {
                        "name": "ovh-credentials",
                        "key": "access-key-id"
                    },
                    "secretCredentialsSecret": {
                        "name": "ovh-credentials",
                        "key": "secret-access-key"
                    },
                    "serverSideEncryption": ""
                }
            }
        },
        "olk": {
            "opensearch": {
                "backup": {
                    "enabled": True,
                    "repositories": {
                        "default": {
                            "snapshot_name": "opensearch",
                            "s3": {
                                "endpoint": config["object_storage"]["endpoint"],
                                "path_style_access": True,
                                "protocol": "https",
                                "region": config["object_storage"]["region"]
                            },
                            "settings": {
                                "base_path": "opensearch-backup",
                                "bucket": config["object_storage"]["bucket_name"],
                                "client": "default",
                                "path_style_access": True,
                                "endpoint": config["object_storage"]["endpoint"],
                                "protocol": "https",
                                "region": config["object_storage"]["region"]
                            },
                            "credentials": {
                                "secret_from": "ovh-credentials"
                            },
                            "schedule": {
                                "cron": "0 0 * * *"
                            },
                            "backup_payload": {
                                "indices": "*",
                                "ignore_unavailable": True,
                                "include_global_state": True,
                                "partial": False
                            }
                        }
                    }
                }
            }
        }
    }

    with open('values.ovh.yaml', 'w') as f:
        yaml.dump(values, f)
    print_colored("Generated values.ovh.yaml successfully.", "green")

def configure_storage_class():
    print_colored("\nConfiguring Storage Class...", "blue")
    storage_class = input("Enter the storage class to use (leave empty for default): ")
    if storage_class:
        print_colored(f"Storage class set to: {storage_class}", "green")
    else:
        print_colored("Using default storage class.", "yellow")
    return storage_class

def configure_ovh_object_storage():
    print_colored("\nConfiguring OVH Object Storage...", "blue")
    bucket_name = input("Enter your OVH Object Storage bucket name: ")
    region = input("Enter your OVH Object Storage region (e.g., SBG, DE): ")
    endpoint = input("Enter your OVH Object Storage endpoint URL: ")
    print_colored("OVH Object Storage configured successfully.", "green")
    return {
        "bucket_name": bucket_name,
        "region": region,
        "endpoint": endpoint
    }

def setup_ovh_docker_registry():
    print_colored("\nSetting up OVH Docker Registry...", "blue")
    registry_url = input("Enter your OVH Docker Registry URL: ")
    robot_name = input("Enter the robot account name (e.g., robot$hopsworks+helm): ")
    robot_password = getpass.getpass("Enter the robot account password: ")
    
    run_command(f"kubectl create secret docker-registry ovhregcred "
                f"--docker-server={registry_url} "
                f"--docker-username={robot_name} "
                f"--docker-password={robot_password} "
                f"--namespace=hopsworks "
                f"--dry-run=client -o yaml | kubectl apply -f -")
    print_colored("OVH Docker Registry configured successfully.", "green")
    return {
        "domain": registry_url,
        "namespace": "hopsworks"
    }

def namespace_exists(namespace):
    cmd = f"kubectl get namespace {namespace}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0

def delete_namespace(namespace):
    cmd = f"kubectl delete namespace {namespace}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0

def install_hopsworks_ovh():
    print_colored("\nPreparing to install Hopsworks on OVH...", "blue")
    
    namespace = "hopsworks"
    
    print_colored("Adding Hopsworks Helm repository...", "blue")
    helm_repo_add_cmd = (
        f"helm repo add hopsworks {HOPSWORKS_HELM_REPO_URL} "
        f"--username {NEXUS_USER} --password {NEXUS_PASSWORD}"
    )
    success, output = run_command(helm_repo_add_cmd)
    if not success:
        print_colored("Failed to add Helm repository with provided credentials.", "red")
        sys.exit(1)
    run_command("helm repo update")
    
    print_colored("Proceeding with Hopsworks installation...", "blue")
    
    helm_command = (f"helm install hopsworks-release hopsworks/hopsworks "
                    f"--wait --timeout=600s --namespace={namespace} "
                    f"--values values.ovh.yaml --devel")
    
    success, output = run_command(helm_command)
    
    if success:
        print_colored("✓ Hopsworks installed successfully!", "green")
    else:
        print_colored("✗ Failed to install Hopsworks", "red")
        print(output)
        print_colored("\nIf the issue persists, please contact Hopsworks support with the error message and your installation ID.", "yellow")

def setup_port_forwarding(namespace):
    print_colored("\nSetting up port forwarding...", "blue")
    
    service_name = "hopsworks"
    cmd = f"kubectl get service {service_name} -n {namespace} -o json"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print_colored(f"Failed to get service '{service_name}' in namespace '{namespace}'.", "red")
        print_colored("Please check the service name and try again.", "yellow")
        return
    
    service = json.loads(result.stdout)
    ports = service.get('spec', {}).get('ports', [])
    if not ports:
        print_colored(f"No ports found for service '{service_name}'.", "red")
        return
    port = ports[0]['port']
    
    local_port = 8080
    target_port = port
    
    print_colored(f"Forwarding local port {local_port} to service '{service_name}' port {target_port}...", "blue")
    cmd = f"kubectl port-forward svc/{service_name} -n {namespace} {local_port}:{target_port}"
    
    # Run the command in a subprocess
    process = subprocess.Popen(cmd, shell=True)
    
    print_colored(f"Port forwarding set up successfully. You can access Hopsworks UI at http://localhost:{local_port}", "green")
    print_colored("Press Ctrl+C to stop port forwarding and exit.", "yellow")
    
    try:
        process.wait()
    except KeyboardInterrupt:
        print_colored("\nStopping port forwarding...", "blue")
        process.terminate()
        process.wait()
        print_colored("Port forwarding stopped.", "green")

def main():
    print_colored(HOPSWORKS_LOGO, "blue")
    print_colored("Welcome to the Hopsworks Installation Script!", "green")
    
    check_requirements()
    
    name, email, company, license_type, agreement = get_user_info()
    
    if not agreement:
        print_colored("You must agree to the terms and conditions to proceed.", "red")
        sys.exit(1)
    
    success, installation_id = send_user_data(name, email, company, license_type, agreement)
    if success:
        print_colored(f"Installation ID: {installation_id}", "green")
        print_colored("Please keep this ID for your records and support purposes.", "yellow")
    else:
        print_colored("Failed to process user information. Continuing with installation.", "yellow")
    
    cloud_provider = select_cloud_provider()
    
    setup_kubeconfig()
    
    namespace = "hopsworks"
    
    if namespace_exists(namespace):
        print_colored(f"The namespace '{namespace}' already exists.", "yellow")
        delete = get_user_input(f"Do you want to delete the existing '{namespace}' namespace and all its resources? (yes/no): ", ["yes", "no"])
        
        if delete.lower() == "yes":
            print_colored(f"Deleting namespace '{namespace}'...", "blue")
            if delete_namespace(namespace):
                print_colored(f"Namespace '{namespace}' deleted successfully.", "green")
            else:
                print_colored(f"Failed to delete namespace '{namespace}'. Please delete it manually and try again.", "red")
                return
        else:
            print_colored("Installation cancelled.", "yellow")
            return
    
    # Create namespace
    run_command(f"kubectl create namespace {namespace}")
    
    # Setup secrets (common for all cloud providers)
    access_key, secret_key = setup_secrets(namespace)
    
    if cloud_provider == "OVH":
        storage_class = configure_storage_class()
        object_storage_config = configure_ovh_object_storage()
        docker_registry_config = setup_ovh_docker_registry()
        
        # Generate the values.ovh.yaml file
        config = {
            "storage_class": storage_class,
            "object_storage": object_storage_config,
            "docker_registry": docker_registry_config
        }
        generate_values_file(config)
        
        install_hopsworks_ovh()
    else:
        print_colored(f"Unsupported cloud provider: {cloud_provider}", "red")
        sys.exit(1)
    
    # After successful installation, set up port forwarding
    setup_port_forwarding(namespace)
    
    print_colored("\nThank you for installing Hopsworks!", "green")
    print_colored("If you need any assistance, please contact our support team.", "blue")

if __name__ == "__main__":
    main()
