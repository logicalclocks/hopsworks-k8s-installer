#!/usr/bin/env python3

import subprocess
import time
import sys
import os
import uuid
import shutil
import argparse
from datetime import datetime
import urllib.request
import urllib.error
import ssl
import threading
import boto3
import base64
import json
import tempfile
import yaml

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

class HopsworksInstaller:
    def __init__(self):
        self.environment = None
        self.kubeconfig_path = None
        self.cluster_name = None
        self.region = None
        self.zone = None
        self.namespace = 'hopsworks'
        self.installation_id = None
        self.args = None
        self.project_id = None
        self.use_managed_registry = False
        self.managed_registry_info = None
        self.sa_email = None
        self.role_name = None 

    def run(self):
        print_colored(HOPSWORKS_LOGO, "white")
        self.parse_arguments()
        self.check_required_tools()
        self.get_deployment_environment()

        if not self.args.loadbalancer_only:
            if self.environment == "GCP":
                self.setup_gke_prerequisites()
            else:
                self.setup_and_verify_kubeconfig()
            self.handle_managed_registry()
            self.handle_license_and_user_data()
            if self.install_hopsworks():
                print_colored("\nHopsworks installation completed.", "green")
                self.finalize_installation()
            else:
                print_colored("Hopsworks installation failed. Please check the logs and try again.", "red")
                sys.exit(1)
        else:
            # For loadbalancer-only, we need to set up the necessary variables
            self.namespace = self.args.namespace
            self.setup_and_verify_kubeconfig()
            self.finalize_installation()

    def setup_gke_prerequisites(self):
        """Setup everything needed before cluster creation"""
        print_colored("\nSetting up GKE prerequisites...", "blue")

        # 1. Get essential info first
        self.project_id = input("Enter your GCP project ID: ").strip()
        zone_input = input("Enter your GCP zone (e.g. europe-west1-b): ").strip()
        self.zone = zone_input
        self.region = '-'.join(zone_input.split('-')[:-1])  # extract region from zone

        # 2. Create role with timestamp to avoid collision
        timestamp = int(time.time())
        self.role_name = f"hopsworksai.instances.{timestamp}"  # Unique role name
        print_colored(f"Creating role '{self.role_name}'...", "cyan")

        role_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        try:
            role_def = {
                "title": "Hopsworks AI Instances",
                "description": "Role for Hopsworks instances",
                "stage": "GA",
                "includedPermissions": [
                    # Artifact Registry permissions
                    "artifactregistry.repositories.create",
                    "artifactregistry.repositories.get",
                    "artifactregistry.repositories.uploadArtifacts",
                    "artifactregistry.repositories.downloadArtifacts",
                    "artifactregistry.tags.list",
                    "artifactregistry.repositories.list"
                ]
            }
            yaml.dump(role_def, role_file)
            role_file.close()

            success, _, error = run_command(
                f"gcloud iam roles create {self.role_name} --project={self.project_id} --file={role_file.name}"
            )
            if not success:
                print_colored(f"Failed to create role: {error}", "red")
                sys.exit(1)
            else:
                print_colored(f"Role '{self.role_name}' created successfully.", "green")
        finally:
            os.unlink(role_file.name)

        # 3. Create/update service account
        sa_name = "hopsworksai-instances"
        self.sa_email = f"{sa_name}@{self.project_id}.iam.gserviceaccount.com"

        # Check if SA exists first
        success, _, _ = run_command(
            f"gcloud iam service-accounts describe {self.sa_email} --project={self.project_id}",
            verbose=False
        )

        if not success:
            success, _, error = run_command(
                f"gcloud iam service-accounts create {sa_name} "
                f"--project={self.project_id} "
                f"--description='Service account for Hopsworks' "
                f"--display-name='Hopsworks Service Account'"
            )
            if not success and "already exists" not in error:
                print_colored(f"Failed to create service account: {error}", "red")
                sys.exit(1)
            else:
                print_colored(f"Service account '{self.sa_email}' created.", "green")
        else:
            print_colored(f"Service account '{self.sa_email}' already exists.", "green")

        # 4. Update role binding
        print_colored("Updating role binding...", "cyan")
        # Remove existing binding if it exists
        run_command(
            f"gcloud projects remove-iam-policy-binding {self.project_id} "
            f"--member=serviceAccount:{self.sa_email} "
            f"--role=projects/{self.project_id}/roles/{self.role_name}",
            verbose=False
        )

        success, _, error = run_command(
            f"gcloud projects add-iam-policy-binding {self.project_id} "
            f"--member=serviceAccount:{self.sa_email} "
            f"--role=projects/{self.project_id}/roles/{self.role_name}"
        )
        if not success:
            print_colored(f"Failed to bind role: {error}", "red")
            sys.exit(1)
        else:
            print_colored(f"Role '{self.role_name}' bound to service account '{self.sa_email}'.", "green")

        # 5. NOW we can create the cluster with the service account
        self.cluster_name = input("Enter your GKE cluster name: ").strip() or "hopsworks-cluster"
        node_count = input("Enter number of nodes (default: 6): ").strip() or "6"
        machine_type = input("Enter machine type (default: n2-standard-8): ").strip() or "n2-standard-8"

        cluster_cmd = (f"gcloud container clusters create {self.cluster_name} "
                       f"--zone={self.zone} "
                       f"--machine-type={machine_type} "
                       f"--num-nodes={node_count} "
                       f"--enable-ip-alias "
                       f"--service-account={self.sa_email}")
        
        print_colored("Creating GKE cluster...", "cyan")
        if not run_command(cluster_cmd)[0]:
            print_colored("Failed to create GKE cluster.", "red")
            sys.exit(1)
        else:
            print_colored(f"GKE cluster '{self.cluster_name}' created.", "green")

        # 6. Configure kubectl
        print_colored("Configuring kubectl...", "cyan")
        run_command(f"gcloud container clusters get-credentials {self.cluster_name} "
                    f"--zone={self.zone} "
                    f"--project={self.project_id}")

        # 7. Setup Artifact Registry
        registry_name = f"hopsworks-{self.cluster_name}"
        print_colored("Creating Artifact Registry repository...", "cyan")
        success, _, error = run_command(f"gcloud artifacts repositories create {registry_name} "
                    f"--repository-format=docker "
                    f"--location={self.region} "
                    f"--project={self.project_id}")
        if not success and "already exists" not in error:
            print_colored(f"Failed to create Artifact Registry: {error}", "red")
            sys.exit(1)
        else:
            print_colored(f"Artifact Registry repository '{registry_name}' created or already exists.", "green")

        # Now, set up GKE authentication
        self.setup_gke_authentication()

    def setup_gke_authentication(self):
        """Setup GKE auth with proper Workload Identity"""
        # 1. Create and bind Kubernetes service account
        print_colored("Setting up Kubernetes service account...", "cyan")
        run_command(f"kubectl create namespace {self.namespace} --dry-run=client -o yaml | kubectl apply -f -")
        run_command(f"kubectl create serviceaccount -n {self.namespace} hopsworks-sa")
        
        # Bind the GCP SA to K8s SA
        workload_binding = (
            f"gcloud iam service-accounts add-iam-policy-binding {self.sa_email} "
            f"--role roles/iam.workloadIdentityUser "
            f"--member \"serviceAccount:{self.project_id}.svc.id.goog[{self.namespace}/hopsworks-sa]\""
        )
        run_command(workload_binding)

        # Annotate the K8s SA
        run_command(
            f"kubectl annotate serviceaccount -n {self.namespace} hopsworks-sa "
            f"iam.gke.io/gcp-service-account={self.sa_email}"
        )

        # 2. Setup Docker config for both GCP and hops.works registries
        docker_config = {
            "credHelpers": {
                f"{self.region}-docker.pkg.dev": "gcloud",
                "docker.hops.works": "gcloud"
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(docker_config, f)
            config_file = f.name

        run_command(f"kubectl create configmap docker-config -n {self.namespace} "
                   f"--from-file=config.json={config_file} "
                   f"--dry-run=client -o yaml | kubectl apply -f -")
        
        os.unlink(config_file)
        return True

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
            # Existing AWS logic
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

        elif self.environment == "GCP":
            if self.args.loadbalancer_only:
                cluster_name = input("Enter your GKE cluster name: ").strip()
                self.project_id = input("Enter your GCP project ID: ").strip()
                zone_input = input("Enter your GCP zone (e.g. europe-west1-b): ").strip()
                self.zone = zone_input
                self.region = '-'.join(zone_input.split('-')[:-1])  # extract region from zone
            else:
                # Since we handle GCP kubeconfig in setup_gke_prerequisites, skip here
                cluster_name = self.cluster_name

            cmd = f"gcloud container clusters get-credentials {cluster_name} --project {self.project_id} --zone {self.zone}"
            if not run_command(cmd)[0]:
                print_colored("Failed to get GKE credentials. Check your gcloud setup.", "red")
                return None, None, None

            run_command("gcloud auth configure-docker", verbose=False)
            kubeconfig_path = os.path.expanduser("~/.kube/config")

        elif self.environment == "Azure":
            self.resource_group = input("Enter your Azure resource group name: ").strip()
            cluster_name = input("Enter your AKS cluster name: ").strip()
            cmd = f"az aks get-credentials --resource-group {self.resource_group} --name {cluster_name} --overwrite-existing"
            if not run_command(cmd)[0]:
                print_colored("Failed to get AKS credentials. Check your Azure CLI configuration and permissions.", "red")
                return None, None, None
            kubeconfig_path = os.path.expanduser("~/.kube/config")

        else:
            # Other environments
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
        if self.environment == "GCP":
            tools.append("gcloud")
        elif self.environment == "AWS":
            tools.append("aws")
        elif self.environment == "Azure":
            tools.append("az")
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
        environments = ["AWS", "Azure", "GCP", "OVH"]
        print_colored("Select your deployment environment:", "blue")
        for i, env in enumerate(environments, 1):
            print(f"{i}. {env}")
        choice = get_user_input(
            "Enter the number of your environment:",
            [str(i) for i in range(1, len(environments) + 1)]
        )
        self.environment = environments[int(choice) - 1]

    def get_aws_region(self):
        region = os.environ.get('AWS_REGION')
        if not region:
            region = input("Enter your AWS region (e.g., us-east-2): ").strip()
            os.environ['AWS_REGION'] = region
        return region

    def handle_managed_registry(self):
        if self.environment == "AWS":
            print_colored("Setting up AWS ECR (required for AWS installations)...", "blue")
            self.setup_aws_ecr()
        elif self.environment == "GCP":
            print_colored("Setting up GCP Artifact Registry (required for GKE installations)...", "blue")
            # Namespace is already created in setup_gke_authentication
            if not self.setup_gke_registry():
                print_colored("GCP Artifact Registry setup failed. Cannot proceed with installation.", "red")
                sys.exit(1)

    def setup_aws_ecr(self):
        client = boto3.client('ecr', region_name=self.region)
        base_repo_name = f"hopsworks-{self.cluster_name}/hopsworks-base"
        try:
            response = client.create_repository(repositoryName=base_repo_name)
            repo_uri = response['repository']['repositoryUri']
        except client.exceptions.RepositoryAlreadyExistsException:
            repo_uri = client.describe_repositories(repositoryNames=[base_repo_name])['repositories'][0]['repositoryUri']

        self.managed_registry_info = {
            "domain": repo_uri.split('/')[0],
            "namespace": f"hopsworks-{self.cluster_name}"
        }
        print_colored(f"ECR repository set up: {repo_uri}", "green")

    def setup_gke_registry(self):
        """Setup Artifact Registry"""
        try:
            registry_name = f"hopsworks-{self.cluster_name}"
            # Just confirm the repo exists
            run_command(f"gcloud artifacts repositories describe {registry_name} "
                        f"--location={self.region} "
                        f"--project={self.project_id}")
            self.managed_registry_info = {
                "domain": f"{self.region}-docker.pkg.dev",
                "namespace": f"{self.project_id}/{registry_name}"
            }
            return True

        except Exception as e:
            print_colored(f"Error during GCP Artifact Registry setup: {str(e)}", "red")
            return False

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
        """Installs Hopsworks with proper registry handling for all cloud providers"""
        print_colored("\nInstalling Hopsworks...", "blue")

        if not run_command("helm repo add hopsworks https://nexus.hops.works/repository/hopsworks-helm --force-update")[0]:
            print_colored("Failed to add Hopsworks Helm repo.", "red")
            return False

        print_colored("Updating Helm repositories...", "cyan")
        if not run_command("helm repo update")[0]:
            print_colored("Failed to update Helm repos.", "red")
            return False

        # Base command with common settings
        helm_command = (
            f"helm upgrade --install hopsworks-release hopsworks/hopsworks "
            f"--namespace={self.namespace} "
            f"--create-namespace "
            f"--set global._hopsworks.imagePullPolicy=Always "
            f"--set hopsworks.replicaCount.worker=1 "
            f"--set rondb.clusterSize.activeDataReplicas=1 "
            f"--set hopsworks.service.worker.external.https.type=LoadBalancer "
            f"--set hopsfs.datanode.count=2 "
            f"--set global._hopsworks.imageRegistry=docker.hops.works " 
        )

        # Cloud-specific configurations
        if self.environment == "GCP":
            registry_name = f"hopsworks-{self.cluster_name}"
            helm_command += (
                f" --set global._hopsworks.cloudProvider=GCP"
                f" --set global._hopsworks.managedDockerRegistery.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.domain={self.region}-docker.pkg.dev"
                f" --set global._hopsworks.managedDockerRegistery.namespace={self.project_id}/{registry_name}"
                f" --set global._hopsworks.managedDockerRegistery.credHelper.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.credHelper.secretName=gcrregcred"
                f" --set hopsworks.variables.docker_operations_managed_docker_secrets=gcrregcred"
                f" --set hopsworks.variables.docker_operations_image_pull_secrets=gcrregcred"
                f" --set hopsworks.dockerRegistry.preset.secrets[0]=gcrregcred"
                f" --set serviceAccount.name=hopsworks-sa"  # Use our created SA
                f" --set serviceAccount.annotations.\"iam\\.gke\\.io/gcp-service-account\"={self.sa_email}"
            )

        elif self.environment == "AWS":
            helm_command += (
                f" --set global._hopsworks.cloudProvider=AWS"
                f" --set global._hopsworks.managedDockerRegistery.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.credHelper.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.credHelper.secretName=awsregcred"
                f" --set global._hopsworks.managedDockerRegistery.domain={self.managed_registry_info['domain']}"
                f" --set global._hopsworks.managedDockerRegistery.namespace={self.managed_registry_info['namespace']}"
                # AWS specific registry settings
                f" --set hopsworks.variables.docker_operations_managed_docker_secrets=awsregcred"
                f" --set hopsworks.variables.docker_operations_image_pull_secrets=awsregcred"
                f" --set hopsworks.dockerRegistry.preset.secrets[0]=awsregcred"
            )
        elif self.environment == "Azure":
            helm_command += (
                f" --set global._hopsworks.cloudProvider=AZURE"
                f" --set global._hopsworks.managedDockerRegistery.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.domain={self.managed_registry_info['domain']}"
                f" --set global._hopsworks.managedDockerRegistery.namespace={self.managed_registry_info['namespace']}"
                # Azure typically handles registry auth through AKS integration
            )
        else:  # OVH or others
            helm_command += f" --set global._hopsworks.cloudProvider={self.environment}"

        helm_command += " --timeout 60m --wait --devel"

        print_colored("Starting Hopsworks installation...", "cyan")
        print_colored(f"Using base registry: docker.hops.works", "cyan")
        if self.use_managed_registry:
            print_colored(f"Using managed registry for ML pipelines: {self.managed_registry_info['domain']}", "cyan")

        stop_event = threading.Event()
        status_thread = threading.Thread(target=periodic_status_update, args=(stop_event, self.namespace))
        status_thread.start()

        success, _, _ = run_command(helm_command)

        stop_event.set()
        status_thread.join()

        if not success:
            print_colored("\nHopsworks installation failed.", "red")
            return False

        print_colored("\nHopsworks installation command completed.", "green")
        return wait_for_pods_ready(self.namespace)

    def finalize_installation(self):
        load_balancer_address = self.get_load_balancer_address()
        if not load_balancer_address:
            print_colored("Failed to obtain LoadBalancer address. You may need to configure it manually.", "red")
        else:
            print_colored(f"Hopsworks LoadBalancer address: {load_balancer_address}", "green")

        hopsworks_url = f"https://{load_balancer_address}:443"  # Port 443 for HTTPS
        print_colored(f"Hopsworks UI should be accessible at: {hopsworks_url}", "cyan")
        print_colored("Default login: admin@hopsworks.ai, password: admin", "cyan")

        if health_check(self.namespace):
            print_colored("\nHealth check passed. Hopsworks appears to be running correctly.", "green")
        else:
            print_colored("\nHealth check failed. Please review the installation and check the logs.", "red")

        print_colored("\nInstallation completed!", "green")
        if hasattr(self, 'installation_id') and self.installation_id:
            print_colored(f"Your installation ID is: {self.installation_id}", "green")
        else:
            print_colored("Installation ID not available.", "yellow")
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
        elif self.environment == "Azure":
            cmd = f"kubectl get svc -n {self.namespace} hopsworks-release -o jsonpath='{{.status.loadBalancer.ingress[0].ip}}{{.status.loadBalancer.ingress[0].hostname}}'"
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
                services = dict(line.split('=') for line in output.strip().split('\n') if '=' in line)
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
                print_colored(f"\rWaiting for pods to be created... Do not panic. This will take a moment", "yellow", end='')
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

            readiness_ratio = ready_pods / total_pods if total_pods > 0 else 0
            print_colored(f"\rPods ready: {ready_pods}/{total_pods} ({readiness_ratio:.2%})", "cyan", end='')

            if readiness_ratio >= readiness_threshold and critical_ready == len(critical_pods):
                print_colored(f"\nSufficient pods are ready! ({readiness_ratio:.2%})", "green")
                return True

            time.sleep(5)
        else:
            print_colored("\nFailed to get pod status. Retrying...", "yellow")
            time.sleep(5)

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
