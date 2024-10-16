#!/usr/bin/env python3

import subprocess
import time
import sys
import os
import uuid
import json
import shutil
import argparse
from datetime import datetime
import urllib.request
import urllib.error
import ssl
import threading

HOPSWORKS_LOGO = """
██╗  ██╗    ██████╗    ██████╗    ███████╗   ██╗    ██╗    ██████╗    ██████╗    ██╗  ██╗   ███████╗
██║  ██║   ██╔═══██╗   ██╔══██╗   ██╔════╝   ██║    ██║   ██╔═══██╗   ██╔══██╗   ██║ ██╔╝   ██╔════╝
███████║   ██║   ██║   ██████╔╝   ███████╗   ██║ █╗ ██║   ██║   ██║   ██████╔╝   █████╔╝    ███████╗ 
██╔══██║   ██║   ██║   ██╔═══╝    ╚════██║   ██║███╗██║   ██║   ██║   ██╔══██╗   ██╔═██╗    ╚════██║
██║  ██║   ╚██████╔╝   ██║        ███████║   ╚███╔███╔╝   ╚██████╔╝   ██║  ██║   ██║  ██╗   ███████║     
╚═╝  ╚═╝    ╚═════╝    ╚═╝        ╚══════╝    ╚══╝╚══╝     ╚═════╝    ╚═╝  ╚═╝   ╚═╝  ╚═╝   ╚══════╝
"""

SERVER_URL = "https://magiclex--hopsworks-installation-hopsworks-installation.modal.run/"
STARTUP_LICENSE_URL = "https://www.hopsworks.ai/startup-license"
EVALUATION_LICENSE_URL = "https://www.hopsworks.ai/evaluation-license"

eks_helm_addition, aks_helm_addition = {
    "global._hopsworks.cloudProvider": "AWS",
    "global._hopsworks.imagePullPolicy": "Always",  
    "docker-registry.enabled": "true",
    "docker-registry.replicas": "1",
    "hopsfs.datanode.count": "1",
    "hopsworks.replicaCount.worker": "1",
    "hopsworks.payara.debug": "true",
    "rondb.isMultiNodeCluster": "true",
    "rondb.clusterSize.activeDataReplicas": "1",
    "hopsworks.service.worker.external.https.type": "LoadBalancer",

    # "hopsworks.service.worker.external.https.annotations.service\\.beta\\.kubernetes\\.io/aws-load-balancer-ssl-cert": "<your-acm-cert-arn>",
    # "hopsworks.service.worker.external.https.annotations.service\\.beta\\.kubernetes\\.io/aws-load-balancer-backend-protocol": "https",
    # "hopsworks.service.worker.external.https.annotations.service\\.beta\\.kubernetes\\.io/aws-load-balancer-ssl-ports": "443,8181",
}


class HopsworksInstaller:
    def __init__(self):
        self.environment = None
        self.kubeconfig_path = None
        self.cluster_name = None
        self.region = None
        self.namespace = 'hopsworks'
        self.installation_id = None
        self.args = None

    def run(self):
        print_colored(HOPSWORKS_LOGO, "white")
        self.check_required_tools()
        self.parse_arguments()
        self.get_deployment_environment()
        self.setup_and_verify_kubeconfig()

        if not self.args.loadbalancer_only:
            self.handle_license_and_user_data()
            if self.install_hopsworks():
                print_colored("\nHopsworks installation completed.", "green")
                self.finalize_installation()
            else:
                print_colored("Hopsworks installation failed. Please check the logs and try again.", "red")
                sys.exit(1)
        else:
            self.finalize_installation()

    def setup_and_verify_kubeconfig(self):
        while True:
            self.kubeconfig_path, self.cluster_name, self.region = self.setup_kubeconfig()
            if self.kubeconfig_path:
                if self.verify_kubeconfig():
                    break
            else:
                print_colored("Failed to set up a valid kubeconfig.", "red")
                if not get_user_input("Do you want to try again? (yes/no):", ["yes", "no"]).lower() == "yes":
                    sys.exit(1)

    def setup_kubeconfig(self):
        print_colored(f"\nSetting up kubeconfig for {self.environment}...", "blue")

        kubeconfig_path = None
        cluster_name = None
        region = None

        if self.environment == "AWS":
            cluster_name = input("Enter your EKS cluster name: ").strip()
            region = self.get_aws_region()
            cmd = f"aws eks get-token --cluster-name {cluster_name} --region {region}"
            if not run_command(cmd)[0]:
                print_colored("Failed to get EKS token. Updating kubeconfig...", "yellow")
                cmd = f"aws eks update-kubeconfig --name {cluster_name} --region {region}"
                if not run_command(cmd)[0]:
                    print_colored("Failed to update kubeconfig.", "red")
                    return None, None, None
            kubeconfig_path = os.path.expanduser("~/.kube/config")
        else:
            kubeconfig_path = input("Enter the path to your kubeconfig file: ").strip()
            kubeconfig_path = os.path.expanduser(kubeconfig_path)
            if not os.path.exists(kubeconfig_path):
                print_colored(f"The file {kubeconfig_path} does not exist. Check the path and try again.", "red")
                return None, None, None

        if kubeconfig_path:
            os.environ['KUBECONFIG'] = kubeconfig_path
            with open('set_kubeconfig.sh', 'w') as f:
                f.write(f"export KUBECONFIG={kubeconfig_path}\n")
            print("\nTo use kubectl in your current shell, run:")
            print("source set_kubeconfig.sh")

        return kubeconfig_path, cluster_name, region

    def verify_kubeconfig(self):
        print_colored("\nVerifying kubeconfig...", "cyan")
        
        # Check current context
        cmd = "kubectl config current-context"
        success, output, error = run_command(cmd, verbose=True)
        if not success:
            print_colored(f"Failed to get current context. Error: {error}", "red")
            return False
        
        # Try to list namespaces
        cmd = "kubectl get namespaces"
        success, output, error = run_command(cmd, verbose=True)
        if not success:
            print_colored(f"Failed to list namespaces. Error: {error}", "red")
            return False
        
        print_colored("Kubeconfig verified successfully.", "green")
        return True

    def check_required_tools(self):
        tools = ["kubectl", "helm"]
        for tool in tools:
            if not shutil.which(tool):
                print_colored(f"{tool} not found. Please install it and try again.", "red")
                sys.exit(1)

    def parse_arguments(self):
        parser = argparse.ArgumentParser(description="Hopsworks Installation Script")
        parser.add_argument('--loadbalancer-only', action='store_true', help='Jump directly to the LoadBalancer setup')
        parser.add_argument('--no-user-data', action='store_true', help='Skip sending user data')
        parser.add_argument('--skip-license', action='store_true', help='Skip license agreement step')
        parser.add_argument('--namespace', default='hopsworks', help='Namespace for Hopsworks installation')
        self.args = parser.parse_args()
        self.namespace = self.args.namespace

    def get_deployment_environment(self):
        environments = ["AWS", "GCP", "Azure", "OVH", "On-Premise/VM"]
        print_colored("Select your deployment environment:", "blue")
        for i, env in enumerate(environments, 1):
            print(f"{i}. {env}")
        choice = get_user_input(
            "Enter the number of your environment:",
            [str(i) for i in range(1, len(environments) + 1)]
        )
        self.environment = environments[int(choice) - 1]

    def setup_and_verify_kubeconfig(self):
        while True:
            self.kubeconfig_path, self.cluster_name, self.region = self.setup_kubeconfig()
            if self.kubeconfig_path:
                if self.verify_kubeconfig():
                    break
            else:
                print_colored("Failed to set up a valid kubeconfig.", "red")
                if not get_user_input("Do you want to try again? (yes/no):", ["yes", "no"]).lower() == "yes":
                    sys.exit(1)

    def setup_kubeconfig(self):
        print_colored(f"\nSetting up kubeconfig for {self.environment}...", "blue")

        kubeconfig_path = None
        cluster_name = None
        region = None

        if self.environment == "AWS":
            cluster_name = input("Enter your EKS cluster name: ").strip()
            region = self.get_aws_region()
            
            print_colored("Updating kubeconfig...", "cyan")
            cmd = f"aws eks update-kubeconfig --name {cluster_name} --region {region}"
            success, output, error = run_command(cmd, verbose=True)
            if not success:
                print_colored(f"Failed to update kubeconfig. Error: {error}", "red")
                return None, None, None
            
            kubeconfig_path = os.path.expanduser("~/.kube/config")
            
            print_colored("Verifying AWS CLI configuration...", "cyan")
            aws_cmd = "aws sts get-caller-identity"
            aws_success, aws_output, aws_error = run_command(aws_cmd, verbose=True)
            if not aws_success:
                print_colored(f"AWS CLI is not configured correctly. Error: {aws_error}", "red")
                return None, None, None
            
        else:
            kubeconfig_path = input("Enter the path to your kubeconfig file: ").strip()
            kubeconfig_path = os.path.expanduser(kubeconfig_path)
            if not os.path.exists(kubeconfig_path):
                print_colored(f"The file {kubeconfig_path} does not exist. Check the path and try again.", "red")
                return None, None, None

        if kubeconfig_path:
            os.environ['KUBECONFIG'] = kubeconfig_path
            with open('set_kubeconfig.sh', 'w') as f:
                f.write(f"export KUBECONFIG={kubeconfig_path}\n")
            print("\nTo use kubectl in your current shell, run:")
            print("source set_kubeconfig.sh")
            
        self.print_current_kubeconfig()
        return kubeconfig_path, cluster_name, region

    def print_current_kubeconfig(self):
        print_colored("\nCurrent KUBECONFIG environment variable:", "cyan")
        print(os.environ.get('KUBECONFIG', 'Not set'))
        
        print_colored("\nContents of current kubeconfig:", "cyan")
        cmd = "kubectl config view --raw"
        success, output, error = run_command(cmd, verbose=True)
        if not success:
            print_colored(f"Failed to view kubeconfig. Error: {error}", "red")


    def get_aws_region(self):
        region = os.environ.get('AWS_REGION')
        if not region:
            region = input("Enter your AWS region (e.g., us-east-2): ").strip()
            os.environ['AWS_REGION'] = region
        return region

    def handle_license_and_user_data(self):
        if not self.args.skip_license:
            license_type, agreement = get_license_agreement()
        else:
            license_type, agreement = None, False

        if not self.args.no_user_data:
            name, email, company = get_user_info()
            success, self.installation_id = send_user_data(name, email, company, license_type, agreement)
            if success:
                print_colored(f"Installation ID: {self.installation_id}", "green")
            else:
                print_colored("Failed to process user information. Continuing with installation.", "yellow")
                self.installation_id = "unknown"
        else:
            self.installation_id = "debug_mode"

    def install_hopsworks(self):
        print_colored("\nInstalling Hopsworks...", "blue")

        if not run_command("helm repo add hopsworks https://nexus.hops.works/repository/hopsworks-helm --force-update")[0]:
            print_colored("Failed to add Hopsworks Helm repo.", "red")
            return False

        print_colored("Updating Helm repositories...", "cyan")
        if not run_command("helm repo update")[0]:
            print_colored("Failed to update Helm repos.", "red")
            return False

        if os.path.exists('hopsworks'):
            shutil.rmtree('hopsworks', ignore_errors=True)

        print_colored("Pulling Hopsworks Helm chart...", "cyan")
        if not run_command("helm pull hopsworks/hopsworks --untar --devel")[0]:
            print_colored("Failed to pull Hopsworks chart.", "red")
            return False

        helm_command = (
            f"helm upgrade --install hopsworks-release hopsworks/hopsworks "
            f"--namespace={self.namespace} "
            f"--create-namespace "
            f"--values hopsworks/values.yaml "
            f"--set hopsworks.service.worker.external.https.type=LoadBalancer "
        )
            
        if self.environment == "AWS":
            for key, value in eks_helm_addition.items():
                helm_command += f" --set {key}={value} "

        helm_command += " --timeout 60m --wait --devel"


        print_colored("Starting Hopsworks installation...", "cyan")

        stop_event = threading.Event()
        status_thread = threading.Thread(target=periodic_status_update, args=(stop_event, self.namespace))
        status_thread.start()

        success, _, _ = run_command(helm_command)

        stop_event.set()
        status_thread.join()

        if not success:
            print_colored("\nHopsworks installation command failed.", "red")
            return False

        print_colored("\nHopsworks installation command completed.", "green")
        print_colored("Checking Hopsworks pod readiness...", "yellow")
        return wait_for_pods_ready(self.namespace)

    def finalize_installation(self):
        load_balancer_address = self.get_load_balancer_address()
        if not load_balancer_address:
            print_colored("Failed to obtain LoadBalancer address. You may need to configure it manually.", "red")
        else:
            print_colored(f"Hopsworks LoadBalancer address: {load_balancer_address}", "green")

        hopsworks_url = f"https://{load_balancer_address}:28181"  # Note the added port
        print_colored(f"Hopsworks UI should be accessible at: {hopsworks_url}", "cyan")
        print_colored("Default login: admin@hopsworks.ai, password: admin", "cyan")

        if health_check(self.namespace):
            print_colored("\nHealth check passed. Hopsworks appears to be running correctly.", "green")
        else:
            print_colored("\nHealth check failed. Please review the installation and check the logs.", "red")

        print_colored("\nInstallation completed!", "green")
        print_colored(f"Your installation ID is: {self.installation_id}", "green")
        print_colored(
            "Note: It may take a few minutes for all services to become fully operational.",
            "yellow"
        )
        print_colored(
            "If you're having trouble accessing the UI, ensure your LoadBalancer and DNS are properly configured.",
            "yellow"
        )
        print_colored(
            "If you need any assistance, contact our support team and provide your installation ID.",
            "blue"
        )

    def get_load_balancer_address(self):
        if self.environment == "AWS":
            cmd = f"kubectl get svc -n {self.namespace} hopsworks-release -o jsonpath='{{.status.loadBalancer.ingress[0].hostname}}'"
        else:
            cmd = f"kubectl get svc -n {self.namespace} hopsworks-release -o jsonpath='{{.status.loadBalancer.ingress[0].ip}}'"
        
        success, output, _ = run_command(cmd, verbose=False)
        if success and output.strip():
            return output.strip()
        else:
            print_colored("Failed to retrieve LoadBalancer address for hopsworks-release. Checking alternatives...", "yellow")
            
            # Fallback to checking all LoadBalancer services
            cmd = f"kubectl get svc -n {self.namespace} -o jsonpath='{{range .items}}{{if eq .spec.type \"LoadBalancer\"}}{{.metadata.name}}{{\"=\"}}{{.status.loadBalancer.ingress[0].ip}}{{\"\\n\"}}{{end}}{{end}}'"
            success, output, _ = run_command(cmd, verbose=False)
            if success and output.strip():
                services = dict(line.split('=') for line in output.strip().split('\n'))
                if 'hopsworks-release' in services:
                    return services['hopsworks-release']
                else:
                    print_colored("Couldn't find hopsworks-release LoadBalancer. Available LoadBalancer services:", "yellow")
                    for svc, ip in services.items():
                        print(f"{svc}: {ip}")
                    return None
            else:
                print_colored("Failed to retrieve any LoadBalancer addresses. Please check your service configuration.", "yellow")
                return None
            
def print_colored(message, color, **kwargs):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "magenta": "\033[95m", "cyan": "\033[96m",
        "white": "\033[97m", "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{message}{colors['reset']}", **kwargs)

def run_command(command, verbose=True):
    if verbose:
        print_colored(f"Running: {command}", "cyan")
    try:
        result = subprocess.run(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if verbose:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print_colored(result.stderr, "yellow")
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def get_user_input(prompt, options=None):
    while True:
        response = input(prompt + " ").strip()
        if options is None or response.lower() in [option.lower() for option in options]:
            return response
        print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "yellow")

def periodic_status_update(stop_event, namespace):
    while not stop_event.is_set():
        cmd = f"kubectl get pods -n {namespace} --no-headers"
        success, output, error = run_command(cmd, verbose=False)
        if success and output.strip():
            pod_count = len(output.strip().split('\n'))
            print_colored(f"\rCurrent status: {pod_count} pods created", "cyan", end='')
        else:
            if "No resources found" in error:
                print_colored("\rWaiting for pods to be created...", "yellow", end='')
            else:
                print_colored(f"\rError checking pod status: {error.strip()}", "red", end='')
        sys.stdout.flush()  # Ensure the output is displayed immediately
        time.sleep(10)  # Update every 10 seconds
    print()  # Print a newline when done to move to the next line


def get_license_agreement():
    print_colored("\nChoose a license agreement:", "blue")
    print("1. Startup Software License")
    print("2. Evaluation Agreement")
    choice = get_user_input("Enter 1 or 2:", ["1", "2"])
    license_type = "Startup" if choice == "1" else "Evaluation"
    license_url = STARTUP_LICENSE_URL if choice == "1" else EVALUATION_LICENSE_URL
    print_colored(f"\nReview the {license_type} License Agreement at:", "blue")
    print_colored(license_url, "cyan")
    agreement = get_user_input(
        "\nDo you agree to the terms and conditions? (yes/no):", ["yes", "no"]
    ).lower() == "yes"
    if not agreement:
        print_colored("You must agree to the terms and conditions to proceed.", "red")
        sys.exit(1)
    return license_type, agreement

def get_user_info():
    print_colored("\nProvide the following information:", "blue")
    return input("Your name: "), input("Your email address: "), input("Your company name: ")

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
        req = urllib.request.Request(
            SERVER_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        context = ssl._create_unverified_context()  # For HTTPS connections
        with urllib.request.urlopen(req, timeout=30, context=context) as response:
            if response.getcode() == 200:
                print_colored("User data sent successfully.", "green")
                return True, installation_id
            else:
                raise urllib.error.HTTPError(
                    SERVER_URL, response.getcode(), "Failed to send user data", None, None
                )
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print_colored(f"Failed to send user data: {str(e)}", "red")
        return False, installation_id

def wait_for_pods_ready(namespace, timeout=600, readiness_threshold=0.7):
    print_colored("Checking pod readiness...", "yellow")
    start_time = time.time()
    
    critical_pods = ['namenode', 'resourcemanager', 'hopsworks', 'mysql']
    
    while time.time() - start_time < timeout:
        cmd = f"kubectl get pods -n {namespace} -o json"
        success, output, _ = run_command(cmd, verbose=False)
        
        if success:
            pods = json.loads(output)['items']
            total_pods = len(pods)
            ready_pods = 0
            critical_ready = 0
            
            for pod in pods:
                if all(cont.get('ready', False) for cont in pod['status'].get('containerStatuses', [])):
                    ready_pods += 1
                    if any(critical in pod['metadata']['name'] for critical in critical_pods):
                        critical_ready += 1
            
            readiness_ratio = ready_pods / total_pods
            print_colored(f"\rPods ready: {ready_pods}/{total_pods} ({readiness_ratio:.2%})", "cyan", end='')
            
            if readiness_ratio >= readiness_threshold and critical_ready == len(critical_pods):
                print_colored(f"\nSufficient pods are ready! ({readiness_ratio:.2%})", "green")
                return True
            
            time.sleep(5)
        else:
            print_colored("\nFailed to get pod status. Retrying...", "yellow")
            time.sleep(5)
        
        if time.time() - start_time > 30:  # 5 minutes passed
            proceed = get_user_input("\nMost of the pods are ready! Proceed? (yes/no): ", ["yes", "no"])
            if proceed.lower() == "yes":
                print_colored("Proceeding with installation...", "yellow")
                return True

    print_colored("\nTimed out waiting for pods to be ready.", "red")
    return False

def health_check(namespace):
    print_colored("\nPerforming basic health check...", "blue")

    cmd = f"kubectl get pods -n {namespace} -o jsonpath='{{.items[*].status.phase}}'"
    success, output, _ = run_command(cmd, verbose=False)
    if not success or 'Running' not in output:
        print_colored("Not all pods are in Running state. Health check failed.", "red")
        return False

    print_colored("Basic health check passed.", "green")
    return True

if __name__ == "__main__":
    installer = HopsworksInstaller()
    installer.run()