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
import shutil
import argparse
import time

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
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if verbose:
        print(result.stdout)
        if result.stderr:
            print_colored(result.stderr, "yellow")
    return result.returncode == 0, result.stdout, result.stderr

def get_user_input(prompt, options=None):
    while True:
        response = input(prompt).strip()
        if options is None or response.lower() in options:
            return response
        else:
            print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "red")

HOPSWORKS_LOGO = """
██╗  ██╗ ██████╗ ██████╗ ███████╗██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗███████╗
██║  ██║██╔═══██╗██╔══██╗██╔════╝██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝██╔════╝
███████║██║   ██║██████╔╝███████╗██║ █╗ ██║██║   ██║██████╔╝█████╔╝ ███████╗ 
██╔══██║██║   ██║██╔═══╝ ╚════██║██║███╗██║██║   ██║██╔══██╗██╔═██╗ ╚════██║
██║  ██║╚██████╔╝██║     ███████║╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗███████║
╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚══════╝ ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
"""

SERVER_URL = "https://magiclex--hopsworks-installation-hopsworks-installation.modal.run/"
STARTUP_LICENSE_URL = "https://www.hopsworks.ai/startup-license"
EVALUATION_LICENSE_URL = "https://www.hopsworks.ai/evaluation-license"
HOPSWORKS_HELM_REPO_URL = "https://nexus.hops.works/repository/hopsworks-helm/"

NEXUS_USER = "deploy"
NEXUS_PASSWORD = "t4Jkky7ZsVYU"

HOPSWORKS_CHART_VERSION = "4.0.0-rc1"

def check_requirements():
    print_colored("Checking system requirements...", "blue")
    requirements = [("helm", "helm version"), ("kubectl", "kubectl version --client")]
    for tool, command in requirements:
        success, output, error = run_command(command, verbose=False)
        if not success:
            print_colored(f"✗ {tool} is not installed or not configured properly", "red")
            print_colored(f"Error: {error}", "red")
            sys.exit(1)
    print_colored("All system requirements are met.", "green")

def get_license_agreement():
    print_colored("\nPlease choose a license agreement:", "blue")
    print("1. Startup Software License")
    print("2. Evaluation Agreement")
    
    choice = get_user_input("Enter 1 or 2: ", ["1", "2"])
    license_type = "Startup" if choice == "1" else "Evaluation"
    license_url = STARTUP_LICENSE_URL if choice == "1" else EVALUATION_LICENSE_URL
    
    print_colored(f"\nPlease review the {license_type} License Agreement at:", "blue")
    print_colored(license_url, "blue")
    
    agreement = get_user_input("\nDo you agree to the terms and conditions? (yes/no): ", ["yes", "no"]).lower() == "yes"
    if not agreement:
        print_colored("You must agree to the terms and conditions to proceed.", "red")
        sys.exit(1)
    return license_type, agreement

def get_user_info():
    print_colored("\nPlease provide the following information:", "blue")
    name = input("Your name: ")
    email = input("Your email address: ")
    company = input("Your company name: ")
    return name, email, company

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
    
    choice = get_user_input("Enter the number of your cloud provider: ", ["1"])
    if choice == "1":
        return "OVH"
    
    return None

def setup_kubeconfig():
    print_colored("\nSetting up kubeconfig...", "blue")
    
    kubeconfig_path = input("Enter the path to your kubeconfig file: ").strip()
    kubeconfig_path = os.path.expanduser(kubeconfig_path)

    if not os.path.exists(kubeconfig_path):
        print_colored(f"The file {kubeconfig_path} does not exist. Please check the path and try again.", "red")
        return None

    # Copy the provided kubeconfig to the default location
    default_kubeconfig = os.path.expanduser("~/.kube/config")
    os.makedirs(os.path.dirname(default_kubeconfig), exist_ok=True)
    shutil.copy2(kubeconfig_path, default_kubeconfig)
    
    print_colored(f"Copied kubeconfig to {default_kubeconfig}", "green")

    try:
        os.chmod(default_kubeconfig, 0o600)
        print_colored("Updated kubeconfig file permissions to 600.", "green")
    except Exception as e:
        print_colored(f"Failed to update kubeconfig file permissions: {str(e)}", "yellow")
        print_colored(f"Please manually run: chmod 600 {default_kubeconfig}", "yellow")

    # Verify the kubeconfig works and get cluster info
    success, output, error = run_command("kubectl config current-context", verbose=False)
    if not success:
        print_colored("Failed to get current context. Please check if the kubeconfig is valid.", "red")
        print_colored("Error output:", "red")
        print(error)
        return None
    
    current_context = output.strip()
    print_colored(f"Current context: {current_context}", "green")

    success, output, error = run_command("kubectl config view --minify -o jsonpath='{.clusters[0].name}'", verbose=False)
    if not success:
        print_colored("Failed to get cluster name. Please check if the kubeconfig is valid.", "red")
        print_colored("Error output:", "red")
        print(error)
        return None
    
    cluster_name = output.strip()
    print_colored(f"Cluster name: {cluster_name}", "green")

    success, output, error = run_command("kubectl get nodes -o custom-columns=NAME:.metadata.name --no-headers", verbose=False)
    if not success:
        print_colored("Failed to get nodes. Please check if the kubeconfig is valid and you have the necessary permissions.", "red")
        print_colored("Error output:", "red")
        print(error)
        return None
    
    nodes = output.strip().split('\n')
    print_colored("Nodes in the cluster:", "green")
    for node in nodes:
        print_colored(f"  - {node}", "cyan")

    print_colored("Kubeconfig setup successful. Connected to the cluster.", "green")
    return default_kubeconfig

def setup_secrets(namespace):
    print_colored("\nSetting up secrets...", "blue")
    
    print_colored("Setting up Docker registry credentials...", "blue")
    default_docker_server = "docker.hops.works"
    docker_server = input(f"Enter Docker registry server (default: {default_docker_server}): ").strip() or default_docker_server

    if docker_server == default_docker_server:
        docker_username = input("Enter your Nexus username: ")
        docker_password = getpass.getpass("Enter your Nexus password: ")
        print_colored(f"Using default Docker registry '{default_docker_server}' with Nexus credentials.", "green")
    else:
        docker_username = input("Enter Docker registry username: ")
        docker_password = getpass.getpass("Enter Docker registry password: ")
    
    success, output, error = run_command(f"kubectl create secret docker-registry regcred "
                f"--namespace={namespace} "
                f"--docker-server={docker_server} "
                f"--docker-username={docker_username} "
                f"--docker-password={docker_password} "
                f"--dry-run=client -o yaml | kubectl apply -f -")
    if not success:
        print_colored("Failed to create Docker registry secret.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    print_colored("Docker registry secret 'regcred' created/updated successfully.", "green")
    
    print_colored("\nSetting up object storage credentials...", "blue")
    access_key = input("Enter your object storage access key: ")
    secret_key = getpass.getpass("Enter your object storage secret key: ")
    
    success, output, error = run_command(f"kubectl create secret generic object-store-credentials "
                f"--namespace={namespace} "
                f"--from-literal=access-key-id={access_key} "
                f"--from-literal=secret-access-key={secret_key} "
                f"--dry-run=client -o yaml | kubectl apply -f -")
    if not success:
        print_colored("Failed to create object storage credentials secret.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    print_colored("Secret 'object-store-credentials' created/updated successfully.", "green")

    print_colored("\nCreating OVH credentials secret...", "blue")
    success, output, error = run_command(f"kubectl create secret generic ovh-credentials "
                f"--namespace={namespace} "
                f"--from-literal=access-key-id={access_key} "
                f"--from-literal=secret-access-key={secret_key} "
                f"--dry-run=client -o yaml | kubectl apply -f -")
    if not success:
        print_colored("Failed to create OVH credentials secret.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    print_colored("Secret 'ovh-credentials' created/updated successfully.", "green")

    return access_key, secret_key

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
    region = input("Enter your OVH Object Storage region (e.g., SBG, DE): ").lower()
    endpoint = f"https://s3.{region}.cloud.ovh.net"
    print_colored(f"OVH Object Storage endpoint set to: {endpoint}", "green")
    print_colored("OVH Object Storage configured successfully.", "green")
    return {
        "bucketName": bucket_name,
        "region": region,
        "endpoint": endpoint
    }

def setup_ovh_docker_registry():
    print_colored("\nSetting up OVH Docker Registry...", "blue")
    registry_url = input("Enter your OVH Docker Registry URL (e.g., xxxxxx.c1.de1.container-registry.ovh.net): ")
    domain = registry_url.split("://")[-1]  # Remove protocol if present
    namespace = input("Enter the namespace for the Docker registry (default: hopsworks): ") or "hopsworks"
    robot_name = input("Enter the robot account name (e.g., robot$hopsworks+helm): ")
    robot_password = getpass.getpass("Enter the robot account password: ")
    
    secret_name = "ovhregcred"
    success, output, error = run_command(f"kubectl create secret docker-registry {secret_name} "
                f"--docker-server={registry_url} "
                f"--docker-username={robot_name} "
                f"--docker-password={robot_password} "
                f"--namespace={namespace} "
                f"--dry-run=client -o yaml | kubectl apply -f -")
    
    if not success:
        print_colored("Failed to configure OVH Docker Registry.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    print_colored("OVH Docker Registry configured successfully.", "green")
    return {
        "domain": domain,
        "namespace": namespace,
        "secretName": secret_name,
        "registryUrl": registry_url
    }

def namespace_exists(namespace):
    cmd = f"kubectl get namespace {namespace}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0

def delete_namespace(namespace):
    cmd = f"kubectl delete namespace {namespace}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0

def install_hopsworks_ovh(namespace, ovh_registry_config, ovh_storage_config, storage_class):
    print_colored("\nPreparing to install Hopsworks on OVH...", "blue")
    
    print_colored("Adding Hopsworks Helm repository...", "blue")
    success, output, error = run_command("helm repo list", verbose=False)
    if success:
        if 'hopsworks' in output:
            print_colored("Helm repository 'hopsworks' already exists. Skipping addition.", "yellow")
        else:
            helm_repo_add_cmd = (
                f"helm repo add hopsworks {HOPSWORKS_HELM_REPO_URL} "
                f"--username {NEXUS_USER} --password {NEXUS_PASSWORD}"
            )
            success, output, error = run_command(helm_repo_add_cmd)
            if not success:
                print_colored("Failed to add Helm repository with provided credentials.", "red")
                print_colored(f"Error: {error}", "red")
                sys.exit(1)
    else:
        print_colored("Failed to list Helm repositories.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    success, output, error = run_command("helm repo update")
    if not success:
        print_colored("Failed to update Helm repositories.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    if os.path.exists('hopsworks'):
        shutil.rmtree('hopsworks')
    
    print_colored("Downloading and extracting the specified Hopsworks chart version...", "blue")
    helm_pull_cmd = f"helm pull hopsworks/hopsworks --version {HOPSWORKS_CHART_VERSION} --untar"
    success, output, error = run_command(helm_pull_cmd)
    if not success:
        print_colored(f"Failed to pull Hopsworks chart version {HOPSWORKS_CHART_VERSION}.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    # Update the values.ovh.yaml file directly
    values_ovh_path = 'hopsworks/values.ovh.yaml'
    with open(values_ovh_path, 'r') as f:
        values_ovh = yaml.safe_load(f)

    # Update the configuration
    values_ovh['global']['_hopsworks']['managedObjectStorage'] = {
        'enabled': True,
        's3': {
            'bucket': {
                'name': ovh_storage_config['bucketName']
            },
            'region': ovh_storage_config['region'],
            'endpoint': ovh_storage_config['endpoint'],
            'secret': {
                'name': 'ovh-credentials',
                'accessKeyId': 'access-key-id',
                'secretKeyId': 'secret-access-key'
            }
        }
    }

    # Update Docker registry configuration
    values_ovh['global']['_hopsworks']['managedDockerRegistery'] = {
        'enabled': True,
        'domain': ovh_registry_config['domain'],
        'namespace': ovh_registry_config['namespace'],
        'credHelper': {
            'enabled': True,
            'secretName': ovh_registry_config['secretName']
        }
    }

    # Update Docker registry secrets
    values_ovh['hopsworks']['dockerRegistry']['preset']['secrets'] = ['regcred', ovh_registry_config['secretName']]
    values_ovh['hopsworks']['variables'] = {
        'docker_operations_image_pull_secrets': f"regcred,{ovh_registry_config['secretName']}",
        'docker_operations_managed_docker_secrets': ovh_registry_config['secretName']
    }

    if storage_class:
        values_ovh['global']['_hopsworks']['storageClassName'] = storage_class

    # Write the updated configuration back to the same file
    with open(values_ovh_path, 'w') as f:
        yaml.dump(values_ovh, f)

    print_colored("Updated values.ovh.yaml with custom configuration.", "green")
    print_colored("Proceeding with Hopsworks installation...", "blue")
    
    helm_command = (
        f"helm install hopsworks-release ./hopsworks "
        f"--wait --timeout=1800s --namespace={namespace} "
        f"--values hopsworks/values.services.yaml "
        f"--values hopsworks/values.yaml "
        f"--values {values_ovh_path} --devel"
    )
    
    success, output, error = run_command(helm_command)
    
    if success:
        print_colored("✓ Hopsworks installed successfully!", "green")
    else:
        print_colored("✗ Failed to install Hopsworks", "red")
        print(output)
        print_colored(f"Error: {error}", "red")
        print_colored("\nIf the issue persists, please contact Hopsworks support with the error message and your installation ID.", "yellow")
        cleanup_installation(namespace)
        sys.exit(1)

def setup_ingress(namespace):
    print_colored("\nSetting up ingress for Hopsworks...", "blue")
    
    print_colored("Installing ingress-nginx via Helm...", "blue")
    helm_commands = [
        "helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx",
        "helm repo update",
        "helm -n ingress-nginx install ingress-nginx ingress-nginx/ingress-nginx --create-namespace"
    ]
    for cmd in helm_commands:
        success, output, error = run_command(cmd)
        if not success:
            print_colored("Failed to install ingress-nginx.", "red")
            print_colored(f"Error: {error}", "red")
            sys.exit(1)
    print_colored("Ingress-nginx installed successfully.", "green")
    
    print_colored("Waiting for ingress-nginx admission webhook service to be ready...", "blue")
    webhook_ready = False
    for i in range(30):  # Wait up to 5 minutes
        success, output, error = run_command("kubectl get svc ingress-nginx-controller-admission -n ingress-nginx", verbose=False)
        if success:
            success, output, error = run_command("kubectl get endpoints ingress-nginx-controller-admission -n ingress-nginx -o json", verbose=False)
            if success:
                endpoints = json.loads(output)
                if endpoints['subsets']:
                    webhook_ready = True
                    print_colored("Ingress-nginx admission webhook service is ready.", "green")
                    break
        time.sleep(10)
    if not webhook_ready:
        print_colored("Ingress-nginx admission webhook service is not ready after 5 minutes.", "red")
        sys.exit(1)
    
    print_colored("Creating ingress resource for Hopsworks...", "blue")
    hostname = input("Enter the hostname for Hopsworks (default: hopsworks.ai.local): ").strip() or "hopsworks.ai.local"
    ingress_yaml = f"""
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hopsworks-ingress
  namespace: {namespace}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
  - host: {hostname}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: hopsworks
            port:
              number: 8182
"""
    with open('hopsworks-ingress.yaml', 'w') as f:
        f.write(ingress_yaml)
    
    success, output, error = run_command("kubectl apply -f hopsworks-ingress.yaml")
    if not success:
        print_colored("Failed to create ingress resource.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    print_colored("Ingress resource created successfully.", "green")
    
    print_colored("Retrieving ingress IP address...", "blue")
    ingress_address = None
    for i in range(30):  # Wait up to 5 minutes
        success, output, error = run_command(f"kubectl get ingress hopsworks-ingress -n {namespace} -o jsonpath='{{.status.loadBalancer.ingress[0].ip}}'", verbose=False)
        if success and output.strip():
            ingress_address = output.strip()
            break
        else:
            success, output, error = run_command(f"kubectl get ingress hopsworks-ingress -n {namespace} -o jsonpath='{{.status.loadBalancer.ingress[0].hostname}}'", verbose=False)
            if success and output.strip():
                ingress_address = output.strip()
                break
        time.sleep(10)
    if not ingress_address:
        print_colored("Ingress address not available yet. Please wait a few moments and try again.", "yellow")
        ingress_address = input("Enter the ingress IP address or hostname manually: ").strip()
    
    print_colored("Please add the following entry to your /etc/hosts file:", "blue")
    print_colored(f"{ingress_address} {hostname}", "green")
    print_colored(f"This will allow you to access Hopsworks at https://{hostname}", "blue")
    input("Press Enter after you have updated your /etc/hosts file.")
    
    print_colored(f"Ingress setup complete. You can access Hopsworks UI at https://{hostname}", "green")


def cleanup_installation(namespace):
    print_colored("\nDo you want to clean up the installation? (yes/no): ", "yellow")
    cleanup_choice = input().strip().lower()
    
    if cleanup_choice != 'yes':
        print_colored("Skipping cleanup. You can manually clean up later if needed.", "yellow")
        return

    print_colored("\nCleaning up installation...", "yellow")
    
    # Uninstall Hopsworks release
    success, output, error = run_command(f"helm uninstall hopsworks-release --namespace {namespace}")
    if not success:
        print_colored(f"Failed to uninstall Hopsworks release. Error: {error}", "red")
    else:
        print_colored("Hopsworks release uninstalled successfully.", "green")
    
    # Delete namespace
    success, output, error = run_command(f"kubectl delete namespace {namespace}")
    if not success:
        print_colored(f"Failed to delete namespace. Error: {error}", "red")
    else:
        print_colored(f"Namespace {namespace} deleted successfully.", "green")
    
    # List and delete any persistent volumes
    success, output, error = run_command("kubectl get pv -o name")
    if success and output:
        for pv in output.split('\n'):
            if pv:
                success, _, error = run_command(f"kubectl delete {pv}")
                if not success:
                    print_colored(f"Failed to delete persistent volume {pv}. Error: {error}", "red")
                else:
                    print_colored(f"Deleted persistent volume {pv}.", "green")
    
    print_colored("Cleanup completed.", "yellow")
def main():
    parser = argparse.ArgumentParser(description="Hopsworks Installation Script")
    parser.add_argument('--no-send-data', action='store_true', help='Do not send user data to the server')
    args = parser.parse_args()
    
    print_colored(HOPSWORKS_LOGO, "blue")
    print_colored("Welcome to the Hopsworks Installation Script!", "green")
    
    check_requirements()
    
    license_type, agreement = get_license_agreement()
    
    if not args.no_send_data:
        name, email, company = get_user_info()
        success, installation_id = send_user_data(name, email, company, license_type, agreement)
        if success:
            print_colored(f"Installation ID: {installation_id}", "green")
            print_colored("Please keep this ID for your records and support purposes.", "yellow")
        else:
            print_colored("Failed to process user information. Continuing with installation.", "yellow")
    else:
        print_colored("Skipping user data collection and sending as per --no-send-data flag.", "yellow")
        installation_id = "unknown"
    
    cloud_provider = select_cloud_provider()
    
    kubeconfig_path = setup_kubeconfig()
    if kubeconfig_path is None:
        print_colored("Failed to set up a valid kubeconfig. Exiting.", "red")
        sys.exit(1)    
        
    namespace = input("Enter the namespace for Hopsworks installation (default: hopsworks): ").strip() or "hopsworks"
    
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
    
    success, output, error = run_command(f"kubectl create namespace {namespace}")
    if not success:
        print_colored(f"Failed to create namespace {namespace}.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    setup_secrets(namespace)
    
    try:
        if cloud_provider == "OVH":
            storage_class = configure_storage_class()
            ovh_storage_config = configure_ovh_object_storage()
            ovh_registry_config = setup_ovh_docker_registry()
            
            install_hopsworks_ovh(namespace, ovh_registry_config, ovh_storage_config, storage_class)
        else:
            print_colored(f"Unsupported cloud provider: {cloud_provider}", "red")
            sys.exit(1)
        
        setup_ingress(namespace)
        
        print_colored("\nInstallation completed successfully!", "green")
        print_colored("If you need any assistance, please contact our support team.", "blue")
        
        # Offer to run diagnostics before cleanup
        print_colored("\nWould you like to run diagnostics before cleaning up? (yes/no): ", "yellow")
        run_diagnostics = input().strip().lower() == 'yes'
        
        if run_diagnostics:
            run_installation_diagnostics(namespace)
        
        # Cleanup installation
        cleanup_installation(namespace)
        
    except Exception as e:
        print_colored(f"An error occurred during installation: {str(e)}", "red")
        print_colored("Running diagnostics before cleanup...", "yellow")
        run_installation_diagnostics(namespace)
        cleanup_installation(namespace)

def run_installation_diagnostics(namespace):
    print_colored("\nRunning installation diagnostics...", "blue")
    
    # Check secrets
    for secret_name in ['regcred', 'object-store-credentials', 'ovh-credentials', 'ovhregcred']:
        success, output, error = run_command(f"kubectl get secret {secret_name} -n {namespace} -o yaml")
        if success:
            print_colored(f"Secret '{secret_name}' found:", "green")
            print(output)
        else:
            print_colored(f"Secret '{secret_name}' not found. Error: {error}", "red")
    
    # Check persistent volumes and claims
    success, output, error = run_command("kubectl get pv")
    print_colored("Persistent Volumes:", "blue")
    print(output)
    
    success, output, error = run_command("kubectl get pvc --all-namespaces")
    print_colored("Persistent Volume Claims:", "blue")
    print(output)
    
    # Check Helm releases
    success, output, error = run_command("helm list --all-namespaces")
    print_colored("Helm Releases:", "blue")
    print(output)
    
    # Additional diagnostics can be added here
    
    print_colored("Diagnostics completed.", "green")

if __name__ == "__main__":
    main()
