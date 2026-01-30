# This file is part of Hopsworks
# Copyright (C) 2024, Hopsworks AB. All rights reserved
#
# Hopsworks is free software: you can redistribute it and/or modify it under the terms of
# the GNU Affero General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.
#
# Hopsworks is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.
# If not, see <https://www.gnu.org/licenses/>.
 
import subprocess
import time
import sys
import os
import shutil
import argparse
import threading
import boto3
import json
import tempfile
import yaml

# Load .env file if present
def load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_dotenv()

HOPSWORKS_LOGO = """
██╗  ██╗    ██████╗    ██████╗    ███████╗   ██╗    ██╗    ██████╗    ██████╗    ██╗  ██╗   ███████╗
██║  ██║   ██╔═══██╗   ██╔══██╗   ██╔════╝   ██║    ██║   ██╔═══██╗   ██╔══██╗   ██║ ██╔╝   ██╔════╝
███████║   ██║   ██║   ██████╔╝   ███████╗   ██║ █╗ ██║   ██║   ██║   ██████╔╝   █████╔╝    ███████╗
██╔══██║   ██║   ██║   ██╔═══╝    ╚════██║   ██║███╗██║   ██║   ██║   ██╔══██╗   ██╔═██╗    ╚════██║
██║  ██║   ╚██████╔╝   ██║        ███████║   ╚███╔███╔╝   ╚██████╔╝   ██║  ██║   ██║  ██╗   ███████║
╚═╝  ╚═╝    ╚═════╝    ╚═╝        ╚══════╝    ╚══╝╚══╝     ╚═════╝    ╚═╝  ╚═╝   ╚═╝  ╚═╝   ╚══════╝
"""

KNOWN_NONFATAL_ERRORS = [
    "invalid ingress class: IngressClass.networking.k8s.io",
]

""" All the helm stuff here ⬇ """
HELM_BASE_CONFIG = {
    "hopsworks.service.worker.external.https.type": "LoadBalancer",
    "global._hopsworks.externalLoadBalancers.enabled": "true",
    "global._hopsworks.imagePullPolicy": "Always",
    "hopsworks.replicaCount.worker": "1",
    "rondb.rondb.clusterSize.activeDataReplicas": "1",
    "hopsfs.datanode.count": "2"
}

CLOUD_SPECIFIC_VALUES = {
    "AWS": {
        "global._hopsworks.cloudProvider": "AWS",
        "global._hopsworks.managedDockerRegistery.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.secretName": "awsregcred",
        "global._hopsworks.storageClassName": "ebs-gp3",
        "global._hopsworks.externalLoadBalancers.annotations.service\\.beta\\.kubernetes\\.io/aws-load-balancer-scheme": "internet-facing",
        "hopsworks.variables.docker_operations_managed_docker_secrets": "awsregcred",
        "hopsworks.variables.docker_operations_image_pull_secrets": "awsregcred",
        "hopsworks.dockerRegistry.preset.secrets[0]": "awsregcred"
    },
    "GCP": {
        "global._hopsworks.cloudProvider": "GCP",
        "global._hopsworks.managedDockerRegistery.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.configMap": "docker-config",
        "global._hopsworks.managedDockerRegistery.credHelper.secretName": "gcrregcred",
        "global._hopsworks.serviceAccount.name": "hopsworks-sa",
        "hopsworks.variables.docker_operations_managed_docker_secrets": "gcrregcred",
        "hopsworks.variables.docker_operations_image_pull_secrets": "gcrregcred",
        "hopsworks.dockerRegistry.preset.secrets[0]": "gcrregcred"
    },
    "Azure": {
        "global._hopsworks.cloudProvider": "AZURE",
        "global._hopsworks.minio.enabled": "true",
        "global._hopsworks.storageClassName": "managed-csi",
        "global._hopsworks.imagePullSecrets[0].name": "regcred",
        "global._hopsworks.serviceAccount.name": "hopsworks-sa",
        "global._hopsworks.serviceAccount.create": "false",
        "global._hopsworks.externalLoadBalancers.annotations.service\\.beta\\.kubernetes\\.io/azure-load-balancer-internal": "false"
    },
    "OVH": {
        "global._hopsworks.cloudProvider": "OVH"
    }
}

# Utilities 

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

def get_user_input(prompt, options=None, default=None, validator=None):
    """Get validated user input with optional default and custom validation"""
    if default:
        prompt = f"{prompt} (default: {default})"

    while True:
        response = input(prompt + " ").strip()

        # Handle default
        if not response and default is not None:
            return default

        # Handle empty required input
        if not response and default is None and options is None:
            print_colored("This field is required. Please provide a value.", "yellow")
            continue

        # Handle options
        if options and response.lower() not in [option.lower() for option in options]:
            print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "yellow")
            continue

        # Handle custom validator
        if validator:
            is_valid, error_msg = validator(response)
            if not is_valid:
                print_colored(error_msg, "yellow")
                continue

        return response

def validate_cluster_name(name):
    """Validate Kubernetes cluster name (DNS-1123 subdomain)"""
    if not name:
        return False, "Cluster name cannot be empty."
    if len(name) > 63:
        return False, "Cluster name must be 63 characters or less."
    if not name.islower() or not all(c.isalnum() or c == '-' for c in name):
        return False, "Cluster name must be lowercase and can only contain alphanumeric characters and hyphens."
    if not name[0].isalnum() or not name[-1].isalnum():
        return False, "Cluster name must start and end with an alphanumeric character."
    return True, None

def validate_bucket_name(name):
    """Validate S3 bucket name"""
    if not name:
        return False, "Bucket name cannot be empty."
    if len(name) < 3 or len(name) > 63:
        return False, "Bucket name must be between 3 and 63 characters."
    if any(c.isupper() for c in name):
        return False, "Bucket name must be lowercase."
    if not all(c.isalnum() or c in '-.' for c in name):
        return False, "Bucket name can only contain lowercase letters, numbers, hyphens, and periods."
    if name.startswith('-') or name.endswith('-') or name.startswith('.') or name.endswith('.'):
        return False, "Bucket name cannot start or end with a hyphen or period."
    return True, None

def validate_non_empty(value):
    """Simple non-empty validator"""
    if not value or not value.strip():
        return False, "This field cannot be empty."
    return True, None

def display_config_summary(config):
    """Display configuration summary and ask for confirmation"""
    print_colored("\n" + "="*60, "cyan")
    print_colored("CONFIGURATION SUMMARY", "cyan")
    print_colored("="*60, "cyan")

    for key, value in config.items():
        if value:  # Only show non-empty values
            print(f"  {key}: {value}")

    print_colored("="*60, "cyan")

    confirm = get_user_input("\nProceed with this configuration? (yes/no)", options=["yes", "no"])
    return confirm.lower() == "yes"

# Main installer
class HopsworksInstaller:
    def __init__(self):
            # Common attributes
            self.environment = None
            self.kubeconfig_path = None
            self.cluster_name = None
            self.region = None
            self.zone = None
            self.namespace = 'hopsworks'
            self.args = None

            # GCP specific
            self.project_id = None
            self.sa_email = None
            self.role_name = None

            # Registry handling
            self.use_managed_registry = False
            self.managed_registry_info = None

            # AWS specific
            self.aws_profile = None
            self.aws_account_id = None
            self.policy_name = None

            # Azure specific
            self.resource_group = None
            self.registry_secrets_created = False

            # Temp file tracking
            self.temp_files = []

    def cleanup_temp_files(self):
        """Clean up all temporary files created during installation"""
        for file in self.temp_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    print_colored(f"Cleaned up temporary file: {file}", "cyan")
                except Exception as e:
                    print_colored(f"Warning: Could not remove {file}: {e}", "yellow")

    def run(self):
        print_colored(HOPSWORKS_LOGO, "white")
        self.parse_arguments()
        self.check_required_tools()
        self.get_deployment_environment()

        try:
            if not self.args.loadbalancer_only:
                if self.environment == "GCP":
                    self.setup_gke_prerequisites()
                elif self.environment == "AWS":
                    self.setup_aws_prerequisites()
                elif self.environment == "Azure":
                    self.setup_aks_prerequisites()  # This will create the cluster
                else:
                    self.setup_and_verify_kubeconfig()  # Only for other environments

                self.handle_managed_registry()
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
        finally:
            # Always cleanup temp files
            if self.temp_files:
                print_colored("\nCleaning up temporary files...", "cyan")
                self.cleanup_temp_files()
                
    def construct_helm_command(self):
            """Constructs the helm command with proper configuration"""
            # Base helm command
            helm_command = [
                "helm upgrade --install hopsworks-release hopsworks-dev/hopsworks",
                f"--namespace={self.namespace}",
                "--create-namespace",
                "--values hopsworks/values.yaml",
                "--set hopsworks.velero.backup.enabled=false"  # Velero not needed for dev installs
            ]
            
            # Helper function to flatten nested dictionaries
            def flatten_dict(d, parent_key='', sep='.'):
                items = []
                for k, v in d.items():
                    new_key = f"{parent_key}{sep}{k}" if parent_key else k
                    if isinstance(v, dict):
                        items.extend(flatten_dict(v, new_key, sep=sep).items())
                    else:
                        items.append((new_key, v))
                return dict(items)

            # Start with base config
            helm_values = HELM_BASE_CONFIG.copy()
            
            # Add cloud-specific values
            if self.environment in CLOUD_SPECIFIC_VALUES:
                cloud_config = CLOUD_SPECIFIC_VALUES[self.environment].copy()
                
                # Handle registry values for each cloud provider
                if self.environment == "AWS" and self.managed_registry_info:
                    cloud_config.update({
                        "global._hopsworks.managedDockerRegistery.domain": self.managed_registry_info['domain'],
                        "global._hopsworks.managedDockerRegistery.namespace": self.managed_registry_info['namespace']
                    })
                    
                elif self.environment == "GCP" and self.managed_registry_info:
                    cloud_config.update({
                        "global._hopsworks.managedDockerRegistery.domain": self.managed_registry_info['domain'],
                        "global._hopsworks.managedDockerRegistery.namespace": self.managed_registry_info['namespace'],
                        "global._hopsworks.serviceAccount.annotations.iam\\.gke\\.io/gcp-service-account": self.sa_email
                    })
                    
                elif self.environment == "Azure":
                    # Azure uses regcred secret which is already configured in base cloud config
                    if not self.registry_secrets_created:
                        print_colored("Warning: Azure registry secrets not properly configured", "yellow")
                
                helm_values.update(cloud_config)

            # Flatten nested structures
            flat_values = flatten_dict(helm_values)
            
            # Add each value with proper escaping and formatting
            for key, value in flat_values.items():
                if value is None:
                    value = "null"
                elif isinstance(value, bool):
                    value = str(value).lower()
                elif isinstance(value, (int, float)):
                    value = str(value)
                else:
                    # Escape special characters in string values
                    value = f'"{str(value)}"'
                
                helm_command.append(f"--set {key}={value}")

            # Add timeout
            helm_command.append("--timeout 60m")

            # Add version if specified
            if self.args.version:
                helm_command.append(f"--version {self.args.version}")

            # Always add devel flag for dev repo (alpha/rc versions)
            helm_command.append("--devel")

            return " ".join(helm_command)
    def setup_aws_prerequisites(self):
        """Setup AWS prerequisites including metrics server"""
        print_colored("\nSetting up AWS prerequisites...", "blue")

        # 1. Basic AWS setup and verification
        self.aws_profile = get_user_input("Enter your AWS profile name", default="default")
        os.environ['AWS_PROFILE'] = self.aws_profile

        # Verify AWS credentials
        print_colored("Verifying AWS credentials...", "cyan")
        cmd = f"aws sts get-caller-identity --profile {self.aws_profile}"
        if not run_command(cmd, verbose=False)[0]:
            print_colored("AWS CLI not properly configured.", "red")
            print_colored(f"Please run 'aws configure --profile {self.aws_profile}' and try again.", "yellow")
            sys.exit(1)

        # Get basic info
        self.region = self.get_aws_region()
        self.cluster_name = get_user_input("Enter your EKS cluster name", validator=validate_cluster_name)

        # Get AWS account ID
        cmd = f"aws sts get-caller-identity --query Account --output text --profile {self.aws_profile}"
        success, account_id, _ = run_command(cmd, verbose=False)
        if not success:
            print_colored("Failed to get AWS account ID.", "red")
            sys.exit(1)
        self.aws_account_id = account_id.strip()

        # 2. Get S3 bucket name
        bucket_name = get_user_input("Enter S3 bucket name for Hopsworks data", validator=validate_bucket_name)

        # 3. Get cluster configuration
        print_colored("\nCluster configuration...", "cyan")
        instance_type = get_user_input("Enter instance type", default="m6i.2xlarge")
        node_count = get_user_input("Enter number of nodes", default="4")

        # Display summary and confirm
        config_summary = {
            "Cloud Provider": "AWS",
            "AWS Profile": self.aws_profile,
            "Region": self.region,
            "Cluster Name": self.cluster_name,
            "Instance Type": instance_type,
            "Node Count": node_count,
            "S3 Bucket": bucket_name,
            "Namespace": self.namespace
        }

        if not display_config_summary(config_summary):
            print_colored("Installation cancelled by user.", "yellow")
            sys.exit(0)

        # 4. Create S3 bucket (or use existing)
        print_colored("\nCreating AWS resources...", "blue")
        cmd = f"aws s3 mb s3://{bucket_name} --region {self.region} --profile {self.aws_profile}"
        success, _, stderr = run_command(cmd)
        if not success:
            if "BucketAlreadyOwnedByYou" in stderr or "BucketAlreadyExists" in stderr:
                print_colored(f"S3 bucket '{bucket_name}' already exists, using existing bucket.", "yellow")
            else:
                print_colored("Failed to create S3 bucket.", "red")
                print_colored("Possible causes:", "yellow")
                print("  - Bucket name already exists globally (owned by someone else)")
                print("  - Insufficient IAM permissions")
                print("  - Invalid bucket name format")
                sys.exit(1)
        
        # Enable versioning on the bucket
        cmd = f"aws s3api put-bucket-versioning --bucket {bucket_name} --versioning-configuration Status=Enabled --profile {self.aws_profile}"
        if not run_command(cmd)[0]:
            print_colored("Failed to enable bucket versioning", "red")
            sys.exit(1)

        # 3. Create IAM policy
        print_colored("\nCreating IAM policies...", "cyan")
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "HopsworksS3Access",
                    "Effect": "Allow",
                    "Action": [
                        "S3:PutObject", "S3:ListBucket", "S3:GetObject", "S3:DeleteObject",
                        "S3:AbortMultipartUpload", "S3:ListBucketMultipartUploads",
                        "S3:PutLifecycleConfiguration", "S3:GetLifecycleConfiguration",
                        "S3:PutBucketVersioning", "S3:GetBucketVersioning",
                        "S3:ListBucketVersions", "S3:DeleteObjectVersion"
                    ],
                    "Resource": [
                        f"arn:aws:s3:::{bucket_name}/*",
                        f"arn:aws:s3:::{bucket_name}"
                    ]
                },
                {
                    "Sid": "HopsworksECRAccess",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage",
                        "ecr:CompleteLayerUpload", "ecr:UploadLayerPart",
                        "ecr:InitiateLayerUpload", "ecr:BatchCheckLayerAvailability",
                        "ecr:PutImage", "ecr:ListImages", "ecr:BatchDeleteImage",
                        "ecr:GetLifecyclePolicy", "ecr:PutLifecyclePolicy",
                        "ecr:TagResource"
                    ],
                    "Resource": [f"arn:aws:ecr:{self.region}:{self.aws_account_id}:repository/*/hopsworks-base"]
                },
                {
                    "Sid": "HopsworksECRAuthToken",
                    "Effect": "Allow",
                    "Action": ["ecr:GetAuthorizationToken"],
                    "Resource": "*"
                },
                {
                    "Sid": "LoadBalancerAccess",
                    "Effect": "Allow",
                    "Action": [
                        "elasticloadbalancing:*", "ec2:CreateTags", "ec2:DeleteTags",
                        "ec2:DescribeAccountAttributes", "ec2:DescribeAddresses",
                        "ec2:DescribeInstances", "ec2:DescribeInternetGateways",
                        "ec2:DescribeNetworkInterfaces", "ec2:DescribeSecurityGroups",
                        "ec2:DescribeSubnets", "ec2:DescribeTags", "ec2:DescribeVpcs",
                        "ec2:ModifyNetworkInterfaceAttribute", 
                        "ec2:DescribeInstanceTypes",        # Added for RSS management
                        "ec2:DescribeInstanceTypeOfferings", # Added for RSS management
                        "iam:CreateServiceLinkedRole", "iam:ListServerCertificates", 
                        "cognito-idp:DescribeUserPoolClient",
                        "acm:ListCertificates", "acm:DescribeCertificate",
                        "waf-regional:*", "wafv2:*", "shield:*"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        timestamp = int(time.time())
        policy_file = f'policy-{timestamp}.json'
        with open(policy_file, 'w') as f:
            json.dump(policy, f, indent=2)
        self.temp_files.append(policy_file)

        self.policy_name = f"hopsworks-policy-{timestamp}"
        cmd = f"aws iam create-policy --policy-name {self.policy_name} --policy-document file://{policy_file} --profile {self.aws_profile}"
        if not run_command(cmd)[0]:
            print_colored("Failed to create IAM policy", "red")
            sys.exit(1)

        print_colored("Waiting for policy to propagate...", "yellow")
        time.sleep(10)

        # 5. Create EKS cluster configuration
        print_colored("\nCreating EKS cluster configuration...", "cyan")
        cluster_config = {
            "apiVersion": "eksctl.io/v1alpha5",
            "kind": "ClusterConfig",
            "metadata": {
                "name": self.cluster_name,
                "region": self.region,
                "version": "1.29"
            },
            "iam": {
                "withOIDC": True,
            },
            "addons": [{
                "name": "aws-ebs-csi-driver",
                "wellKnownPolicies": {
                    "ebsCSIController": True
                }
            }],
            "managedNodeGroups": [{
                "name": "ng-1",
                "amiFamily": "AmazonLinux2023",
                "instanceType": instance_type,
                "minSize": int(node_count),
                "maxSize": int(node_count),
                "volumeSize": 100,
                "ssh": {
                    "allow": True
                },
                "iam": {
                    "attachPolicyARNs": [
                        "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
                        "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
                        "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
                        f"arn:aws:iam::{self.aws_account_id}:policy/{self.policy_name}"
                    ],
                    "withAddonPolicies": {
                        "awsLoadBalancerController": True
                    }
                }
            }]
        }

        eksctl_file = f'eksctl-{timestamp}.yaml'
        with open(eksctl_file, 'w') as f:
            yaml.dump(cluster_config, f)
        self.temp_files.append(eksctl_file)

        # 6. Create EKS cluster
        print_colored("\nCreating EKS cluster (this will take 15-20 minutes)...", "cyan")
        cmd = f"eksctl create cluster -f {eksctl_file} --profile {self.aws_profile}"
        if not run_command(cmd)[0]:
            print_colored("Failed to create EKS cluster.", "red")
            print_colored("Check eksctl output above for details. Common issues:", "yellow")
            print("  - VPC or subnet limits reached")
            print("  - Insufficient IAM permissions")
            print("  - Instance type not available in region")
            sys.exit(1)

        # 7. Create GP3 storage class
        print_colored("\nCreating GP3 storage class...", "cyan")
        storage_class = {
            "apiVersion": "storage.k8s.io/v1",
            "kind": "StorageClass",
            "metadata": {
                "name": "ebs-gp3"
            },
            "provisioner": "ebs.csi.aws.com",
            "parameters": {
                "type": "gp3",
                "csi.storage.k8s.io/fstype": "xfs"
            },
            "volumeBindingMode": "WaitForFirstConsumer",
            "reclaimPolicy": "Delete"
        }
        
        storage_file = f'storage-class-{timestamp}.yaml'
        with open(storage_file, 'w') as f:
            yaml.dump(storage_class, f)
        self.temp_files.append(storage_file)

        if not run_command(f"kubectl apply -f {storage_file}")[0]:
            print_colored("Failed to create GP3 storage class", "red")
            sys.exit(1)

        # 8. Set up AWS Load Balancer Controller
        print_colored("\nSetting up AWS Load Balancer Controller...", "cyan")
        
        # Download and create ALB policy
        alb_policy_file = "iam_policy_alb.json"
        cmd = f"curl -o {alb_policy_file} https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.2/docs/install/iam_policy.json"
        if not run_command(cmd)[0]:
            print_colored("Failed to download ALB policy", "red")
            sys.exit(1)
        self.temp_files.append(alb_policy_file)

        alb_policy_name = f"AWSLoadBalancerControllerIAMPolicy-{self.cluster_name}-{timestamp}"
        cmd = f"aws iam create-policy --policy-name {alb_policy_name} --policy-document file://{alb_policy_file} --profile {self.aws_profile}"
        run_command(cmd)  # Ignore if policy exists

        # Create service account with explicit role
        print_colored("\nCreating service account for Load Balancer Controller...", "cyan")
        cmd = (f"eksctl create iamserviceaccount "
            f"--cluster={self.cluster_name} "
            f"--namespace=kube-system "
            f"--name=aws-load-balancer-controller "
            f"--role-name=AmazonEKSLoadBalancerControllerRole-{self.cluster_name} "
            f"--attach-policy-arn=arn:aws:iam::{self.aws_account_id}:policy/{alb_policy_name} "
            f"--override-existing-serviceaccounts "
            f"--approve "
            f"--region={self.region}")

        if not run_command(cmd)[0]:
            print_colored("Failed to create service account for ALB controller", "red")
            sys.exit(1)

        # Install AWS Load Balancer Controller
        print_colored("\nInstalling AWS Load Balancer Controller...", "cyan")
        cmd = (f"helm install aws-load-balancer-controller eks/aws-load-balancer-controller "
            f"-n kube-system "
            f"--set clusterName={self.cluster_name} "
            f"--set serviceAccount.create=false "
            f"--set serviceAccount.name=aws-load-balancer-controller "
            f"--set region={self.region} "
            f"--set vpcId=$(aws eks describe-cluster --name {self.cluster_name} --query \"cluster.resourcesVpcConfig.vpcId\" --output text --region {self.region}) "
            f"--set image.repository=602401143452.dkr.ecr.{self.region}.amazonaws.com/amazon/aws-load-balancer-controller "
            "--set enableServiceMutatorWebhook=false")

        if not run_command(cmd)[0]:
            print_colored("Failed to install AWS Load Balancer Controller", "red")
            sys.exit(1)

        # 9. Install and configure metrics server
        print_colored("\nInstalling metrics server...", "cyan")
        metrics_cmd = """
        kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/high-availability-1.21+.yaml && \
        kubectl patch deployment metrics-server -n kube-system --type=json \
        -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'
        """
        if not run_command(metrics_cmd)[0]:
            print_colored("Failed to install metrics server. Some monitoring features might be limited.", "yellow")
        else:
            print_colored("Metrics server installed and patched for EKS.", "green")

        # 10. Verify final deployment
        print_colored("\nVerifying AWS Load Balancer Controller deployment...", "cyan")
        max_retries = 12
        for i in range(max_retries):
            cmd = "kubectl get deployment -n kube-system aws-load-balancer-controller"
            success, output, _ = run_command(cmd, verbose=False)
            if success and "1/1" in output:
                print_colored("AWS Load Balancer Controller is ready!", "green")
                break
            if i < max_retries - 1:
                print_colored(f"Waiting for controller to be ready (attempt {i+1}/{max_retries})...", "yellow")
                time.sleep(10)

        print_colored("\nAWS prerequisites setup completed successfully!", "green")
        return True

    def setup_gke_prerequisites(self):
        """Setup everything needed before cluster creation"""
        print_colored("\nSetting up GKE prerequisites...", "blue")

        # 1. Get essential info first
        self.project_id = get_user_input("Enter your GCP project ID", validator=validate_non_empty)
        print_colored("Note: Use a specific zone (e.g., europe-west1-b) to avoid multi-zone deployments.", "yellow")
        zone_input = get_user_input("Enter your GCP zone (e.g., europe-west1-b)", validator=validate_non_empty)
        self.zone = zone_input
        self.region = '-'.join(zone_input.split('-')[:-1])  # extract region from zone

        # 2. Create role with timestamp to avoid collision
        timestamp = int(time.time())
        self.role_name = f"hopsworksai.instances.{timestamp}"  # Unique role name
        print_colored(f"Creating role '{self.role_name}'...", "cyan")

        role_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        self.temp_files.append(role_file.name)

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
                    "artifactregistry.repositories.list",
                    "artifactregistry.tags.list",
                    "artifactregistry.tags.create",
                    "artifactregistry.tags.delete",
                    "artifactregistry.versions.delete"
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
        except Exception as e:
            print_colored(f"Error creating role: {e}", "red")
            sys.exit(1)

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

        # 5. Get cluster configuration
        self.cluster_name = get_user_input("Enter your GKE cluster name", default="hopsworks-cluster", validator=validate_cluster_name)
        node_count = get_user_input("Enter number of nodes", default="5")
        machine_type = get_user_input("Enter machine type", default="n2-standard-8")

        # Display summary and confirm
        config_summary = {
            "Cloud Provider": "GCP",
            "Project ID": self.project_id,
            "Zone": self.zone,
            "Region": self.region,
            "Cluster Name": self.cluster_name,
            "Machine Type": machine_type,
            "Node Count": node_count,
            "Namespace": self.namespace
        }

        if not display_config_summary(config_summary):
            print_colored("Installation cancelled by user.", "yellow")
            sys.exit(0)

        # 6. Create the cluster
        print_colored("\nCreating GKE cluster (this will take 10-15 minutes)...", "blue")
        cluster_cmd = (f"gcloud container clusters create {self.cluster_name} "
                       f"--zone={self.zone} "
                       f"--machine-type={machine_type} "
                       f"--num-nodes={node_count} "
                       f"--enable-ip-alias "
                       f"--workload-pool={self.project_id}.svc.id.goog "
                       f"--service-account={self.sa_email}")

        if not run_command(cluster_cmd)[0]:
            print_colored("Failed to create GKE cluster.", "red")
            print_colored("Check gcloud output above for details. Common issues:", "yellow")
            print("  - Insufficient project quotas")
            print("  - Machine type not available in zone")
            print("  - Billing not enabled on project")
            sys.exit(1)
        else:
            print_colored(f"GKE cluster '{self.cluster_name}' created.", "green")

        # 7. Configure kubectl
        print_colored("Configuring kubectl...", "cyan")
        run_command(f"gcloud container clusters get-credentials {self.cluster_name} "
                    f"--zone={self.zone} "
                    f"--project={self.project_id}")

        # 8. Store registry name for later use in setup_gke_registry
        self._gke_registry_name = f"hopsworks-{self.cluster_name}-{timestamp}"

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
            f"iam.gke.io/gcp-service-account={self.sa_email} --overwrite"
        )

        # 2. Setup Docker config for GCP Artifact Registry
        docker_config = {
            "credHelpers": {
                f"{self.region}-docker.pkg.dev": "gcloud"
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(docker_config, f)
            config_file = f.name
        self.temp_files.append(config_file)

        run_command(f"kubectl create configmap docker-config -n {self.namespace} "
                   f"--from-file=config.json={config_file} "
                   f"--dry-run=client -o yaml | kubectl apply -f -")

        return True

    def setup_aks_prerequisites(self):
        """Setup AKS prerequisites and cluster from scratch"""
        print_colored("\nSetting up AKS prerequisites...", "blue")

        # Verify Azure CLI auth
        print_colored("Verifying Azure CLI authentication...", "cyan")
        if not run_command("az account show", verbose=False)[0]:
            print_colored("Azure CLI not authenticated.", "red")
            print_colored("Please run 'az login' and try again.", "yellow")
            sys.exit(1)

        # Get resource group - create if doesn't exist
        self.resource_group = get_user_input("Enter your Azure resource group name", validator=validate_non_empty)
        location = get_user_input("Enter Azure region (e.g., eastus)", default="eastus")
        
        # Check if resource group exists, create if it doesn't
        if not run_command(f"az group show --name {self.resource_group}", verbose=False)[0]:
            print_colored(f"Creating resource group {self.resource_group}...", "cyan")
            if not run_command(f"az group create --name {self.resource_group} --location {location}")[0]:
                print_colored("Failed to create resource group.", "red")
                sys.exit(1)

        # Get cluster details
        self.cluster_name = get_user_input("Enter your AKS cluster name", validator=validate_cluster_name)
        node_count = get_user_input("Enter number of nodes", default="5")
        machine_type = get_user_input("Enter machine type", default="Standard_D8_v4")

        # Display summary and confirm
        config_summary = {
            "Cloud Provider": "Azure",
            "Resource Group": self.resource_group,
            "Location": location,
            "Cluster Name": self.cluster_name,
            "Machine Type": machine_type,
            "Node Count": node_count,
            "Namespace": self.namespace
        }

        if not display_config_summary(config_summary):
            print_colored("Installation cancelled by user.", "yellow")
            sys.exit(0)

        # Create AKS cluster with minimal config but all we need
        print_colored("\nCreating AKS cluster (this will take 5-10 minutes)...", "cyan")
        cluster_cmd = (
            f"az aks create "
            f"--resource-group {self.resource_group} "
            f"--name {self.cluster_name} "
            f"--node-count {node_count} "
            f"--node-vm-size {machine_type} "
            f"--location {location} "
            f"--network-plugin azure "
            f"--generate-ssh-keys "
            f"--load-balancer-sku standard "  
            f"--enable-managed-identity " 
            f"--network-policy azure " 
            f"--no-wait" 
        )
        
        if not run_command(cluster_cmd)[0]:
            print_colored("Failed to start AKS cluster creation.", "red")
            sys.exit(1)

        # Wait for cluster to be ready with timeout
        print_colored("\nWaiting for cluster to be ready...", "cyan")
        time.sleep(30)  # Initial delay after --no-wait to let Azure start provisioning

        max_wait_time = 1800  # 30 minutes timeout
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_time:
                print_colored(f"Timeout waiting for AKS cluster after {max_wait_time // 60} minutes.", "red")
                print_colored("Check Azure portal for cluster status.", "yellow")
                sys.exit(1)

            success, output, _ = run_command(
                f"az aks show --resource-group {self.resource_group} --name {self.cluster_name} --query provisioningState -o tsv",
                verbose=False
            )
            if success and "Succeeded" in output:
                break
            if success and "Failed" in output:
                print_colored("AKS cluster creation failed.", "red")
                sys.exit(1)
            print_colored(f"Still creating cluster... ({int(elapsed)}s elapsed)", "yellow")
            time.sleep(30)

        # Get credentials
        print_colored("\nGetting kubectl credentials...", "cyan")
        cmd = f"az aks get-credentials --resource-group {self.resource_group} --name {self.cluster_name} --overwrite-existing"
        if not run_command(cmd)[0]:
            print_colored("Failed to get AKS credentials.", "red")
            sys.exit(1)

        # Create namespace and setup basic RBAC
        print_colored(f"\nCreating namespace {self.namespace} and setting up RBAC...", "cyan")
        run_command(f"kubectl create namespace {self.namespace}")
        
        # Create a more permissive service account for Hopsworks
        sa_yaml = f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: hopsworks-sa
  namespace: {self.namespace}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: hopsworks-admin
  namespace: {self.namespace}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: admin
subjects:
- kind: ServiceAccount
  name: hopsworks-sa
  namespace: {self.namespace}"""
        sa_file = 'sa.yaml'
        with open(sa_file, 'w') as f:
            f.write(sa_yaml)
        self.temp_files.append(sa_file)

        run_command(f"kubectl apply -f {sa_file}")

        print_colored("\nAKS prerequisites setup completed successfully!", "green")
        return True
    
    def handle_azure_registry(self):
        """Setup Docker registry auth for Azure with proper error handling and verification"""
        print_colored("\nSetting up Docker registry credentials...", "blue")

        # Get Docker registry credentials with validation
        docker_user = get_user_input("Enter your Hopsworks Docker registry username", validator=validate_non_empty)
        docker_pass = get_user_input("Enter your Hopsworks Docker registry password", validator=validate_non_empty)

        # Define our secrets configuration
        registry_secrets = [
            {
                "name": "regcred",  # Primary secret referenced in Helm values
                "server": "docker.hops.works",
                "required": True  # This one must succeed
            },
            {
                "name": "hopsworks-registry-secret",  # Backup secret for additional components
                "server": "docker.hops.works",
                "required": False  # This one can fail if it exists
            }
        ]
        
        # Track if we've successfully created the required secrets
        required_secrets_created = False
        
        for secret_config in registry_secrets:
            print_colored(f"\nCreating secret {secret_config['name']}...", "cyan")
            
            # First try to delete any existing secret
            cleanup_cmd = f"kubectl delete secret {secret_config['name']} -n {self.namespace} --ignore-not-found=true"
            run_command(cleanup_cmd, verbose=False)
            
            # Create the new secret
            create_cmd = (
                f"kubectl create secret docker-registry {secret_config['name']} "
                f"--namespace={self.namespace} "
                f"--docker-server={secret_config['server']} "
                f"--docker-username={docker_user} "
                f"--docker-password={docker_pass} "
                "--docker-email=noreply@hopsworks.ai"
            )
            
            success, output, error = run_command(create_cmd)
            
            if success:
                print_colored(f"Successfully created secret {secret_config['name']}", "green")
                if secret_config['required']:
                    required_secrets_created = True
            else:
                error_msg = f"Failed to create secret {secret_config['name']}"
                if "already exists" in error:
                    print_colored(f"{error_msg} (already exists)", "yellow")
                    if secret_config['required']:
                        required_secrets_created = True
                else:
                    print_colored(f"{error_msg}: {error}", "red")
                    if secret_config['required'] and not required_secrets_created:
                        print_colored("Failed to create required registry secret. Cannot proceed.", "red")
                        sys.exit(1)

        # Verify the secrets were created
        print_colored("\nVerifying registry secrets...", "cyan")
        verify_cmd = f"kubectl get secrets -n {self.namespace} | grep -E 'regcred|hopsworks-registry-secret'"
        success, output, _ = run_command(verify_cmd, verbose=False)
        
        if success and 'regcred' in output:
            print_colored("\nRegistry secrets setup completed successfully.", "green")
            # Store this for potential use in other methods
            self.registry_secrets_created = True
            return True
        else:
            print_colored("Warning: Registry secrets verification failed.", "yellow")
            print_colored("This might cause issues with pulling images.", "yellow")
            # Don't exit here - let the installation continue and potentially fail later
            self.registry_secrets_created = False
            return False
        
    def setup_and_verify_kubeconfig(self):
        while True:
            self.kubeconfig_path, self.cluster_name, self.region = self.setup_kubeconfig()
            if self.kubeconfig_path:
                # Set the provided config as current context
                run_command(f"kubectl config use-context $(kubectl config current-context --kubeconfig={self.kubeconfig_path})")
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
            cluster_name = get_user_input("Enter your EKS cluster name", validator=validate_cluster_name)
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
                cluster_name = get_user_input("Enter your GKE cluster name", validator=validate_cluster_name)
                self.project_id = get_user_input("Enter your GCP project ID", validator=validate_non_empty)
                zone_input = get_user_input("Enter your GCP zone (e.g., europe-west1-b)", validator=validate_non_empty)
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
            self.resource_group = get_user_input("Enter your Azure resource group name", validator=validate_non_empty)
            cluster_name = get_user_input("Enter your AKS cluster name", validator=validate_cluster_name)
            cmd = f"az aks get-credentials --resource-group {self.resource_group} --name {cluster_name} --overwrite-existing"
            if not run_command(cmd)[0]:
                print_colored("Failed to get AKS credentials. Check your Azure CLI configuration and permissions.", "red")
                return None, None, None
            kubeconfig_path = os.path.expanduser("~/.kube/config")

        else:
            # Other environments (OVH, etc.)
            print_colored(f"\nFor {self.environment}, you need an existing Kubernetes cluster.", "blue")
            print_colored("Make sure your cluster meets these requirements:", "cyan")
            print("  - Kubernetes 1.24+")
            print("  - LoadBalancer support")
            print("  - Storage class configured")
            print("  - At least 32GB RAM and 8 vCPUs total across nodes\n")

            kubeconfig_path = get_user_input("Enter the path to your kubeconfig file", validator=validate_non_empty)
            kubeconfig_path = os.path.expanduser(kubeconfig_path)
            if not os.path.exists(kubeconfig_path):
                print_colored(f"The file {kubeconfig_path} does not exist.", "red")
                print_colored("Check the path and try again.", "yellow")
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
        parser.add_argument('--namespace', default='hopsworks', help='Namespace for Hopsworks installation')
        parser.add_argument('--devel', action='store_true', help='Enable development mode (use --devel flag with helm)')
        parser.add_argument('--version', type=str, help='Specify Hopsworks version to install (e.g., 4.0.0)')
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
            region = get_user_input("Enter your AWS region (e.g., us-east-2)", validator=validate_non_empty)
            os.environ['AWS_REGION'] = region
        else:
            print_colored(f"Using AWS region from environment: {region}", "cyan")
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
        elif self.environment == "Azure":
            print_colored("Setting up Azure registry credentials...", "blue")
            self.handle_azure_registry()

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
                # Use registry name from setup_gke_prerequisites if available, else generate new
                registry_name = getattr(self, '_gke_registry_name', None)
                if not registry_name:
                    timestamp = int(time.time())
                    registry_name = f"hopsworks-{self.cluster_name}-{timestamp}"

                # Create Artifact Registry repository
                print_colored(f"Creating Artifact Registry repository '{registry_name}'...", "cyan")
                success, _, error = run_command(f"gcloud artifacts repositories create {registry_name} "
                            f"--repository-format=docker "
                            f"--location={self.region} "
                            f"--project={self.project_id}")

                if not success and "already exists" not in error:
                    print_colored(f"Failed to create Artifact Registry: {error}", "red")
                    return False

                print_colored(f"Artifact Registry repository '{registry_name}' ready.", "green")

                self.managed_registry_info = {
                    "domain": f"{self.region}-docker.pkg.dev",
                    "namespace": f"{self.project_id}/{registry_name}"
                }
                return True

            except Exception as e:
                print_colored(f"Error during GCP Artifact Registry setup: {str(e)}", "red")
                return False

    def install_hopsworks(self):
        """Installs Hopsworks consistently across all cloud providers"""
        print_colored("\nInstalling Hopsworks...", "blue")

        # Setup helm repos - dev repo requires authentication
        nexus_user = os.environ.get("NEXUS_USER")
        nexus_pass = os.environ.get("NEXUS_PASSWORD")
        if not nexus_user or not nexus_pass:
            print_colored("NEXUS_USER and NEXUS_PASSWORD environment variables required for dev repo.", "red")
            print_colored("Export them before running: export NEXUS_USER=xxx NEXUS_PASSWORD=xxx", "yellow")
            return False

        repo_cmd = f'helm repo add hopsworks-dev https://nexus.hops.works/repository/hopsworks-helm-dev --username {nexus_user} --password "{nexus_pass}" --force-update'
        if not run_command(repo_cmd)[0]:
            print_colored("Failed to add Hopsworks dev Helm repo.", "red")
            return False

        if not run_command("helm repo update")[0]:
            print_colored("Failed to update Helm repos.", "red")
            return False

        # Show available versions if user hasn't specified one
        if not self.args.version:
            print_colored("\nFetching available Hopsworks versions...", "cyan")
            search_cmd = "helm search repo hopsworks-dev/hopsworks -l --devel"

            success, output, _ = run_command(search_cmd, verbose=False)
            if success and output.strip():
                print_colored("\nAvailable dev versions:", "blue")
                lines = output.strip().split('\n')
                for line in lines[:11]:  # Header + 10 versions
                    print(line)
                if len(lines) > 11:
                    print(f"... and {len(lines) - 11} more versions")

                print_colored("\nYou can specify a version with --version flag, or press Enter to use the latest.", "yellow")
                use_specific = get_user_input("Do you want to specify a version now? (yes/no)", options=["yes", "no"], default="no")

                if use_specific.lower() == "yes":
                    version = get_user_input("Enter version number", validator=validate_non_empty)
                    self.args.version = version
                    print_colored(f"Will install version: {version}", "green")
            else:
                print_colored("Could not fetch versions, continuing with latest...", "yellow")

        # Clean up and get fresh chart - this is good practice, keep it
        if os.path.exists('hopsworks'):
            shutil.rmtree('hopsworks', ignore_errors=True)

        # Build helm pull command
        pull_cmd = "helm pull hopsworks-dev/hopsworks --untar --devel"
        if self.args.version:
            pull_cmd += f" --version {self.args.version}"

        if not run_command(pull_cmd)[0]:
            print_colored("Failed to pull Hopsworks chart.", "red")
            return False
        
        # Prepare namespace - good to keep
        if not run_command(f"kubectl create namespace {self.namespace} --dry-run=client -o yaml | kubectl apply -f -")[0]:
            print_colored("Failed to create namespace", "red")
            return False
        time.sleep(5)  # Keep the settle time

        # Construct helm command using our new configuration method
        helm_command = self.construct_helm_command()

        # Execute helm install with progress monitoring
        print_colored("Starting Hopsworks installation...", "cyan")
        stop_event = threading.Event()
        status_thread = threading.Thread(target=periodic_status_update, args=(stop_event, self.namespace))
        status_thread.start()

        try:
            success, output, error = run_command(helm_command)
            if not success:
                # Only ignore known non-fatal errors
                if not any(err in error for err in KNOWN_NONFATAL_ERRORS):
                    print_colored("\nHopsworks installation failed.", "red")
                    print_colored("Error: " + error, "red")
                    return False
                print_colored(f"\nIgnoring expected configuration message: {error}", "yellow")
                
            # Wait for actual deployment readiness regardless of helm command result
            return wait_for_deployment(self.namespace)
        finally:
            stop_event.set()
            status_thread.join()
                                        
    def get_load_balancer_address(self):
        """Get LoadBalancer address with more robust detection"""
        # Try both hostname and IP - some providers might give either
        commands = [
            "kubectl get svc -n {ns} hopsworks-release -o jsonpath='{{.status.loadBalancer.ingress[0].hostname}}'",
            "kubectl get svc -n {ns} hopsworks-release -o jsonpath='{{.status.loadBalancer.ingress[0].ip}}'"
        ]
        
        for cmd in commands:
            formatted_cmd = cmd.format(ns=self.namespace)
            success, output, _ = run_command(formatted_cmd, verbose=False)
            if success and output.strip():
                return output.strip()
                
        # Fallback - check all LoadBalancer services
        print_colored("Retrying LoadBalancer address detection...", "yellow")
        cmd = f"kubectl get svc -n {self.namespace} -o wide | grep LoadBalancer | grep hopsworks-release"
        success, output, _ = run_command(cmd, verbose=False)
        
        if success and output.strip():
            parts = output.split()
            if len(parts) >= 6:  # Standard kubectl output format
                external_ip = parts[5]
                if external_ip != '<pending>' and external_ip != '<none>':
                    return external_ip
        
        # Last resort - get ALL LoadBalancer services
        cmd = f"kubectl get svc -n {self.namespace} --field-selector type=LoadBalancer -o json"
        success, output, _ = run_command(cmd, verbose=False)
        if success:
            import json
            try:
                services = json.loads(output)
                for svc in services.get('items', []):
                    ingress = svc.get('status', {}).get('loadBalancer', {}).get('ingress', [])
                    if ingress:
                        return ingress[0].get('hostname') or ingress[0].get('ip')
            except json.JSONDecodeError:
                pass
                
        return None

    def finalize_installation(self):
        """Simple installation finalization focused on LoadBalancer"""
        print_colored("\nFinalizing installation...", "blue")
        
        # Give the LoadBalancer some time to get an address
        max_retries = 12  # 2 minutes total
        address = None
        
        for i in range(max_retries):
            address = self.get_load_balancer_address()
            if address:
                break
            if i < max_retries - 1:  # Don't sleep on last iteration
                print_colored("Waiting for LoadBalancer address...", "yellow")
                time.sleep(10)
        
        if not address:
            print_colored("Failed to obtain LoadBalancer address. Manual configuration may be needed.", "red")
            print_colored("Run 'kubectl get svc -n {} hopsworks-release' to check status".format(self.namespace), "yellow")
            return

        print_colored("\nHopsworks is accessible at:", "green")
        print_colored(f"UI:    https://{address}:28181", "cyan")
        print_colored(f"API:   https://{address}:8182", "cyan")
        print_colored("Login: admin@hopsworks.ai / admin", "cyan")

        if health_check(self.namespace):
            print_colored("\nHealth check passed!", "green")
        else:
            print_colored("\nSome pods are not ready yet. Give them a few more minutes.", "yellow")

# Installation utillities 
def periodic_status_update(stop_event, namespace):
    while not stop_event.is_set():
        cmd = f"kubectl get pods -n {namespace} --no-headers"
        success, output, error = run_command(cmd, verbose=False)
        if success and output.strip():
            pod_count = len(output.strip().split('\n'))
            print_colored(f"\rCurrent status: {pod_count} pods created", "cyan", end='')
        else:
            if "No resources found" in error:
                print_colored("\rWaiting for pods to be created... Do not panic. This will take a moment", "yellow", end='')
            else:
                print_colored(f"\rError checking pod status: {error.strip()}", "red", end='')
        sys.stdout.flush()  # Ensure the output is displayed immediately
        time.sleep(10)  # Update every 10 seconds
    print()  # Print a newline when done to move to the next line

def wait_for_deployment(namespace, timeout=2700):
    """
    Enhanced deployment monitor that exits immediately when ready,
    or lets you override with a keypress.
    """
    print_colored("\nMonitoring core services...", "blue")
    start_time = time.time()
    
    import threading
    import sys
    if sys.platform != 'win32':
        import termios
        import tty

    override_flag = threading.Event()
    
    def check_status():
        """Check if deployment is ready"""
        # Check jobs
        cmd = f"kubectl get jobs -n {namespace} -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[*].type"
        success, output, _ = run_command(cmd, verbose=False)
        
        if not success or not output.strip():
            return False, 0, 0
            
        jobs = [line.split() for line in output.strip().split('\n')[1:]]
        incomplete_jobs = [job[0] for job in jobs if "Complete" not in job[-1] and "SuccessCriteriaMet" not in job[-1]]
        
        # Check core service(s)
        services_ready = True
        for svc in ["hopsworks-instance"]:
            cmd = f"kubectl get pods -n {namespace} -l app={svc} -o jsonpath='{{.items[0].status.phase}}'"
            success, status, _ = run_command(cmd, verbose=False)
            if not success or status.strip() != "Running":
                services_ready = False
                break
                
        total_jobs = len(jobs)
        complete_jobs = total_jobs - len(incomplete_jobs)
        
        return services_ready and not incomplete_jobs, complete_jobs, total_jobs

    def key_listener():
        """Listen for keypress to override"""
        if sys.platform == 'win32':
            import msvcrt
            while not override_flag.is_set():
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b'1':
                        override_flag.set()
                threading.Event().wait(0.1)
        else:
            old_settings = termios.tcgetattr(sys.stdin)
            try:
                tty.setcbreak(sys.stdin.fileno())
                while not override_flag.is_set():
                    if sys.stdin.read(1) == '1':
                        override_flag.set()
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    # Start key listener in background
    listener = threading.Thread(target=key_listener, daemon=True)
    listener.start()
    
    print_colored("Press '1' at any time to proceed anyway", "yellow")
    
    try:
        while True:
            # Check for override
            if override_flag.is_set():
                print("\n")
                print_colored("Override accepted - proceeding anyway!", "yellow")
                return True
                
            # Check if we've timed out
            if (time.time() - start_time) >= timeout:
                print_colored(f"\nTimeout after {timeout/60:.1f} minutes.", "yellow")
                print_colored("Press '1' to proceed anyway, or Ctrl+C to abort", "cyan")
                # Wait for override or interrupt
                while not override_flag.is_set():
                    time.sleep(1)
                print_colored("\nProceeding despite timeout!", "yellow")
                return True
                
            # Regular status check
            is_ready, complete_jobs, total_jobs = check_status()
            
            if is_ready:
                print("\n")
                print_colored("All jobs complete and core services are ready!", "green")
                return True
            
            # Status update
            elapsed = int(time.time() - start_time)
            progress = (complete_jobs / total_jobs * 100) if total_jobs > 0 else 0
            print_colored(f"\rProgress: {progress:.1f}% ({complete_jobs}/{total_jobs} jobs) | {elapsed}s elapsed | Press '1' to proceed", "cyan", end='')
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n")
        print_colored("Installation interrupted. Check status manually with 'kubectl get pods,jobs -n hopsworks'", "yellow")
        return False
    finally:
        override_flag.set()  # Stop the key listener

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
