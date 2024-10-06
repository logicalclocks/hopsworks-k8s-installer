#!/usr/bin/env python3

import os
import sys
import subprocess
import time
import json

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
|  _  |/ _ \| '_ \/ __\ \ /\ / / _ \| '__| | |/ / __|
| | | | (_) | |_) \__ \\ V  V / (_) | |    |   <\__ \\
\_| |_/\___/| .__/|___/ \_/\_/ \___/|_|    |_|\_\___/
            | |                                      
            |_|                                      
"""

HOPSWORKS_CHART_VERSION = "4.0.0-rc1"
NAMESPACE = "hopsworks"

def check_requirements():
    print_colored("Checking system requirements...", "blue")
    requirements = [("helm", "helm version"), ("kubectl", "kubectl version --client")]
    for tool, command in requirements:
        success, _ = run_command(command, verbose=False)
        if not success:
            print_colored(f"✗ {tool} is not installed or not configured properly", "red")
            sys.exit(1)
    print_colored("All system requirements are met.", "green")

def install_hopsworks():
    print_colored("\nPreparing to install Hopsworks...", "blue")
    
    print_colored("Updating Helm repositories...", "blue")
    success, _ = run_command("helm repo update")
    if not success:
        print_colored("Failed to update Helm repositories.", "red")
        sys.exit(1)
    
    print_colored("Proceeding with Hopsworks installation...", "blue")
    
    helm_command = (
        f"helm install hopsworks-release hopsworks/hopsworks "
        f"--version {HOPSWORKS_CHART_VERSION} "
        f"--wait --timeout=1800s --namespace={NAMESPACE} "
        f"--values hopsworks/values.services.yaml "
        f"--values hopsworks/values.yaml "
        f"--values hopsworks/values.ovh.yaml --devel"
    )
    
    success, output = run_command(helm_command)
    
    if success:
        print_colored("✓ Hopsworks installed successfully!", "green")
    else:
        print_colored("✗ Failed to install Hopsworks", "red")
        print(output)
        print_colored("\nIf the issue persists, please contact Hopsworks support with the error message.", "yellow")
        sys.exit(1)

def setup_ingress():
    print_colored("\nSetting up ingress for Hopsworks...", "blue")
    
    print_colored("Checking if ingress-nginx is already installed...", "blue")
    success, _ = run_command("kubectl get namespace ingress-nginx", verbose=False)
    if not success:
        print_colored("Installing ingress-nginx via Helm...", "blue")
        helm_commands = [
            "helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx",
            "helm repo update",
            "helm -n ingress-nginx install ingress-nginx ingress-nginx/ingress-nginx --create-namespace"
        ]
        for cmd in helm_commands:
            success, output = run_command(cmd)
            if not success:
                print_colored("Failed to install ingress-nginx.", "red")
                sys.exit(1)
        print_colored("Ingress-nginx installed successfully.", "green")
    else:
        print_colored("Ingress-nginx is already installed. Skipping installation.", "yellow")
    
    print_colored("Creating ingress resource for Hopsworks...", "blue")
    ingress_yaml = f"""
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hopsworks-ingress
  namespace: {NAMESPACE}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
  - host: hopsworks.ai.local
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
    
    success, output = run_command("kubectl apply -f hopsworks-ingress.yaml")
    if not success:
        print_colored("Failed to create ingress resource.", "red")
        print(output)
        sys.exit(1)
    print_colored("Ingress resource created successfully.", "green")
    
    print_colored("Retrieving ingress IP address...", "blue")
    ingress_address = None
    for i in range(30):  # Wait up to 5 minutes
        success, output = run_command(f"kubectl get ingress hopsworks-ingress -n {NAMESPACE} -o jsonpath='{{.status.loadBalancer.ingress[0].ip}}'", verbose=False)
        if success and output.strip():
            ingress_address = output.strip()
            break
        else:
            success, output = run_command(f"kubectl get ingress hopsworks-ingress -n {NAMESPACE} -o jsonpath='{{.status.loadBalancer.ingress[0].hostname}}'", verbose=False)
            if success and output.strip():
                ingress_address = output.strip()
                break
        time.sleep(10)
    if not ingress_address:
        print_colored("Ingress address not available yet. Please wait a few moments and try again.", "yellow")
        ingress_address = input("Enter the ingress IP address or hostname manually: ").strip()
    
    print_colored("Please add the following entry to your /etc/hosts file:", "blue")
    print_colored(f"{ingress_address} hopsworks.ai.local", "green")
    print_colored("This will allow you to access Hopsworks at https://hopsworks.ai.local", "blue")
    input("Press Enter after you have updated your /etc/hosts file.")
    
    print_colored("Ingress setup complete. You can access Hopsworks UI at https://hopsworks.ai.local", "green")

def main():
    print_colored(HOPSWORKS_LOGO, "blue")
    print_colored("Welcome to the Hopsworks Installation Script!", "green")
    
    check_requirements()
    
    if not os.path.exists(NAMESPACE):
        print_colored(f"Creating namespace '{NAMESPACE}'...", "blue")
        run_command(f"kubectl create namespace {NAMESPACE}")
    else:
        print_colored(f"Namespace '{NAMESPACE}' already exists.", "yellow")
    
    install_hopsworks()
    
    setup_ingress()
    
    print_colored("\nThank you for installing Hopsworks!", "green")
    print_colored("If you need any assistance, please contact our support team.", "blue")

if __name__ == "__main__":
    main()