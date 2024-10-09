#!/usr/bin/env python3

import subprocess
import time
import sys
import os
import uuid
from datetime import datetime
import yaml
import requests
import json
import shutil
import argparse
import warnings

# Suppress InsecureRequestWarning for unverified HTTPS requests
warnings.simplefilter('ignore', requests.exceptions.InsecureRequestWarning)

# Constants
SERVER_URL = "https://magiclex--hopsworks-installation-hopsworks-installation.modal.run/"
STARTUP_LICENSE_URL = "https://www.hopsworks.ai/startup-license"
EVALUATION_LICENSE_URL = "https://www.hopsworks.ai/evaluation-license"
REQUIRED_NODES = 6

def print_colored(message, color):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "magenta": "\033[95m", "cyan": "\033[96m",
        "white": "\033[97m", "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{message}{colors['reset']}")

def run_command(command, verbose=True, timeout=300):
    if verbose:
        print_colored(f"Running command: {command}", "cyan")
    start_time = time.time()
    try:
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        duration = time.time() - start_time
        if verbose:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print_colored(result.stderr, "yellow")
            print_colored(f"Command completed in {duration:.2f} seconds", "green")
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        print_colored(f"Command timed out after {timeout} seconds: {command}", "red")
        return False, "", "Timeout"

def get_user_input(prompt, options=None):
    while True:
        response = input(prompt + " ").strip()
        if options is None or response.lower() in [option.lower() for option in options]:
            return response
        else:
            print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "yellow")

def get_license_agreement():
    print_colored("\nChoose a license agreement:", "blue")
    print("1. Startup Software License")
    print("2. Evaluation Agreement")

    choice = get_user_input("Enter 1 or 2:", ["1", "2"])
    license_type = "Startup" if choice == "1" else "Evaluation"
    license_url = STARTUP_LICENSE_URL if choice == "1" else EVALUATION_LICENSE_URL

    print_colored(f"\nReview the {license_type} License Agreement at:", "blue")
    print_colored(license_url, "cyan")

    agreement = get_user_input("\nDo you agree to the terms and conditions? (yes/no):", ["yes", "no"]).lower() == "yes"
    if not agreement:
        print_colored("You must agree to the terms and conditions to proceed.", "red")
        sys.exit(1)
    return license_type, agreement

def get_user_info():
    print_colored("\nProvide the following information:", "blue")
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
        response = requests.post(SERVER_URL, json=data, timeout=30)
        response.raise_for_status()
        print_colored("User data sent successfully.", "green")
        return True, installation_id
    except requests.RequestException as e:
        print_colored(f"Failed to send user data: {str(e)}", "red")
        return False, installation_id

def check_node_count():
    print_colored("\nChecking Kubernetes nodes...", "blue")
    cmd = "kubectl get nodes -o json"
    success, output, error = run_command(cmd, verbose=False)
    if not success:
        print_colored("Failed to get Kubernetes nodes. Ensure your kubeconfig is correct and Kubernetes cluster is accessible.", "red")
        sys.exit(1)
    try:
        nodes = json.loads(output)['items']
        node_count = len(nodes)
        print_colored(f"Number of nodes in the cluster: {node_count}", "green")
        if node_count < REQUIRED_NODES:
            print_colored(f"At least {REQUIRED_NODES} nodes are required. Please add more nodes to your cluster.", "red")
            sys.exit(1)
    except json.JSONDecodeError:
        print_colored("Failed to parse nodes JSON output.", "red")
        sys.exit(1)

def is_aws_environment():
    # Try to detect AWS environment
    if os.path.exists('/sys/hypervisor/uuid'):
        with open('/sys/hypervisor/uuid') as f:
            uuid_str = f.read()
        if uuid_str.startswith('ec2'):
            return True

    # Check for AWS environment variables
    if 'AWS_EXECUTION_ENV' in os.environ:
        return True

    # If we can't detect, ask the user
    return get_user_input("Are you installing on AWS EKS? (yes/no):", ["yes", "no"]).lower() == "yes"

def setup_kubeconfig():
    if is_aws_environment():
        print_colored("Detected AWS environment. Updating kubeconfig for EKS...", "blue")
        cluster_name = input("Enter your EKS cluster name: ").strip()
        region = input("Enter your AWS region (e.g., us-west-2): ").strip()

        # Check if AWS CLI is installed
        aws_cli_installed = run_command("aws --version", verbose=False)[0]
        if not aws_cli_installed:
            print_colored("AWS CLI is not installed or not found in PATH. Please install and configure AWS CLI.", "red")
            return None

        # Update kubeconfig
        cmd = f"aws eks update-kubeconfig --name {cluster_name} --region {region}"
        success, _, error = run_command(cmd)
        if not success:
            print_colored(f"Failed to update kubeconfig: {error}", "red")
            return None
        kubeconfig_path = os.path.expanduser("~/.kube/config")
        return kubeconfig_path
    else:
        print_colored("\nSetting up kubeconfig...", "blue")

        kubeconfig_path = input("Enter the path to your kubeconfig file: ").strip()
        kubeconfig_path = os.path.expanduser(kubeconfig_path)

        if not os.path.exists(kubeconfig_path):
            print_colored(f"The file {kubeconfig_path} does not exist. Check the path and try again.", "red")
            return None

        default_kubeconfig = os.path.expanduser("~/.kube/config")
        os.makedirs(os.path.dirname(default_kubeconfig), exist_ok=True)
        try:
            shutil.copy(kubeconfig_path, default_kubeconfig)
            print_colored(f"Copied kubeconfig to {default_kubeconfig}", "green")
        except Exception as e:
            print_colored(f"Failed to copy kubeconfig: {str(e)}", "red")
            return None

        try:
            os.chmod(default_kubeconfig, 0o600)
            print_colored("Updated kubeconfig file permissions to 600.", "green")
        except Exception as e:
            print_colored(f"Failed to update kubeconfig file permissions: {str(e)}", "yellow")
            print_colored(f"Manually run: chmod 600 {default_kubeconfig}", "yellow")

        success, output, error = run_command("kubectl config current-context", verbose=False)
        if not success:
            print_colored("Failed to get current context. Check if the kubeconfig is valid.", "red")
            print_colored(f"Error output: {error}", "red")
            return None

        print_colored(f"Current context: {output.strip()}", "green")
        return default_kubeconfig

def modify_dev_yaml():
    dev_yaml_path = './hopsworks/values.dev.yaml'

    if not os.path.exists(dev_yaml_path):
        print_colored(f"Dev YAML file not found at {dev_yaml_path}", "red")
        return False

    try:
        with open(dev_yaml_path, 'r') as file:
            data = yaml.safe_load(file)

        # Modify values for better performance
        data['hopsworks']['debug'] = False
        # Add more modifications as needed

        with open(dev_yaml_path, 'w') as file:
            yaml.dump(data, file)

        print_colored("Updated dev YAML file for better performance", "green")
        return True
    except Exception as e:
        print_colored(f"Failed to modify dev YAML: {str(e)}", "red")
        return False

def update_values_yaml_for_aws(namespace):
    values_file = './hopsworks/values.yaml'
    if not os.path.exists(values_file):
        print_colored(f"Values YAML file not found at {values_file}", "red")
        return False

    try:
        with open(values_file, 'r') as f:
            values = yaml.safe_load(f)

        # Update values for AWS
        values['externalLoadBalancers'] = values.get('externalLoadBalancers', {})
        values['externalLoadBalancers']['enabled'] = True
        values['externalLoadBalancers']['annotations'] = {
            'service.beta.kubernetes.io/aws-load-balancer-scheme': 'internet-facing'
        }
        values['ingress'] = values.get('ingress', {})
        values['ingress']['enabled'] = True
        values['ingress']['ingressClassName'] = 'alb'
        values['ingress']['annotations'] = {
            'alb.ingress.kubernetes.io/scheme': 'internet-facing'
        }

        # Ask for SSL certificate ARN
        cert_arn = input("Enter your AWS ACM certificate ARN (or press Enter to skip): ").strip()
        if cert_arn:
            values['ingress']['annotations']['alb.ingress.kubernetes.io/certificate-arn'] = cert_arn

        with open(values_file, 'w') as f:
            yaml.dump(values, f)

        print_colored("Updated values.yaml for AWS environment", "green")
        return True
    except Exception as e:
        print_colored(f"Failed to update values.yaml for AWS: {str(e)}", "red")
        return False

def setup_ingress_for_aws(namespace):
    print_colored("Setting up AWS Load Balancer Controller...", "blue")
    # Check if AWS Load Balancer Controller is installed
    cmd = "kubectl get deployment -n kube-system aws-load-balancer-controller"
    success, _, _ = run_command(cmd, verbose=False)
    if not success:
        print_colored("AWS Load Balancer Controller not found. Installing...", "yellow")
        # Install AWS Load Balancer Controller
        run_command("helm repo add eks https://aws.github.io/eks-charts", verbose=False)
        run_command("helm repo update", verbose=False)
        # Create IAM service account if not exists
        service_account_exists = run_command("kubectl get serviceaccount aws-load-balancer-controller -n kube-system", verbose=False)[0]
        if not service_account_exists:
            print_colored("Creating service account for AWS Load Balancer Controller...", "blue")
            run_command("kubectl create serviceaccount aws-load-balancer-controller -n kube-system", verbose=False)
        install_cmd = (
            "helm install aws-load-balancer-controller eks/aws-load-balancer-controller "
            f"--namespace kube-system "
            f"--set clusterName={namespace} "
            "--set serviceAccount.create=false "
            "--set serviceAccount.name=aws-load-balancer-controller"
        )
        run_command(install_cmd)

    # Update values.yaml for AWS
    update_values_yaml_for_aws(namespace)

def install_hopsworks(namespace):
    print_colored("\nInstalling Hopsworks...", "blue")
    print_colored("This may take several minutes to complete. Please be patient.", "yellow")

    if not run_command("helm repo add hopsworks https://nexus.hops.works/repository/hopsworks-helm --force-update")[0]:
        print_colored("Failed to add Hopsworks Helm repo. Check your internet connection and try again.", "red")
        return False

    if not run_command("helm repo update")[0]:
        print_colored("Failed to update Helm repos. Check your internet connection and try again.", "red")
        return False

    if os.path.exists('hopsworks'):
        shutil.rmtree('hopsworks', ignore_errors=True)

    success, _, error = run_command("helm pull hopsworks/hopsworks --untar --devel")
    if not success:
        print_colored(f"Failed to pull Hopsworks chart. Error: {error}", "red")
        return False

    if not modify_dev_yaml():
        print_colored("Failed to modify dev YAML. Continuing with default settings.", "yellow")

    print_colored("Starting Hopsworks installation. This process may take up to an hour. Please be patient and do not interrupt.", "yellow")
    helm_command = (
        f"helm install hopsworks-release ./hopsworks "
        f"--namespace={namespace} "
        f"--create-namespace "
        f"--values hopsworks/values.services.yaml "
        f"--values hopsworks/values.yaml "
        f"--values hopsworks/values.dev.yaml "
        f"--timeout 60m "
        f"--wait "
        f"--debug "
        f"--devel"
    )

    success, output, error = run_command(helm_command, timeout=3600)

    if success:
        print_colored("Hopsworks installation command executed successfully.", "green")
    else:
        print_colored("Hopsworks installation command failed. Check the logs for details.", "red")
        print_colored(f"Error: {error}", "red")
        return False

    print_colored("Waiting for Hopsworks pods to be ready...", "yellow")
    pods_ready = wait_for_pods_ready(namespace)

    if pods_ready:
        print_colored("Hopsworks pods are ready.", "green")
    else:
        print_colored("Some pods did not become ready in time.", "red")
        print_colored("You may need to check the status of the pods and address any issues.", "yellow")
        # Decide whether to continue or exit
        # For now, continue to the next step

    print_colored("Proceeding to setup ingress...", "blue")
    return True

def wait_for_pods_ready(namespace, timeout=1800):  # 30 minutes timeout
    print_colored(f"Waiting for pods in namespace '{namespace}' to be ready...", "yellow")
    start_time = time.time()
    while time.time() - start_time < timeout:
        cmd = f"kubectl get pods -n {namespace} -o json"
        success, output, _ = run_command(cmd, verbose=False)
        if success:
            try:
                pods = json.loads(output)['items']
                total_pods = len(pods)
                ready_pods = 0
                failed_pods = []
                for pod in pods:
                    pod_phase = pod['status'].get('phase', '')
                    pod_name = pod['metadata'].get('name', '')
                    conditions = pod['status'].get('conditions', [])
                    pod_ready = any(cond['type'] == 'Ready' and cond['status'] == 'True' for cond in conditions)
                    if pod_ready:
                        ready_pods += 1
                    elif pod_phase == 'Failed':
                        failed_pods.append(pod_name)
                if total_pods > 0:
                    readiness = (ready_pods / total_pods) * 100
                    print_colored(f"Pods readiness: {readiness:.2f}% ({ready_pods}/{total_pods})", "green")
                    if failed_pods:
                        print_colored(f"The following pods have failed: {', '.join(failed_pods)}", "red")
                        print_colored("You may need to delete these pods to allow Kubernetes to recreate them.", "yellow")
                    if readiness >= 80:
                        print_colored("Sufficient pods are ready!", "green")
                        return True
                else:
                    print_colored("No pods found. Waiting...", "yellow")
            except json.JSONDecodeError as e:
                print_colored(f"Failed to parse pod status JSON: {str(e)}", "red")
        else:
            print_colored("Failed to get pods status. Retrying...", "yellow")
        time.sleep(10)
    print_colored(f"Timed out waiting for pods to be ready in namespace '{namespace}'", "red")
    return False

def get_hopsworks_url(namespace):
    cmd = f"kubectl get ingress -n {namespace} -o jsonpath='{{.items[0].spec.rules[0].host}}'"
    success, host_output, _ = run_command(cmd, verbose=False)
    if success and host_output.strip():
        host = host_output.strip()
    else:
        print_colored("Failed to retrieve Hopsworks URL from ingress. Defaulting to hopsworks.ai.local", "yellow")
        host = "hopsworks.ai.local"

    return f"https://{host}"

def check_ingress_controller():
    print_colored("\nChecking for an existing ingress controller...", "blue")
    cmd = "kubectl get pods --all-namespaces -l app.kubernetes.io/name=ingress-nginx -o json"
    success, output, _ = run_command(cmd, verbose=False)
    if success:
        try:
            pods = json.loads(output).get('items', [])
            if pods:
                print_colored("Ingress controller is already installed.", "green")
                return True
            else:
                print_colored("No ingress controller found.", "yellow")
                return False
        except json.JSONDecodeError:
            print_colored("Failed to parse pods JSON output.", "red")
            return False
    else:
        print_colored("Failed to check ingress controller. Proceeding to install one.", "yellow")
        return False

def install_ingress_controller():
    print_colored("\nInstalling ingress-nginx controller...", "blue")
    if not run_command("helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx")[0]:
        print_colored("Failed to add ingress-nginx Helm repo.", "red")
        return False
    if not run_command("helm repo update")[0]:
        print_colored("Failed to update Helm repos.", "red")
        return False
    helm_command = (
        "helm install ingress-nginx ingress-nginx/ingress-nginx "
        "--namespace ingress-nginx "
        "--create-namespace "
        "--set controller.service.type=LoadBalancer"
    )
    success, _, error = run_command(helm_command)
    if success:
        print_colored("Ingress controller installed successfully.", "green")
        return True
    else:
        print_colored(f"Failed to install ingress controller: {error}", "red")
        return False

def wait_for_ingress_address(namespace, timeout=600):
    print_colored("\nWaiting for ingress address to be assigned...", "yellow")
    start_time = time.time()
    while time.time() - start_time < timeout:
        cmd_ip = f"kubectl get ingress -n {namespace} -o jsonpath='{{.items[0].status.loadBalancer.ingress[0].ip}}'"
        cmd_hostname = f"kubectl get ingress -n {namespace} -o jsonpath='{{.items[0].status.loadBalancer.ingress[0].hostname}}'"

        success_ip, ip_output, _ = run_command(cmd_ip, verbose=False)
        success_hostname, hostname_output, _ = run_command(cmd_hostname, verbose=False)

        ingress_address = ip_output.strip() if ip_output.strip() else hostname_output.strip()

        if ingress_address:
            print_colored(f"Ingress address found: {ingress_address}", "green")
            return ingress_address
        else:
            print_colored("Ingress address not yet assigned. Waiting...", "yellow")
            time.sleep(10)

    print_colored("Timed out waiting for ingress address to be assigned.", "red")
    return None

def wait_for_ingress(namespace, hopsworks_url, timeout=600):
    print_colored("Waiting for ingress to be ready...", "yellow")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(hopsworks_url, timeout=10, verify=False)
            if response.status_code < 500:
                print_colored("Ingress is responding!", "green")
                return True
        except requests.RequestException:
            pass
        time.sleep(10)
    print_colored("Timed out waiting for ingress to be ready", "red")
    return False

def update_hosts_file(ingress_address, ingress_host):
    print_colored("\nTo access Hopsworks UI, you may need to update your /etc/hosts file.", "yellow")
    print_colored("Add the following entry to your /etc/hosts file:", "cyan")
    hosts_entry = f"{ingress_address} {ingress_host}"
    print_colored(hosts_entry, "green")
    update_hosts = get_user_input("Would you like the script to attempt to update your /etc/hosts file? (yes/no):", ["yes", "no"]).lower() == "yes"
    if update_hosts:
        try:
            with open("/etc/hosts", "a") as hosts_file:
                hosts_file.write(f"\n{hosts_entry}\n")
            print_colored("Successfully updated /etc/hosts.", "green")
        except PermissionError:
            print_colored("Permission denied when trying to update /etc/hosts.", "yellow")
            use_sudo = get_user_input("Do you want to try updating /etc/hosts using sudo? (yes/no): ", ["yes", "no"]).lower() == "yes"
            if use_sudo:
                sudo_command = f"echo '{hosts_entry}' | sudo tee -a /etc/hosts"
                success, _, error = run_command(sudo_command)
                if success:
                    print_colored("Successfully updated /etc/hosts using sudo.", "green")
                else:
                    print_colored("Failed to update /etc/hosts even with sudo.", "red")
                    print_colored(f"Error: {error}", "red")
                    print_colored("Please manually add the following entry to your /etc/hosts file:", "yellow")
                    print_colored(hosts_entry, "green")
            else:
                print_colored("Please manually add the following entry to your /etc/hosts file.", "yellow")
                print_colored(hosts_entry, "green")
        except Exception as e:
            print_colored(f"An unexpected error occurred: {str(e)}", "red")
            print_colored("Please manually add the following entry to your /etc/hosts file.", "yellow")
            print_colored(hosts_entry, "green")
    else:
        print_colored("Please manually add the following entry to your /etc/hosts file.", "yellow")
        print_colored(hosts_entry, "green")

def main():
    parser = argparse.ArgumentParser(description="Hopsworks Installation Script")
    parser.add_argument('--ingress-only', action='store_true', help='Jump directly to the ingress setup')
    args = parser.parse_args()

    if not args.ingress_only:
        print_colored("Welcome to the Hopsworks Installation Script!", "blue")

        license_type, agreement = get_license_agreement()
        name, email, company = get_user_info()
        success, installation_id = send_user_data(name, email, company, license_type, agreement)

        if success:
            print_colored(f"Installation ID: {installation_id}", "green")
            print_colored("Keep this ID for your records and support purposes.", "yellow")
        else:
            print_colored("Failed to process user information. Continuing with installation.", "yellow")
            installation_id = "unknown"

        kubeconfig = setup_kubeconfig()
        if not kubeconfig:
            print_colored("Failed to set up a valid kubeconfig. Exiting.", "red")
            sys.exit(1)

        check_node_count()

        namespace = get_user_input("Enter the namespace for Hopsworks installation (default: hopsworks):") or "hopsworks"

        if is_aws_environment():
            setup_ingress_for_aws(namespace)
        else:
            # Existing ingress setup logic
            if not install_hopsworks(namespace):
                print_colored("Hopsworks installation failed. Please check the logs and try again.", "red")
                sys.exit(1)
    else:
        namespace = get_user_input("Enter the namespace for Hopsworks installation (default: hopsworks):") or "hopsworks"
        installation_id = "unknown"

    print_colored("\nProceeding to setup ingress for Hopsworks...", "blue")

    if is_aws_environment():
        setup_ingress_for_aws(namespace)
        # For AWS, assume that ingress is set up via AWS Load Balancer Controller
        hopsworks_url = get_hopsworks_url(namespace)
        print_colored(f"Hopsworks UI should be accessible at: {hopsworks_url}", "cyan")
    else:
        # Check and install ingress controller if necessary
        if not check_ingress_controller():
            if not install_ingress_controller():
                print_colored("Failed to install ingress controller. Exiting.", "red")
                sys.exit(1)

        ingress_address = wait_for_ingress_address(namespace)
        if not ingress_address:
            print_colored("Failed to obtain ingress address. Exiting.", "red")
            sys.exit(1)

        hopsworks_url = get_hopsworks_url(namespace)
        if not hopsworks_url:
            print_colored("Unable to determine Hopsworks URL. Please check your ingress configuration.", "yellow")
            sys.exit(1)
        else:
            ingress_host = hopsworks_url.replace("https://", "")
            update_hosts_file(ingress_address, ingress_host)

            if not wait_for_ingress(namespace, hopsworks_url):
                print_colored("Warning: Ingress might not be fully set up. Check your cluster's networking.", "yellow")
            else:
                print_colored(f"Hopsworks UI should be accessible at: {hopsworks_url}, logins=admin@hopsworks.ai, password=admin", "cyan")

    print_colored("\nInstallation completed!", "green")
    print_colored(f"Your installation ID is: {installation_id}", "green")
    print_colored("Note: It may take a few minutes for all services to become fully operational.", "yellow")
    print_colored("If you're having trouble accessing the UI, ensure your ingress and DNS are properly configured.", "yellow")
    print_colored("If you need any assistance, contact our support team and provide your installation ID.", "blue")

if __name__ == "__main__":
    main()
