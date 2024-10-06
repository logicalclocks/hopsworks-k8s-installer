#!/usr/bin/env python3

import os
import sys
from datetime import datetime
import uuid
import subprocess
import json
import shutil
import argparse
import time
import itertools
import urllib.request
import urllib.error

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
        data_json = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(SERVER_URL, data=data_json, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            response.read().decode('utf-8')
            print_colored("User data sent successfully.", "green")
            return True, installation_id
    except urllib.error.URLError as e:
        print_colored(f"Failed to communicate with server: {e}", "red")
        return False, None

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

def install_hopsworks_dev(namespace):
    print_colored("\nPreparing to install Hopsworks (Development Setup)...", "blue")
    
    print_colored("Adding Hopsworks Helm repository...", "blue")
    helm_repo_add_cmd = f"helm repo add hopsworks {HOPSWORKS_HELM_REPO_URL}"
    success, output, error = run_command(helm_repo_add_cmd)
    if not success:
        print_colored("Failed to add Helm repository.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    success, output, error = run_command("helm repo update")
    if not success:
        print_colored("Failed to update Helm repositories.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    if os.path.exists('hopsworks'):
        shutil.rmtree('hopsworks')
    
    print_colored("Downloading and extracting the latest Hopsworks chart...", "blue")
    helm_pull_cmd = "helm pull hopsworks/hopsworks --untar"
    success, output, error = run_command(helm_pull_cmd)
    if not success:
        print_colored("Failed to pull Hopsworks chart.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    print_colored("Installing Hopsworks...", "blue")
    helm_command = (
        f"helm install hopsworks-release ./hopsworks "
        f"--namespace={namespace} "
        f"--values hopsworks/values.services.yaml "
        f"--values hopsworks/values.yaml "
        f"--values hopsworks/values.dev.yaml "
        f"--timeout 30m "
        f"--wait "
        f"--debug"
    )
    
    success, output, error = run_command(helm_command)
    
    if success:
        print_colored("✓ Hopsworks (Development Setup) installed successfully!", "green")
    else:
        print_colored("✗ Failed to install Hopsworks", "red")
        print(output)
        print_colored(f"Error: {error}", "red")
        print_colored("\nIf the issue persists, please contact Hopsworks support with the error message and your installation ID.", "yellow")

def setup_ingress(namespace):
    print_colored("\nSetting up ingress for Hopsworks...", "blue")
    
    print_colored("Please note that ingress setup may vary depending on your cloud provider.", "yellow")
    print_colored("Ensure that you have an ingress controller installed and properly configured.", "yellow")
    
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

def wait_for_installation(namespace, timeout=1800):
    print_colored("\nWaiting for Hopsworks installation to complete...", "blue")
    start_time = time.time()
    spinner = itertools.cycle(['-', '/', '|', '\\'])
    
    while time.time() - start_time < timeout:
        success, output, error = run_command(f"kubectl get pods -n {namespace} -o jsonpath='{{.items[*].status.phase}}'", verbose=False)
        if success and all(status == "Running" for status in output.split()):
            print("\nAll pods are running.")
            return True
        
        sys.stdout.write(next(spinner))
        sys.stdout.flush()
        sys.stdout.write('\b')
        time.sleep(1)
    
    print("\nTimeout reached. Installation may not be complete.")
    return False

def namespace_exists(namespace):
    cmd = f"kubectl get namespace {namespace}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0

def delete_namespace(namespace):
    cmd = f"kubectl delete namespace {namespace}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0

def run_installation_diagnostics(namespace):
    print_colored("\nRunning installation diagnostics...", "blue")
    
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
            installation_id = "unknown"
    else:
        print_colored("Skipping user data collection and sending as per --no-send-data flag.", "yellow")
        installation_id = "unknown"
    
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
    
    # Install Hopsworks
    install_hopsworks_dev(namespace)
    
    # Set up ingress
    setup_ingress(namespace)
    
    # Wait for installation
    if not wait_for_installation(namespace):
        print_colored("Installation is taking longer than expected.", "yellow")
        while True:
            choice = input("Do you want to (w)ait more, run (d)iagnostics, or (c)lean up? (w/d/c): ").lower()
            if choice == 'w':
                if wait_for_installation(namespace, timeout=600):  # Wait for 10 more minutes
                    break
            elif choice == 'd':
                run_installation_diagnostics(namespace)
            elif choice == 'c':
                cleanup_installation(namespace)
                break
            else:
                print_colored("Invalid choice. Please enter 'w', 'd', or 'c'.", "red")
    
    print_colored("\nInstallation completed successfully!", "green")
    print_colored("If you need any assistance, please contact our support team.", "blue")
    
    # Offer to run diagnostics
    print_colored("\nWould you like to run diagnostics? (yes/no): ", "yellow")
    run_diagnostics = input().strip().lower() == 'yes'
    
    if run_diagnostics:
        run_installation_diagnostics(namespace)

if __name__ == "__main__":
    main()
