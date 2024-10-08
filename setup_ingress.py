#!/usr/bin/env python3

import subprocess
import time
import sys
import os

def print_colored(message, color):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "cyan": "\033[96m", "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{message}{colors['reset']}")

def run_command(command, verbose=True):
    if verbose:
        print_colored(f"Running command: {command}", "cyan")
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if verbose:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print_colored(result.stderr, "yellow")
    return result.returncode == 0, result.stdout, result.stderr

def get_yes_no_input(prompt):
    while True:
        response = input(prompt).strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print_colored("Please enter 'yes' or 'no'.", "yellow")

def ensure_namespace_exists(namespace):
    success, _, _ = run_command(f"kubectl get namespace {namespace}", verbose=False)
    if not success:
        print_colored(f"The {namespace} namespace does not exist. Creating it now...", "yellow")
        success, _, _ = run_command(f"kubectl create namespace {namespace}")
        if not success:
            return False
        print_colored(f"{namespace} namespace created successfully.", "green")
    else:
        print_colored(f"{namespace} namespace already exists.", "green")
    
    # Wait for namespace to be fully created
    for _ in range(30):  # Wait up to 30 seconds
        success, output, _ = run_command(f"kubectl get namespace {namespace} -o jsonpath='{{.status.phase}}'", verbose=False)
        if success and output.strip() == "Active":
            return True
        time.sleep(1)
    print_colored(f"Timeout waiting for {namespace} namespace to become active.", "red")
    return False

def install_nginx_ingress_controller():
    print_colored("Installing NGINX Ingress Controller...", "blue")
    
    run_command("helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx")
    run_command("helm repo update")
    
    install_cmd = (
        "helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx "
        "--namespace ingress-nginx --create-namespace "
        "--set controller.service.type=LoadBalancer "
        "--debug"
    )
    success, _, error = run_command(install_cmd)
    if not success:
        print_colored("Failed to install/upgrade NGINX Ingress Controller.", "red")
        print_colored(f"Error: {error}", "red")
        return False
    
    print_colored("NGINX Ingress Controller installation/upgrade command executed.", "green")
    return wait_for_nginx_ingress_ready()

def wait_for_nginx_ingress_ready():
    print_colored("Waiting for NGINX Ingress Controller resources to be ready...", "yellow")
    timeout = 300  # 5 minutes timeout
    start_time = time.time()
    while time.time() - start_time < timeout:
        success, output, _ = run_command(
            "kubectl get pods -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx-controller -o jsonpath='{.items[*].status.phase}'",
            verbose=False
        )
        if success and all(status == "Running" for status in output.split()):
            print_colored("NGINX Ingress Controller pods are running.", "green")
            return True
        print_colored("Waiting for NGINX Ingress Controller pods to be ready...", "yellow")
        time.sleep(10)
    
    print_colored("Timed out waiting for NGINX Ingress Controller pods to be ready.", "red")
    return False

def get_ingress_address(timeout=600):
    print_colored("Retrieving LoadBalancer IP or hostname...", "blue")
    start_time = time.time()
    while time.time() - start_time < timeout:
        success, output, _ = run_command("kubectl get service ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}'", verbose=False)
        if success and output.strip():
            return output.strip()
        
        success, output, _ = run_command("kubectl get service ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'", verbose=False)
        if success and output.strip():
            return output.strip()
        
        print_colored("LoadBalancer IP/hostname not yet assigned. Waiting...", "yellow")
        time.sleep(10)
    
    print_colored("Failed to retrieve LoadBalancer IP or hostname.", "red")
    return None

def check_existing_ingress(namespace, hostname):
    success, output, _ = run_command(f"kubectl get ingress -n {namespace} -o jsonpath='{{.items[?(@.spec.rules[0].host==\"{hostname}\")].metadata.name}}'", verbose=False)
    return output.strip() if success else None

def create_ingress_yaml(namespace, hostname):
    return f"""
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hopsworks-ingress
  namespace: {namespace}
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
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
            name: hopsworks-release-http
            port: 
              number: 28080
"""

def update_ingress(namespace, hostname, existing_ingress):
    ingress_yaml = create_ingress_yaml(namespace, hostname)
    with open('hopsworks-ingress.yaml', 'w') as f:
        f.write(ingress_yaml)
    success, _, error = run_command(f"kubectl apply -f hopsworks-ingress.yaml -n {namespace}")
    if not success:
        print_colored("Failed to update ingress resource.", "red")
        print_colored(f"Error: {error}", "red")
        return False
    print_colored("Ingress resource updated successfully.", "green")
    return True

def create_ingress(namespace, hostname):
    ingress_yaml = create_ingress_yaml(namespace, hostname)
    with open('hopsworks-ingress.yaml', 'w') as f:
        f.write(ingress_yaml)
    success, _, error = run_command(f"kubectl create -f hopsworks-ingress.yaml -n {namespace}")
    if not success:
        print_colored("Failed to create ingress resource.", "red")
        print_colored(f"Error: {error}", "red")
        return False
    print_colored("Ingress resource created successfully.", "green")
    return True

def update_etc_hosts(ingress_address, hostname):
    hosts_entry = f"{ingress_address} {hostname}"
    
    try:
        with open('/etc/hosts', 'a') as hosts_file:
            hosts_file.write(f"\n{hosts_entry}\n")
        print_colored("Successfully updated /etc/hosts file.", "green")
    except PermissionError:
        print_colored("Permission denied when trying to update /etc/hosts.", "yellow")
        use_sudo = get_yes_no_input("Do you want to try updating /etc/hosts using sudo? (yes/no): ")
        if use_sudo:
            sudo_command = f"echo '{hosts_entry}' | sudo tee -a /etc/hosts"
            success, output, error = run_command(sudo_command)
            if success:
                print_colored("Successfully updated /etc/hosts file using sudo.", "green")
            else:
                print_colored("Failed to update /etc/hosts file even with sudo.", "red")
                print_colored(f"Error: {error}", "red")
                print_colored("Please manually add the following entry to your /etc/hosts file:", "yellow")
                print_colored(hosts_entry, "green")
        else:
            print_colored("Please manually add the following entry to your /etc/hosts file:", "yellow")
            print_colored(hosts_entry, "green")
    except Exception as e:
        print_colored(f"An unexpected error occurred: {str(e)}", "red")
        print_colored("Please manually add the following entry to your /etc/hosts file:", "yellow")
        print_colored(hosts_entry, "green")

def setup_ingress(namespace):
    print_colored("\nSetting up ingress for Hopsworks...", "blue")
    
    if not ensure_namespace_exists("ingress-nginx"):
        print_colored("Failed to create or verify ingress-nginx namespace. Exiting.", "red")
        return

    success, _, _ = run_command("kubectl get pods -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx-controller", verbose=False)
    if not success:
        print_colored("NGINX Ingress Controller is not installed or not ready.", "yellow")
        install_nginx = get_yes_no_input("Do you want to install/upgrade NGINX Ingress Controller? (yes/no): ")
        
        if install_nginx:
            if install_nginx_ingress_controller():
                print_colored("NGINX Ingress Controller installed/upgraded successfully.", "green")
            else:
                print_colored("Failed to install/upgrade NGINX Ingress Controller. Please check your cluster logs.", "red")
                sys.exit(1)
        else:
            print_colored("NGINX Ingress Controller installation/upgrade skipped. Exiting.", "yellow")
            sys.exit(0)
    else:
        print_colored("NGINX Ingress Controller is already installed and running.", "green")
    
    ingress_address = get_ingress_address()
    if not ingress_address:
        print_colored("Failed to retrieve LoadBalancer IP or hostname. Please check your cluster configuration.", "red")
        print_colored("You may need to configure the LoadBalancer manually.", "yellow")
        manual_address = input("Enter the IP or hostname for your ingress (leave blank to exit): ").strip()
        if not manual_address:
            sys.exit(1)
        ingress_address = manual_address

    print_colored(f"LoadBalancer IP/hostname: {ingress_address}", "green")
    
    hostname = input("Enter the hostname for Hopsworks (default: hopsworks.ai.local): ").strip() or "hopsworks.ai.local"
    
    existing_ingress = check_existing_ingress(namespace, hostname)
    if existing_ingress:
        print_colored(f"An ingress resource '{existing_ingress}' already exists for host '{hostname}'.", "yellow")
        update = get_yes_no_input("Do you want to update the existing ingress? (yes/no): ")
        if update:
            success = update_ingress(namespace, hostname, existing_ingress)
        else:
            print_colored("Ingress update skipped. Using existing ingress configuration.", "yellow")
            success = True
    else:
        success = create_ingress(namespace, hostname)

    if not success:
        print_colored("Failed to set up ingress. Please check your cluster configuration.", "red")
        return

    print_colored("\nTo access Hopsworks, you need to add an entry to your /etc/hosts file.", "blue")
    print_colored("Here's the line you need to add:", "yellow")
    print_colored(f"\n{ingress_address} {hostname}\n", "green")
    
    update_hosts = get_yes_no_input("Would you like the script to update your /etc/hosts file? (yes/no): ")
    if update_hosts:
        update_etc_hosts(ingress_address, hostname)
    else:
        print_colored("Please manually add the entry to your /etc/hosts file.", "yellow")
    
    print_colored(f"\nIngress setup complete. You can access Hopsworks UI at http://{hostname}", "green")
    print_colored("Note: It may take a few minutes for the ingress to become fully operational.", "yellow")
    
    return hostname, ingress_address

def main():
    namespace = input("Enter the namespace where Hopsworks is installed (default: hopsworks): ").strip() or "hopsworks"
    hostname, ingress_address = setup_ingress(namespace)
    print_colored("\nIngress setup completed successfully!", "green")
    print_colored(f"Hopsworks should be accessible at: http://{hostname}", "green")
    print_colored(f"Ingress address: {ingress_address}", "green")
    print_colored("\nIf you didn't update your /etc/hosts file, remember to add this line:", "yellow")
    print_colored(f"{ingress_address} {hostname}", "green")

if __name__ == "__main__":
    main()