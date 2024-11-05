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
from botocore.exceptions import ClientError

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
INSTALL_RAW = "https://raw.githubusercontent.com/MagicLex/hopsworks-k8s-installer/refs/heads/master/assets"

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
        self.project_id = None  # for GCP
        self.policy_arn = None  # for AWS
        self.use_managed_registry = False
        self.managed_registry_info = None
        self.sa_email = None    # for GCP
        self.role_name = None   # for GCP

    def fetch_and_customize_configs(self):
        """Fetch and customize eksctl and IAM policy configurations"""
        print_colored("Fetching configuration templates...", "cyan")
        
        configs = {
            'eksctl.yaml': '/eksctl.yaml',
            'policy.json': '/policy.json'
        }
        
        for file, remote_path in configs.items():
            try:
                url = f"{INSTALL_RAW}{remote_path}"
                response = urllib.request.urlopen(url)
                content = response.read().decode('utf-8')
                
                if file == 'eksctl.yaml':
                    content = self._customize_eksctl_config(content)
                elif file == 'policy.json':
                    content = self._customize_policy(content)
                    
                with open(file, 'w') as f:
                    f.write(content)
                    
                print_colored(f"Successfully customized {file}", "green")
                
            except Exception as e:
                print_colored(f"Failed to fetch {file}: {str(e)}", "red")
                print_colored("Falling back to local template generation...", "yellow")
                if file == 'eksctl.yaml':
                    self._generate_eksctl_config()
                elif file == 'policy.json':
                    self._generate_policy()

    def _customize_eksctl_config(self, content):
        """Customize the eksctl config template"""
        config = yaml.safe_load(content)
        
        # Update basic metadata
        config['metadata']['name'] = self.cluster_name
        config['metadata']['region'] = self.region
        
        # Update node configuration based on user input
        node_count = input("Enter number of nodes (default: 4): ").strip() or "4"
        instance_type = input("Enter instance type (default: m6i.2xlarge): ").strip() or "m6i.2xlarge"
        
        config['managedNodeGroups'][0].update({
            'minSize': 1,
            'maxSize': int(node_count),
            'desiredCapacity': int(node_count),
            'instanceType': instance_type
        })
        
        return yaml.dump(config)

    def _customize_policy(self, content):
        """Customize the IAM policy template"""
        policy = json.loads(content)
        
        # Update S3 bucket resources
        for statement in policy['Statement']:
            if statement.get('Sid') == 'hopsworksaiInstanceProfile':
                statement['Resource'] = [
                    f"arn:aws:s3:::{self.cluster_name}-bucket/*",
                    f"arn:aws:s3:::{self.cluster_name}-bucket"
                ]
            elif statement.get('Sid') == 'AllowPushandPullImagesToUserRepo':
                statement['Resource'] = [
                    f"arn:aws:ecr:{self.region}:{self._get_account_id()}:repository/*/hopsworks-base"
                ]
        
        return json.dumps(policy, indent=2)

    def _get_account_id(self):
        """Get AWS account ID"""
        return boto3.client('sts').get_caller_identity()['Account']

    def setup_alb_controller(self):
        """Setup AWS Load Balancer Controller"""
        try:
            run_command("kubectl create namespace kube-system --dry-run=client -o yaml | kubectl apply -f -")
        except Exception as e:
            # kube-system probably exists already, which is fine
            pass

        print_colored("Setting up AWS Load Balancer Controller...", "cyan")
        
        # Add helm repo and update
        run_command("helm repo add eks https://aws.github.io/eks-charts")
        run_command("helm repo update eks")
        
        # Create IAM policy for ALB controller
        alb_policy_name = f"AWSLoadBalancerControllerIAMPolicy-{self.cluster_name}"
        
        # Download and apply the ALB policy
        run_command("curl -o alb-policy.json https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.6.1/docs/install/iam_policy.json")
        
        try:
            with open('alb-policy.json', 'r') as policy_file:
                alb_policy = policy_file.read()
                
            iam_client = boto3.client('iam')
            try:
                response = iam_client.create_policy(
                    PolicyName=alb_policy_name,
                    PolicyDocument=alb_policy
                )
                alb_policy_arn = response['Policy']['Arn']
            except iam_client.exceptions.EntityAlreadyExistsException:
                alb_policy_arn = f"arn:aws:iam::{self._get_account_id()}:policy/{alb_policy_name}"
            
            # Create service account for ALB controller
            sa_manifest = f"""
apiVersion: v1
kind: ServiceAccount
metadata:
  name: aws-load-balancer-controller
  namespace: kube-system
  annotations:
    eks.amazonaws.com/role-arn: {alb_policy_arn}
"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(sa_manifest)
                sa_file = f.name
            
            run_command(f"kubectl apply -f {sa_file}")
            os.unlink(sa_file)
            
            # Install ALB controller
            install_cmd = (
                f"helm install aws-load-balancer-controller eks/aws-load-balancer-controller "
                f"-n kube-system "
                f"--set clusterName={self.cluster_name} "
                f"--set serviceAccount.create=false "
                f"--set serviceAccount.name=aws-load-balancer-controller"
            )
            
            if not run_command(install_cmd)[0]:
                print_colored("Failed to install AWS Load Balancer Controller", "red")
                return False
                
            # Create IngressClass
            ingress_class = """
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: alb
  annotations:
    ingressclass.kubernetes.io/is-default-class: "true"
spec:
  controller: ingress.k8s.aws/alb
"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(ingress_class)
                ic_file = f.name
            
            run_command(f"kubectl apply -f {ic_file}")
            os.unlink(ic_file)
            
            return True
            
        except Exception as e:
            print_colored(f"Failed to setup ALB controller: {str(e)}", "red")
            return False

    def setup_aws_prerequisites(self):
        """Setup everything needed before cluster creation for AWS"""
        print_colored("\nSetting up AWS prerequisites...", "blue")
        
        self.region = self.get_aws_region()
        self.cluster_name = input("Enter your EKS cluster name: ").strip() or "hopsworks-cluster"
        
        # Fetch and customize configurations
        self.fetch_and_customize_configs()
        
        # Create ECR repository with proper error handling
        print_colored("Setting up ECR repository...", "cyan")
        repo_name = f"{self.cluster_name}/hopsworks-base"
        try:
            ecr_client = boto3.client('ecr', region_name=self.region)
            try:
                ecr_client.create_repository(repositoryName=repo_name)
                print_colored(f"Created ECR repository: {repo_name}", "green")
            except ecr_client.exceptions.RepositoryAlreadyExistsException:
                print_colored(f"Using existing ECR repository: {repo_name}", "yellow")
        except Exception as e:
            print_colored(f"ECR setup failed: {str(e)}", "red")
            sys.exit(1)

        # Create the cluster with proper feedback
        print_colored("Creating EKS cluster (estimated time: 15-20 minutes)...", "cyan")
        
        if not run_command(f"eksctl create cluster -f eksctl.yaml")[0]:
            print_colored("Failed to create EKS cluster", "red")
            sys.exit(1)
       
        print_colored("Waiting for cluster API to be fully ready...", "cyan")
        time.sleep(30)  # Simple but effective

        # Setup ALB controller
        if not self.setup_alb_controller():
            print_colored("Failed to setup AWS Load Balancer Controller", "red")
            sys.exit(1)

        print_colored("AWS prerequisites setup completed successfully!", "green")

    def get_aws_region(self):
        region = os.environ.get('AWS_REGION')
        if not region:
            region = input("Enter your AWS region (e.g., us-east-2): ").strip()
            os.environ['AWS_REGION'] = region
        return region

    def run(self):
        print_colored(HOPSWORKS_LOGO, "white")
        self.parse_arguments()
        self.get_deployment_environment()
        self.check_required_tools()

        if not self.args.loadbalancer_only:
            # This is where we branch based on cloud provider
            if self.environment == "GCP":
                self.setup_gke_prerequisites()
            elif self.environment == "AWS":
                self.setup_aws_prerequisites()  # Our new method
            else:
                self.setup_and_verify_kubeconfig()

            self.handle_managed_registry()
            self.handle_license_and_user_data()
            if self.install_hopsworks():
                print_colored("\nHopsworks installation completed.", "green")
                self.finalize_installation()
            else:
                print_colored("Hopsworks installation failed. Please check the logs and try again.", "red")
                self.clean_up_resources()
                sys.exit(1)
        else:
            self.namespace = self.args.namespace
            self.setup_and_verify_kubeconfig()
            self.finalize_installation()

    def check_required_tools(self):
        """Update the required tools check"""
        if self.environment == "AWS":
            tools = ["kubectl", "helm", "aws", "eksctl"]  # Added eksctl
        elif self.environment == "GCP":
            tools = ["kubectl", "helm", "gcloud"]
        else:
            tools = ["kubectl", "helm"]

        for tool in tools:
            if not shutil.which(tool):
                print_colored(f"{tool} not found. Please install it and try again.", "red")
                sys.exit(1)
    def parse_arguments(self):
        """Parse command line arguments"""
        parser = argparse.ArgumentParser(description="Hopsworks Installation Script")
        parser.add_argument('--loadbalancer-only', 
                        action='store_true', 
                        help='Jump directly to the LoadBalancer setup')
        parser.add_argument('--no-user-data', 
                        action='store_true', 
                        help='Skip sending user data')
        parser.add_argument('--skip-license', 
                        action='store_true', 
                        help='Skip license agreement step')
        parser.add_argument('--namespace', 
                        default='hopsworks', 
                        help='Namespace for Hopsworks installation')
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

    def handle_managed_registry(self):
        """Update registry handling for AWS"""
        if self.environment == "AWS":
            if not self.args.loadbalancer_only:
                # Registry is already set up in prerequisites
                print_colored("Using AWS ECR registry configured during prerequisites...", "blue")
                account_id = boto3.client('sts').get_caller_identity()['Account']
                repo_uri = f"{account_id}.dkr.ecr.{self.region}.amazonaws.com"
                self.managed_registry_info = {
                    "domain": repo_uri,
                    "namespace": f"{self.cluster_name}"
                }
            else:
                print_colored("Setting up AWS ECR...", "blue")
                self.setup_aws_ecr()
        elif self.environment == "GCP":
            print_colored("Setting up GCP Artifact Registry...", "blue")
            if not self.setup_gke_registry():
                print_colored("GCP Artifact Registry setup failed. Cannot proceed with installation.", "red")
                sys.exit(1)

    def clean_up_resources(self):
        """Add cleanup method for when things go wrong"""
        if self.environment == "AWS" and hasattr(self, 'policy_arn'):
            try:
                iam_client = boto3.client('iam')
                iam_client.delete_policy(PolicyArn=self.policy_arn)
                print_colored(f"Cleaned up IAM policy: {self.policy_arn}", "green")
            except Exception as e:
                print_colored(f"Failed to clean up IAM policy: {str(e)}", "yellow")
        # Add other cleanup tasks as needed

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

        # Basic helm repo setup
        if not run_command("helm repo add hopsworks https://nexus.hops.works/repository/hopsworks-helm --force-update")[0]:
            print_colored("Failed to add Hopsworks Helm repo.", "red")
            return False

        print_colored("Updating Helm repositories...", "cyan")
        if not run_command("helm repo update")[0]:
            print_colored("Failed to update Helm repos.", "red")
            return False

        # Clean up any existing chart directory
        if os.path.exists('hopsworks'):
            shutil.rmtree('hopsworks', ignore_errors=True)

        print_colored("Pulling Hopsworks Helm chart...", "cyan")
        if not run_command("helm pull hopsworks/hopsworks --untar --devel")[0]:
            print_colored("Failed to pull Hopsworks chart.", "red")
            return False

        # Base command with common settings
        helm_command = (
            f"helm upgrade --install hopsworks-release hopsworks/hopsworks "
            f"--namespace={self.namespace} "
            f"--create-namespace "
            f"--values hopsworks/values.yaml "
            f"--set hopsworks.service.worker.external.https.type=LoadBalancer "
        )

        # Cloud-specific configurations
        if self.environment == "OVH":
            helm_command = (
                f"{helm_command}"
                f" --set global._hopsworks.cloudProvider=OVH"
            )

        elif self.environment == "GCP":
            registry_name = f"hopsworks-{self.cluster_name}"
            helm_command = (
                f"{helm_command}"
                f" --set global._hopsworks.cloudProvider=GCP"
                f" --set global._hopsworks.managedDockerRegistery.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.domain={self.region}-docker.pkg.dev"
                f" --set global._hopsworks.managedDockerRegistery.namespace={self.project_id}/{registry_name}"
                f" --set global._hopsworks.managedDockerRegistery.credHelper.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.credHelper.secretName=gcrregcred"
                f" --set hopsworks.variables.docker_operations_managed_docker_secrets=gcrregcred"
                f" --set hopsworks.variables.docker_operations_image_pull_secrets=gcrregcred"
                f" --set hopsworks.dockerRegistry.preset.secrets[0]=gcrregcred"
                f" --set serviceAccount.name=hopsworks-sa"
                f" --set serviceAccount.annotations.\"iam\\.gke\\.io/gcp-service-account\"={self.sa_email}"
                f" --set global._hopsworks.imagePullPolicy=Always"
                f" --set hopsworks.replicaCount.worker=1"
                f" --set rondb.clusterSize.activeDataReplicas=1"
                f" --set hopsfs.datanode.count=2"
            )

        elif self.environment == "AWS":
            # Create namespace first
            run_command(f"kubectl create namespace {self.namespace}")
            
            # Get account ID for ECR domain
            account_id = boto3.client('sts').get_caller_identity()['Account']
            ecr_domain = f"{account_id}.dkr.ecr.{self.region}.amazonaws.com"
            
            print_colored("Setting up AWS-specific Kubernetes secrets...", "cyan")
            
            # Create docker-registry secret for ECR
            run_command(
                f"kubectl create secret docker-registry awsregcred "
                f"--docker-server={ecr_domain} "
                f"--namespace={self.namespace} "
                f"--docker-username=AWS "
                f"--docker-password=$(aws ecr get-login-password --region {self.region})"
            )

            # Create service account with proper annotations
            service_account_yaml = f"""
apiVersion: v1
kind: ServiceAccount
metadata:
name: hopsworks-sa
namespace: {self.namespace}
annotations:
    eks.amazonaws.com/role-arn: {self.policy_arn}
"""
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(service_account_yaml)
                sa_file = f.name

            run_command(f"kubectl apply -f {sa_file}")
            os.unlink(sa_file)

            helm_command = (
                f"{helm_command}"
                f" --set global._hopsworks.cloudProvider=AWS"
                f" --set global._hopsworks.managedDockerRegistery.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.credHelper.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.credHelper.secretName=awsregcred"
                f" --set global._hopsworks.managedDockerRegistery.domain={ecr_domain}"
                f" --set global._hopsworks.managedDockerRegistery.namespace={self.cluster_name}"
                f" --set hopsworks.variables.docker_operations_managed_docker_secrets=awsregcred"
                f" --set hopsworks.variables.docker_operations_image_pull_secrets=awsregcred"
                f" --set hopsworks.dockerRegistry.preset.secrets[0]=awsregcred"
                f" --set serviceAccount.name=hopsworks-sa"
                f" --set serviceAccount.annotations.\"eks\\.amazonaws\\.com/role-arn\"={self.policy_arn}"
                # AWS specific storage classes
                f" --set global._hopsworks.storageClassName=gp3"
                f" --set rondb.storageClass=gp3"
                f" --set elastic.persistentVolume.storageClassName=gp3"
                f" --set filebeat.persistentVolume.storageClassName=gp3"
                f" --set kafka.persistentVolume.storageClassName=gp3"
                f" --set onlinefs.persistentVolume.storageClassName=gp3"
                # Standard optimizations
                f" --set global._hopsworks.imagePullPolicy=Always"
                f" --set hopsworks.replicaCount.worker=1"
                f" --set rondb.clusterSize.activeDataReplicas=1"
                f" --set hopsfs.datanode.count=2"
                # AWS Load Balancer annotations
                f" --set hopsworks.service.worker.external.https.annotations.\"service\\.beta\\.kubernetes\\.io/aws-load-balancer-type\"=nlb"
                f" --set hopsworks.service.worker.external.https.annotations.\"service\\.beta\\.kubernetes\\.io/aws-load-balancer-nlb-target-type\"=ip"
                f" --set hopsworks.service.worker.external.https.annotations.\"service\\.beta\\.kubernetes\\.io/aws-load-balancer-scheme\"=internet-facing"
                # Update ingress class to use ALB
                f" --set hopsworks.ingress.class=alb"
            )

        elif self.environment == "Azure":
            helm_command = (
                f"{helm_command}"
                f" --set global._hopsworks.cloudProvider=AZURE"
                f" --set global._hopsworks.managedDockerRegistery.enabled=true"
                f" --set global._hopsworks.managedDockerRegistery.domain={self.managed_registry_info['domain']}"
                f" --set global._hopsworks.managedDockerRegistery.namespace={self.managed_registry_info['namespace']}"
                f" --set global._hopsworks.imagePullPolicy=Always"
                f" --set hopsworks.replicaCount.worker=1"
                f" --set rondb.clusterSize.activeDataReplicas=1"
                f" --set hopsfs.datanode.count=2"
            )

        # Add timeout for all installations
        helm_command += " --timeout 60m --wait --devel"

        print_colored("Starting Hopsworks installation...", "cyan")

        # Start the status update thread
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

    def get_load_balancer_port(self):
            cmd = f"kubectl get svc -n {self.namespace} hopsworks-release -o jsonpath='{{.spec.ports[?(@.name==\"https\")].port}}'"
            success, output, _ = run_command(cmd, verbose=False)
            if success and output.strip():
                return output.strip()
            else:
                # Fallback to checking node port
                print_colored("Failed to get LoadBalancer port directly, checking node port...", "yellow")
                cmd = f"kubectl get svc -n {self.namespace} hopsworks-release -o jsonpath='{{.spec.ports[?(@.name==\"https\")].nodePort}}'"
                success, output, _ = run_command(cmd, verbose=False)
                return output.strip() if success and output.strip() else "28181"  # Default fallback

    def finalize_installation(self):
        load_balancer_address = self.get_load_balancer_address()
        if not load_balancer_address:
            print_colored("Failed to obtain LoadBalancer address. You may need to configure it manually.", "red")
        else:
            print_colored(f"Hopsworks LoadBalancer address: {load_balancer_address}", "green")

        port = self.get_load_balancer_port()
        hopsworks_url = f"https://{load_balancer_address}:{port}"
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
                
            # Add manual override after 5 minutes if we hit the threshold
            if time.time() - start_time > 10:  # 5 minutes passed
                if readiness_ratio >= readiness_threshold:
                    print()  # New line for cleaner output
                    proceed = get_user_input("\nMost of the pods are ready! Proceed? (yes/no): ", ["yes", "no"])
                    if proceed.lower() == "yes":
                        print_colored("Proceeding with installation...", "yellow")
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
