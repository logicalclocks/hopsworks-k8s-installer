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

from util import (
    print_colored,
    periodic_status_update,
    run_command
)

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

ENV_CONFIGS = {
    "AWS": {
        "ingress_class": "alb",
        "annotations": {
            "alb.ingress.kubernetes.io/scheme": "internet-facing",
            "service.beta.kubernetes.io/aws-load-balancer-scheme": "internet-facing"
        },
        "setup_cmd": None  # AWS uses the AWS Load Balancer Controller
    },
    "GCP": {
        "ingress_class": "gce",
        "annotations": {"kubernetes.io/ingress.class": "gce"},
        "setup_cmd": (
            "helm install ingress-nginx ingress-nginx/ingress-nginx "
            "--namespace ingress-nginx --create-namespace "
            "--set controller.service.type=LoadBalancer"
        )
    },
    "OVH": {
        "ingress_class": "nginx",
        "annotations": {},
        "setup_cmd": (
            "helm install ingress-nginx ingress-nginx/ingress-nginx "
            "--namespace ingress-nginx --create-namespace "
            "--set controller.service.type=LoadBalancer"
        )
    },
    "Azure": {
        "ingress_class": "nginx",
        "annotations": {},
        "setup_cmd": (
            "helm install ingress-nginx ingress-nginx/ingress-nginx "
            "--namespace ingress-nginx --create-namespace "
            "--set controller.service.type=LoadBalancer"
        )
    },
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

        if not self.args.ingress_only:
            self.handle_license_and_user_data()
            self.setup_environment_specifics()
            if self.install_hopsworks():
                print_colored("\nHopsworks installation completed.", "green")
                print_colored("Proceeding to setup ingress for Hopsworks...", "blue")
                self.setup_ingress()
                self.finalize_installation()
            else:
                print_colored("Hopsworks installation failed. Please check the logs and try again.", "red")
                sys.exit(1)
        else:
            self.setup_ingress()
            self.finalize_installation()

    def verify_kubeconfig(self):
        cmd = "kubectl get nodes"
        success, output, _ = run_command(cmd, verbose=False)
        if not success:
            print_colored("Failed to verify kubeconfig. Unable to get nodes.", "red")
            return False
        print_colored("Kubeconfig verified successfully.", "green")
        return True

    def check_pod_status(self):
        cmd = f"kubectl get pods -n {self.namespace}"
        run_command(cmd, verbose=True)

    def check_required_tools(self):
        tools = ["kubectl", "helm"]
        for tool in tools:
            if not shutil.which(tool):
                print_colored(f"{tool} not found. Please install it and try again.", "red")
                sys.exit(1)

    def parse_arguments(self):
        parser = argparse.ArgumentParser(description="Hopsworks Installation Script")
        parser.add_argument('--ingress-only', action='store_true', help='Jump directly to the ingress setup')
        parser.add_argument('--no-user-data', action='store_true', help='Skip sending user data')
        parser.add_argument('--skip-license', action='store_true', help='Skip license agreement step')
        parser.add_argument('--namespace', default='hopsworks', help='Namespace for Hopsworks installation')
        self.args = parser.parse_args()
        self.namespace = self.args.namespace

    def get_deployment_environment(self):
        self.environment = get_deployment_environment()

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

        if self.environment == "OVH":
            kubeconfig_path = input("Enter the full path to your OVH kubeconfig file: ").strip()
            kubeconfig_path = os.path.expanduser(kubeconfig_path)
            if not os.path.exists(kubeconfig_path):
                print_colored(f"The file {kubeconfig_path} does not exist. Check the path and try again.", "red")
                return None, None, None
            os.environ['KUBECONFIG'] = kubeconfig_path

        elif self.environment == "AWS":
            cluster_name = input("Enter your EKS cluster name: ").strip()
            region = self.get_aws_region()
            cmd = f"aws eks get-token --cluster-name {cluster_name} --region {region}"
            if not run_command(cmd)[0]:
                print_colored("Failed to get EKS token. Trying to update kubeconfig directly...", "yellow")
                cmd = f"aws eks update-kubeconfig --name {cluster_name} --region {region}"
                if not run_command(cmd)[0]:
                    print_colored("Failed to update kubeconfig.", "red")
                    return None, None, None
            kubeconfig_path = os.path.expanduser("~/.kube/config")

        else:  # For GCP, Azure, On-Premise/VM
            kubeconfig_path = input("Enter the path to your kubeconfig file: ").strip()
            kubeconfig_path = os.path.expanduser(kubeconfig_path)
            if not os.path.exists(kubeconfig_path):
                print_colored(f"The file {kubeconfig_path} does not exist. Check the path and try again.", "red")
                return None, None, None
            os.environ['KUBECONFIG'] = kubeconfig_path

        if kubeconfig_path:
            os.environ['KUBECONFIG'] = kubeconfig_path
            with open('set_kubeconfig.sh', 'w') as f:
                f.write(f"export KUBECONFIG={kubeconfig_path}\n")
            print("\nTo use kubectl in your current shell, run:")
            print("source set_kubeconfig.sh")

        return kubeconfig_path, cluster_name if self.environment == "AWS" else None, region if self.environment == "AWS" else None

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

    def setup_environment_specifics(self):
        if self.environment == "AWS":
            if not create_aws_load_balancer_controller(self.cluster_name, self.region, "kube-system"):
                print_colored("Failed to set up AWS Load Balancer Controller. Installation may fail.", "red")

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

        env_config = ENV_CONFIGS.get(self.environment, {})
        ingress_class = env_config.get('ingress_class', 'nginx')
        ingress_annotations = json.dumps(env_config.get('annotations', {}))

        helm_command = (
            f"helm upgrade --install hopsworks-release hopsworks/hopsworks "
            f"--namespace={self.namespace} "
            f"--create-namespace "
            f"--values hopsworks/values.yaml "
            f"--set externalLoadBalancers.enabled=true "
            f"--set ingress.enabled=true "
            f"--set ingress.ingressClassName={ingress_class} "
            f"--set-json ingress.annotations='{ingress_annotations}' "
            f"--timeout 60m "
            f"--wait "
            f"--debug "
            f"--devel"
        )

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

    def setup_ingress(self):
        print_colored("\nProceeding to setup ingress for Hopsworks...", "blue")
        if not setup_ingress(self.environment, self.namespace, self.cluster_name, self.region):
            print_colored("Failed to setup ingress. You may need to set it up manually.", "red")

    def finalize_installation(self):
        ingress_address = wait_for_ingress_address(self.namespace)
        if not ingress_address:
            print_colored("Failed to obtain ingress address. You may need to configure it manually.", "red")

        hopsworks_url = get_hopsworks_url(self.namespace)
        if hopsworks_url:
            ingress_host = hopsworks_url.replace("https://", "")
            update_hosts_file(ingress_address, ingress_host)
            print_colored(f"Hopsworks UI should be accessible at: {hopsworks_url}", "cyan")
            print_colored("Default login: admin@hopsworks.ai, password: admin", "cyan")
        else:
            print_colored("Unable to determine Hopsworks URL. Please check your ingress configuration.", "yellow")

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
            "If you're having trouble accessing the UI, ensure your ingress and DNS are properly configured.",
            "yellow"
        )
        print_colored(
            "If you need any assistance, contact our support team and provide your installation ID.",
            "blue"
        )


def get_user_input(prompt, options=None):
    while True:
        response = input(prompt + " ").strip()
        if options is None or response.lower() in [option.lower() for option in options]:
            return response
        print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "yellow")

def get_deployment_environment():
    environments = list(ENV_CONFIGS.keys()) + ["On-Premise/VM"]
    print_colored("Select your deployment environment:", "blue")
    for i, env in enumerate(environments, 1):
        print(f"{i}. {env}")
    choice = get_user_input(
        "Enter the number of your environment:",
        [str(i) for i in range(1, len(environments) + 1)]
    )
    return environments[int(choice) - 1]

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

def create_aws_load_balancer_controller(cluster_name, region, namespace):
    print_colored("Setting up AWS Load Balancer Controller...", "blue")

    # Add EKS repo
    if not run_command("helm repo add eks https://aws.github.io/eks-charts")[0]:
        print_colored("Failed to add EKS Helm repo.", "red")
        return False

    # Update Helm repos
    if not run_command("helm repo update")[0]:
        print_colored("Failed to update Helm repos.", "red")
        return False

    # Create IAM service account
    cmd_iam = f"""
    eksctl create iamserviceaccount \
    --cluster={cluster_name} \
    --namespace=kube-system \
    --name=aws-load-balancer-controller \
    --attach-policy-arn=arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess \
    --override-existing-serviceaccounts \
    --approve \
    --region={region}
    """
    if not run_command(cmd_iam)[0]:
        print_colored("Failed to create IAM service account for AWS Load Balancer Controller.", "red")
        return False

    # Install the controller
    cmd_install = f"""
    helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
    -n kube-system \
    --set clusterName={cluster_name} \
    --set serviceAccount.create=false \
    --set serviceAccount.name=aws-load-balancer-controller
    """
    if not run_command(cmd_install)[0]:
        print_colored("Failed to install AWS Load Balancer Controller.", "red")
        return False

    print_colored("AWS Load Balancer Controller setup completed.", "green")
    return True

def setup_ingress(environment, namespace, cluster_name=None, region=None):
    if environment == "AWS":
        if cluster_name is None or region is None:
            print_colored("Cluster name and region are required for AWS setup.", "red")
            return False
        return create_aws_load_balancer_controller(cluster_name, region, namespace)
    else:
        env_config = ENV_CONFIGS.get(environment, {})
        setup_cmd = env_config.get('setup_cmd', '')
        if setup_cmd:
            if "{cluster_name}" in setup_cmd:
                setup_cmd = setup_cmd.format(cluster_name=cluster_name)
            if "{namespace}" in setup_cmd:
                setup_cmd = setup_cmd.format(namespace=namespace)
            return run_command(setup_cmd)[0]
    return True

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
        
        if time.time() - start_time > 300:  # 5 minutes passed
            proceed = get_user_input("\nTaking longer than expected. Do you want to proceed anyway? (yes/no): ", ["yes", "no"])
            if proceed.lower() == "yes":
                print_colored("Proceeding with installation...", "yellow")
                return True

    print_colored("\nTimed out waiting for pods to be ready.", "red")
    return False

def wait_for_ingress_address(namespace, timeout=600):
    print_colored("\nWaiting for ingress address to be assigned...", "yellow")
    start_time = time.time()
    while time.time() - start_time < timeout:
        cmd = (
            f"kubectl get ingress -n {namespace} "
            f"-o jsonpath='{{.items[0].status.loadBalancer.ingress[0].ip}}"
            f"{{.items[0].status.loadBalancer.ingress[0].hostname}}'"
        )
        _, output, _ = run_command(cmd, verbose=False)
        if output.strip():
            print_colored(f"Ingress address found: {output.strip()}", "green")
            return output.strip()
        time.sleep(10)
    print_colored("Timed out waiting for ingress address to be assigned.", "red")
    return None

def get_hopsworks_url(namespace):
    cmd = f"kubectl get ingress -n {namespace} -o jsonpath='{{.items[0].spec.rules[0].host}}'"
    success, host_output, _ = run_command(cmd, verbose=False)
    if success and host_output.strip():
        host = host_output.strip()
    else:
        print_colored(
            "Failed to retrieve Hopsworks URL from ingress. Defaulting to hopsworks.ai.local",
            "yellow"
        )
        host = "hopsworks.ai.local"

    return f"https://{host}"

def update_hosts_file(ingress_address, ingress_host):
    print_colored(
        "\nTo access Hopsworks UI, you may need to update your /etc/hosts file.",
        "yellow"
    )
    print_colored("Add the following entry to your /etc/hosts file:", "cyan")
    hosts_entry = f"{ingress_address} {ingress_host}"
    print_colored(hosts_entry, "green")
    update_hosts = get_user_input(
        "Would you like the script to attempt to update your /etc/hosts file? (yes/no):",
        ["yes", "no"]
    ).lower() == "yes"
    if update_hosts:
        try:
            with open("/etc/hosts", "a") as hosts_file:
                hosts_file.write(f"\n{hosts_entry}\n")
            print_colored("Successfully updated /etc/hosts.", "green")
        except PermissionError:
            print_colored("Permission denied when trying to update /etc/hosts.", "yellow")
            use_sudo = get_user_input(
                "Do you want to try updating /etc/hosts using sudo? (yes/no): ", ["yes", "no"]
            ).lower() == "yes"
            if use_sudo:
                sudo_command = f"echo '{hosts_entry}' | sudo tee -a /etc/hosts"
                success, _, error = run_command(sudo_command)
                if success:
                    print_colored("Successfully updated /etc/hosts using sudo.", "green")
                else:
                    print_colored("Failed to update /etc/hosts even with sudo.", "red")
                    print_colored(
                        "Please manually add the following entry to your /etc/hosts file:",
                        "yellow"
                    )
                    print_colored(hosts_entry, "green")
            else:
                print_colored(
                    "Please manually add the following entry to your /etc/hosts file:",
                    "yellow"
                )
                print_colored(hosts_entry, "green")
    else:
        print_colored(
            "Please manually add the following entry to your /etc/hosts file:",
            "yellow"
        )
        print_colored(hosts_entry, "green")

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
