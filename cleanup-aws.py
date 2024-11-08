#!/usr/bin/env python3
import boto3
import botocore
import click
from typing import List, Dict, Any
import time
from datetime import datetime, timezone
import sys

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_colored(message: str, color: str, bold: bool = False) -> None:
    prefix = Colors.BOLD if bold else ""
    print(f"{prefix}{color}{message}{Colors.END}")

def confirm_action(message: str, default: bool = False) -> bool:
    """Ask user for confirmation with colored output."""
    default_str = "Y/n" if default else "y/N"
    response = input(f"{Colors.YELLOW}{message} [{default_str}]: {Colors.END}").lower().strip()
    if not response:
        return default
    return response.startswith('y')

class AWSResourceCleaner:
    def __init__(self, profile: str, region: str, cluster_name: str):
        self.session = boto3.Session(profile_name=profile, region_name=region)
        self.cluster_name = cluster_name
        self.region = region
        
        # Initialize AWS clients
        self.eks = self.session.client('eks')
        self.ec2 = self.session.client('ec2')
        self.elb = self.session.client('elb')
        self.elbv2 = self.session.client('elbv2')
        self.s3 = self.session.client('s3')
        self.cloudformation = self.session.client('cloudformation')
        self.iam = self.session.client('iam')

    def get_cluster_vpc(self) -> str:
        """Get VPC ID associated with the EKS cluster."""
        try:
            response = self.eks.describe_cluster(name=self.cluster_name)
            return response['cluster']['resourcesVpcConfig']['vpcId']
        except self.eks.exceptions.ResourceNotFoundException:
            print_colored(f"Cluster {self.cluster_name} not found!", Colors.RED)
            return None
        except Exception as e:
            print_colored(f"Error getting cluster VPC: {str(e)}", Colors.RED)
            return None

    def list_load_balancers(self) -> List[Dict[str, Any]]:
        """List all load balancers associated with the cluster."""
        load_balancers = []
        
        # Get cluster VPC
        vpc_id = self.get_cluster_vpc()
        if not vpc_id:
            return load_balancers

        # Check Classic ELBs
        try:
            elbs = self.elb.describe_load_balancers()['LoadBalancerDescriptions']
            for elb in elbs:
                if elb['VPCId'] == vpc_id:
                    # Get tags to verify it's ours
                    tags = self.elb.describe_tags(LoadBalancerNames=[elb['LoadBalancerName']])['TagDescriptions'][0]['Tags']
                    if any(tag['Key'] == 'kubernetes.io/cluster/' + self.cluster_name for tag in tags):
                        load_balancers.append({
                            'name': elb['LoadBalancerName'],
                            'type': 'classic',
                            'dns': elb['DNSName']
                        })
        except Exception as e:
            print_colored(f"Error listing classic ELBs: {str(e)}", Colors.RED)

        # Check ALBs/NLBs
        try:
            albs = self.elbv2.describe_load_balancers()['LoadBalancers']
            for alb in albs:
                if alb['VpcId'] == vpc_id:
                    # Get tags to verify it's ours
                    tags = self.elbv2.describe_tags(ResourceArns=[alb['LoadBalancerArn']])['TagDescriptions'][0]['Tags']
                    if any(tag['Key'] == 'kubernetes.io/cluster/' + self.cluster_name for tag in tags):
                        load_balancers.append({
                            'name': alb['LoadBalancerName'],
                            'type': 'application/network',
                            'arn': alb['LoadBalancerArn'],
                            'dns': alb['DNSName']
                        })
        except Exception as e:
            print_colored(f"Error listing ALBs/NLBs: {str(e)}", Colors.RED)

        return load_balancers

    def list_target_groups(self) -> List[Dict[str, Any]]:
        """List target groups associated with the cluster."""
        try:
            target_groups = []
            paginator = self.elbv2.get_paginator('describe_target_groups')
            
            for page in paginator.paginate():
                for tg in page['TargetGroups']:
                    tags = self.elbv2.describe_tags(ResourceArns=[tg['TargetGroupArn']])['TagDescriptions'][0]['Tags']
                    if any(tag['Key'] == 'kubernetes.io/cluster/' + self.cluster_name for tag in tags):
                        target_groups.append({
                            'name': tg['TargetGroupName'],
                            'arn': tg['TargetGroupArn']
                        })
            return target_groups
        except Exception as e:
            print_colored(f"Error listing target groups: {str(e)}", Colors.RED)
            return []

    def list_security_groups(self) -> List[Dict[str, Any]]:
        """List security groups associated with the cluster."""
        vpc_id = self.get_cluster_vpc()
        if not vpc_id:
            return []

        try:
            security_groups = []
            response = self.ec2.describe_security_groups(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'tag:kubernetes.io/cluster/' + self.cluster_name, 'Values': ['owned', 'shared']}
                ]
            )
            
            for sg in response['SecurityGroups']:
                security_groups.append({
                    'id': sg['GroupId'],
                    'name': sg['GroupName'],
                    'description': sg['Description']
                })
            return security_groups
        except Exception as e:
            print_colored(f"Error listing security groups: {str(e)}", Colors.RED)
            return []

    def list_s3_buckets(self) -> List[Dict[str, Any]]:
        """List S3 buckets that might be associated with Hopsworks."""
        try:
            buckets = []
            response = self.s3.list_buckets()
            
            for bucket in response['Buckets']:
                try:
                    tags = self.s3.get_bucket_tagging(Bucket=bucket['Name'])['TagSet']
                    if any(tag['Key'] == 'hopsworks-cluster' and tag['Value'] == self.cluster_name for tag in tags):
                        buckets.append({
                            'name': bucket['Name'],
                            'creation_date': bucket['CreationDate']
                        })
                except self.s3.exceptions.ClientError:
                    # Bucket might not have tags, skip it
                    continue
            return buckets
        except Exception as e:
            print_colored(f"Error listing S3 buckets: {str(e)}", Colors.RED)
            return []

    def cleanup_resources(self):
        """Main cleanup method with user confirmation for each resource type."""
        print_colored(f"\n🔍 Analyzing resources for cluster: {self.cluster_name}", Colors.BLUE, bold=True)
        
        # Load Balancers
        lbs = self.list_load_balancers()
        if lbs:
            print_colored("\nFound Load Balancers:", Colors.GREEN)
            for lb in lbs:
                print(f"- {lb['name']} ({lb['type']}) - {lb['dns']}")
            if confirm_action("Would you like to delete these load balancers?"):
                for lb in lbs:
                    try:
                        if lb['type'] == 'classic':
                            self.elb.delete_load_balancer(LoadBalancerName=lb['name'])
                        else:
                            self.elbv2.delete_load_balancer(LoadBalancerArn=lb['arn'])
                        print_colored(f"Deleted load balancer: {lb['name']}", Colors.GREEN)
                    except Exception as e:
                        print_colored(f"Error deleting {lb['name']}: {str(e)}", Colors.RED)

        # Target Groups
        target_groups = self.list_target_groups()
        if target_groups:
            print_colored("\nFound Target Groups:", Colors.GREEN)
            for tg in target_groups:
                print(f"- {tg['name']}")
            if confirm_action("Would you like to delete these target groups?"):
                for tg in target_groups:
                    try:
                        self.elbv2.delete_target_group(TargetGroupArn=tg['arn'])
                        print_colored(f"Deleted target group: {tg['name']}", Colors.GREEN)
                    except Exception as e:
                        print_colored(f"Error deleting target group {tg['name']}: {str(e)}", Colors.RED)

        # Security Groups
        sgs = self.list_security_groups()
        if sgs:
            print_colored("\nFound Security Groups:", Colors.GREEN)
            for sg in sgs:
                print(f"- {sg['name']} ({sg['id']}) - {sg['description']}")
            if confirm_action("Would you like to delete these security groups?"):
                for sg in sgs:
                    try:
                        self.ec2.delete_security_group(GroupId=sg['id'])
                        print_colored(f"Deleted security group: {sg['name']}", Colors.GREEN)
                    except Exception as e:
                        print_colored(f"Error deleting security group {sg['name']}: {str(e)}", Colors.RED)

        # S3 Buckets
        buckets = self.list_s3_buckets()
        if buckets:
            print_colored("\nFound S3 Buckets:", Colors.GREEN)
            for bucket in buckets:
                print(f"- {bucket['name']} (Created: {bucket['creation_date']})")
            if confirm_action("Would you like to delete these S3 buckets? THIS IS DESTRUCTIVE!", default=False):
                for bucket in buckets:
                    try:
                        # First empty the bucket
                        s3_resource = self.session.resource('s3')
                        bucket_obj = s3_resource.Bucket(bucket['name'])
                        bucket_obj.objects.all().delete()
                        # Then delete the bucket
                        self.s3.delete_bucket(Bucket=bucket['name'])
                        print_colored(f"Deleted bucket: {bucket['name']}", Colors.GREEN)
                    except Exception as e:
                        print_colored(f"Error deleting bucket {bucket['name']}: {str(e)}", Colors.RED)

        print_colored("\n🧹 Cleanup process completed!", Colors.GREEN, bold=True)

@click.command()
@click.option('--profile', default='default', help='AWS profile to use')
@click.option('--region', required=True, help='AWS region')
@click.option('--cluster-name', required=True, help='EKS cluster name')
def main(profile: str, region: str, cluster_name: str):
    """AWS Resource Cleanup Tool for Hopsworks"""
    print_colored("""
    🧹 AWS Hopsworks Cleanup Tool 🧹
    ===============================
    This tool will help you clean up AWS resources associated with your Hopsworks cluster.
    It will only delete resources that are tagged with your cluster name.
    """, Colors.BLUE, bold=True)

    if not confirm_action(
        "⚠️  This tool will delete resources. Do you want to continue?",
        default=False
    ):
        sys.exit(0)

    cleaner = AWSResourceCleaner(profile, region, cluster_name)
    cleaner.cleanup_resources()

if __name__ == '__main__':
    main()