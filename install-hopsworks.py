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
import uuid
import shutil
import argparse
from datetime import datetime
import urllib.request
import urllib.error
import ssl
import threading
import boto3
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
KNOWN_NONFATAL_ERRORS = [
    "invalid ingress class: IngressClass.networking.k8s.io",
]

""" All the helm stuff here ⬇ """
HELM_BASE_CONFIG = {
    "hopsworks.service.worker.external.https.type": "LoadBalancer",
    "global._hopsworks.externalLoadBalancers.enabled": "true",
    "global._hopsworks.imagePullPolicy": "Always",
    "hopsworks.replicaCount.worker": "1",
    "rondb.clusterSize.activeDataReplicas": "1",
    "hopsfs.datanode.count": "2"
}

CLOUD_SPECIFIC_VALUES = {
    "AWS": {
        "global._hopsworks.cloudProvider": "AWS",
        "global._hopsworks.ingressController.type": "none",
        "global._hopsworks.managedDockerRegistery.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.secretName": "awsregcred",
        "global._hopsworks.storageClassName": "ebs-gp3",
        "hopsworks.variables.docker_operations_managed_docker_secrets": "awsregcred",
        "hopsworks.variables.docker_operations_image_pull_secrets": "awsregcred",
        "hopsworks.dockerRegistry.preset.secrets[0]": "awsregcred",
        "externalLoadBalancers": {
            "enabled": True,
            "class": None,
            "annotations": {
                "service.beta.kubernetes.io/aws-load-balancer-scheme": "internet-facing"
            }
        }
    },
    "GCP": {
        "global._hopsworks.cloudProvider": "GCP",
        "global._hopsworks.managedDockerRegistery.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.configMap": "docker-config",
        "global._hopsworks.managedDockerRegistery.credHelper.secretName": "gcrregcred",
        "hopsworks.variables.docker_operations_managed_docker_secrets": "gcrregcred",
        "hopsworks.variables.docker_operations_image_pull_secrets": "gcrregcred",
        "hopsworks.dockerRegistry.preset.secrets[0]": "gcrregcred",
        "serviceAccount.name": "hopsworks-sa"
    },
    "Azure": {
        "global._hopsworks.cloudProvider": "AZURE",
        "global._hopsworks.managedDockerRegistery.enabled": "true",
        "global._hopsworks.ingressController.type": "none",
        "global._hopsworks.imagePullSecretName": "regcred",
        "global._hopsworks.minio.enabled": "true", 
        "serviceAccount.name": "hopsworks-sa",
        "serviceAccount.create": "false",
        "hopsworks.service.worker.external.https.type": "LoadBalancer",  
        "hopsworks.service.worker.external.https.annotations.service\\.beta\\.kubernetes\\.io/azure-load-balancer-internal": "false"
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

def get_user_input(prompt, options=None):
    while True:
        response = input(prompt + " ").strip()
        if options is None or response.lower() in [option.lower() for option in options]:
            return response
        print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "yellow")

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
            self.installation_id = None
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
            
            # Azure specific (if we need it later)
            self.resource_group = None

    def run(self):
        print_colored(HOPSWORKS_LOGO, "white")
        self.parse_arguments()
        self.check_required_tools()
        self.get_deployment_environment()

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
                
    def construct_helm_command(self):
            """Constructs the helm command with proper configuration"""
            # Base helm command
            helm_command = [
                "helm upgrade --install hopsworks-release hopsworks/hopsworks",
                f"--namespace={self.namespace}",
                "--create-namespace",
                "--values hopsworks/values.yaml"
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
                        "serviceAccount.annotations.iam\\.gke\\.io/gcp-service-account": self.sa_email
                    })
                    
                elif self.environment == "Azure" and hasattr(self, 'registry_secrets_created'):
                    # Azure uses regcred secret which is already configured in base cloud config
                    # We only need to verify the secret exists, which we track with registry_secrets_created
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

            # Add timeout and devel flag
            helm_command.extend([
                "--timeout 60m",
                "--devel"
            ])

            return " ".join(helm_command)
    def setup_aws_prerequisites(self):
        """Setup AWS prerequisites including metrics server"""
        print_colored("\nSetting up AWS prerequisites...", "blue")
        
        # 1. Basic AWS setup and verification
        self.aws_profile = input("Enter your AWS profile name (default: default): ").strip() or "default"
        os.environ['AWS_PROFILE'] = self.aws_profile
        
        # Verify AWS credentials
        cmd = f"aws sts get-caller-identity --profile {self.aws_profile}"
        if not run_command(cmd, verbose=False)[0]:
            print_colored("AWS CLI not properly configured. Please run 'aws configure' first.", "red")
            sys.exit(1)
        
        # Get basic info
        self.region = self.get_aws_region()
        self.cluster_name = input("Enter your EKS cluster name: ").strip()
        
        # Get AWS account ID
        cmd = f"aws sts get-caller-identity --query Account --output text --profile {self.aws_profile}"
        success, account_id, _ = run_command(cmd)
        if not success:
            print_colored("Failed to get AWS account ID.", "red")
            sys.exit(1)
        self.aws_account_id = account_id.strip()

        # 2. Create S3 bucket
        bucket_name = input("Enter S3 bucket name for Hopsworks data: ").strip()
        cmd = f"aws s3 mb s3://{bucket_name} --region {self.region} --profile {self.aws_profile}"
        if not run_command(cmd)[0]:
            print_colored("Failed to create S3 bucket", "red")
            sys.exit(1)
        
        # Enable versioning on the bucket
        cmd = f"aws s3api put-bucket-versioning --bucket {bucket_name} --versioning-configuration Status=Enabled --profile {self.aws_profile}"
        if not run_command(cmd)[0]:
            print_colored("Failed to enable bucket versioning", "red")
            sys.exit(1)

        # 3. Create ECR repository
        print_colored("\nCreating ECR repository...", "cyan")
        repo_name = f"{self.cluster_name}/hopsworks-base"
        cmd = f"aws ecr create-repository --repository-name {repo_name} --profile {self.aws_profile} --region {self.region}"
        if not run_command(cmd)[0]:
            print_colored("Failed to create ECR repository", "red")
            sys.exit(1)

        # 4. Create IAM policy
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
        with open(f'policy-{timestamp}.json', 'w') as f:
            json.dump(policy, f, indent=2)

        self.policy_name = f"hopsworks-policy-{timestamp}"
        cmd = f"aws iam create-policy --policy-name {self.policy_name} --policy-document file://policy-{timestamp}.json --profile {self.aws_profile}"
        if not run_command(cmd)[0]:
            print_colored("Failed to create IAM policy", "red")
            sys.exit(1)

        print_colored("Waiting for policy to propagate...", "yellow")
        time.sleep(10)

        # 5. Create EKS cluster configuration
        print_colored("\nCreating EKS cluster configuration...", "cyan")
        instance_type = input("Enter instance type (default: m6i.2xlarge): ").strip() or "m6i.2xlarge"
        node_count = input("Enter number of nodes (default: 4): ").strip() or "4"

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

        with open(f'eksctl-{timestamp}.yaml', 'w') as f:
            yaml.dump(cluster_config, f)

        # 6. Create EKS cluster
        print_colored("\nCreating EKS cluster (this will take 15-20 minutes)...", "cyan")
        cmd = f"eksctl create cluster -f eksctl-{timestamp}.yaml --profile {self.aws_profile}"
        if not run_command(cmd)[0]:
            print_colored("Failed to create EKS cluster", "red")
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
        
        with open(f'storage-class-{timestamp}.yaml', 'w') as f:
            yaml.dump(storage_class, f)
        
        if not run_command(f"kubectl apply -f storage-class-{timestamp}.yaml")[0]:
            print_colored("Failed to create GP3 storage class", "red")
            sys.exit(1)

        # 8. Set up AWS Load Balancer Controller
        print_colored("\nSetting up AWS Load Balancer Controller...", "cyan")
        
        # Download and create ALB policy
        cmd = "curl -o iam_policy_alb.json https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.2/docs/install/iam_policy.json"
        if not run_command(cmd)[0]:
            print_colored("Failed to download ALB policy", "red")
            sys.exit(1)

        alb_policy_name = f"AWSLoadBalancerControllerIAMPolicy-{self.cluster_name}-{timestamp}"
        cmd = f"aws iam create-policy --policy-name {alb_policy_name} --policy-document file://iam_policy_alb.json --profile {self.aws_profile}"
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

        # 11. Cleanup temporary files
        for file in [f'policy-{timestamp}.json', f'eksctl-{timestamp}.yaml', f'storage-class-{timestamp}.yaml', 'iam_policy_alb.json']:
            if os.path.exists(file):
                os.remove(file)

        print_colored("\nAWS prerequisites setup completed successfully!", "green")
        return True

    def setup_gke_prerequisites(self):
        """Setup everything needed before cluster creation"""
        print_colored("\nSetting up GKE prerequisites...", "blue")

        # 1. Get essential info first
        self.project_id = input("Enter your GCP project ID: ").strip()
        zone_input = input("Enter your GCP zone (e.g., europe-west1-b). Note: If you select a region like europe-west1, deployments will include all sub-zones (a, b, c), potentially multiplying node counts. Proceed with caution: ").strip()
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
        node_count = input("Enter number of nodes (default: 5): ").strip() or "5"
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
        registry_name = f"hopsworks-{self.cluster_name}-{timestamp}"
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

    def setup_aks_prerequisites(self):
        """Setup AKS prerequisites and cluster from scratch"""
        print_colored("\nSetting up AKS prerequisites...", "blue")
        
        # Verify Azure CLI auth
        if not run_command("az account show", verbose=False)[0]:
            print_colored("Please run 'az login' first.", "red")
            sys.exit(1)

        # Get resource group - create if doesn't exist
        self.resource_group = input("Enter your Azure resource group name: ").strip()
        location = input("Enter Azure region (eg. eastus): ").strip() or "eastus"
        
        # Check if resource group exists, create if it doesn't
        if not run_command(f"az group show --name {self.resource_group}", verbose=False)[0]:
            print_colored(f"Creating resource group {self.resource_group}...", "cyan")
            if not run_command(f"az group create --name {self.resource_group} --location {location}")[0]:
                print_colored("Failed to create resource group.", "red")
                sys.exit(1)

        # Get cluster details
        self.cluster_name = input("Enter your AKS cluster name: ").strip()
        node_count = input("Enter number of nodes (default: 5): ").strip() or "5"
        machine_type = input("Enter machine type (default: Standard_D8_v4): ").strip() or "Standard_D8_v4"

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

        # Wait for cluster to be ready
        print_colored("\nWaiting for cluster to be ready...", "cyan")
        while True:
            success, output, _ = run_command(
                f"az aks show --resource-group {self.resource_group} --name {self.cluster_name} --query provisioningState -o tsv",
                verbose=False
            )
            if success and "Succeeded" in output:
                break
            print_colored("Still creating cluster...", "yellow")
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
        with open('sa.yaml', 'w') as f:
            f.write(sa_yaml)
        
        run_command("kubectl apply -f sa.yaml")

        print_colored("\nAKS prerequisites setup completed successfully!", "green")
        return True
    
    def handle_azure_registry(self):
        """Setup Docker registry auth for Azure with proper error handling and verification"""
        print_colored("\nSetting up Docker registry credentials...", "blue")
        
        # Get Docker registry credentials with basic validation
        while True:
            docker_user = input("Enter your Hopsworks Docker registry username: ").strip()
            if docker_user:
                break
            print_colored("Username cannot be empty.", "yellow")
        
        while True:
            docker_pass = input("Enter your Hopsworks Docker registry password: ").strip()
            if docker_pass:
                break
            print_colored("Password cannot be empty.", "yellow")

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
                timestamp = int(time.time())
                registry_name = f"hopsworks-{self.cluster_name}-{timestamp}"
                
                # Create Artifact Registry repository
                run_command(f"gcloud artifacts repositories create {registry_name} "
                            f"--repository-format=docker "
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
        """Installs Hopsworks consistently across all cloud providers"""
        print_colored("\nInstalling Hopsworks...", "blue")

        # Setup helm repos - this part works, keep it
        if not run_command("helm repo add hopsworks https://nexus.hops.works/repository/hopsworks-helm --force-update")[0]:
            print_colored("Failed to add Hopsworks Helm repo.", "red")
            return False

        if not run_command("helm repo update")[0]:
            print_colored("Failed to update Helm repos.", "red")
            return False

        # Clean up and get fresh chart - this is good practice, keep it
        if os.path.exists('hopsworks'):
            shutil.rmtree('hopsworks', ignore_errors=True)

        if not run_command("helm pull hopsworks/hopsworks --untar --devel")[0]:
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
    
    while True:
        name = input("Your name: ").strip()
        if len(name) < 2:
            print_colored("Sorry, We need a real name, please.", "yellow")
            continue
            
        email = input("Your email address: ").strip()
        if not '@' in email or not '.' in email or len(email) < 5:
            print_colored("That doesn't look like an email address. Please try again", "yellow")
            continue
            
        company = input("Your company name (optional): ").strip()
            
        # If we get here, all inputs are valid
        break
        
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
