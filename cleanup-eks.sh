#!/bin/bash

# chmod +x cleanup-eks.sh
# ./cleanup-eks.sh "your cluster name" "your region" "profile (optional)"

# Default values
DEFAULT_CLUSTER_NAME="lex-eks-cluster"
DEFAULT_REGION="us-west-2"
PROFILE="${3:-default}"

# Accepting inputs with defaults
CLUSTER_NAME="${1:-$DEFAULT_CLUSTER_NAME}"
REGION="${2:-$DEFAULT_REGION}"

echo "🗑️  Starting cleanup for EKS cluster $CLUSTER_NAME in region $REGION..."

# Delete EKS cluster and associated node groups
echo "Deleting EKS cluster..."
aws eks delete-cluster --name $CLUSTER_NAME --region $REGION --profile $PROFILE --output text

echo "Deleting node groups..."
aws eks list-nodegroups --cluster-name $CLUSTER_NAME --region $REGION --profile $PROFILE --output text | while read nodegroup; do
    echo "Deleting node group: $nodegroup"
    aws eks delete-nodegroup --cluster-name $CLUSTER_NAME --nodegroup-name $nodegroup --region $REGION --profile $PROFILE --output text
done

# Delete IAM roles
echo "Cleaning up IAM roles..."
aws iam list-roles --output text | grep eks | awk '{print $5}' | while read role; do
    echo "Deleting IAM role: $role"
    aws iam delete-role --role-name $role --output text
done

# Delete Load Balancers associated with the EKS cluster
echo "Deleting load balancers..."
aws elb describe-load-balancers --region $REGION --output text | awk '/LoadBalancerName/ {print $2}' | while read lb; do
    echo "Deleting load balancer: $lb"
    aws elb delete-load-balancer --load-balancer-name $lb --region $REGION --output text
done

echo "🧹 EKS cleanup completed!"
