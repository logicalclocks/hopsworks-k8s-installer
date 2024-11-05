#!/bin/bash

# chmod +x cleanup-aks.sh
# ./cleanup-aks.sh "your resource group name" "your cluster name" "your region"

# Default values
DEFAULT_RESOURCE_GROUP="lex-aks-rg"
DEFAULT_CLUSTER_NAME="lex-aks-cluster"
DEFAULT_REGION="eastus"

# Accepting inputs with defaults
RESOURCE_GROUP="${1:-$DEFAULT_RESOURCE_GROUP}"
CLUSTER_NAME="${2:-$DEFAULT_CLUSTER_NAME}"
REGION="${3:-$DEFAULT_REGION}"

echo "🗑️  Starting cleanup for AKS cluster $CLUSTER_NAME in resource group $RESOURCE_GROUP..."

# Delete AKS cluster
echo "Deleting AKS cluster..."
az aks delete --resource-group $RESOURCE_GROUP --name $CLUSTER_NAME --yes --no-wait

# Delete associated resources (if any)
echo "Deleting associated resources..."
az network lb list --resource-group $RESOURCE_GROUP --query "[].name" -o tsv | while read lb; do
    echo "Deleting load balancer: $lb"
    az network lb delete --name $lb --resource-group $RESOURCE_GROUP
done

az role assignment list --query "[].principalId" --output tsv | while read role; do
    echo "Deleting role assignment: $role"
    az role assignment delete --assignee $role --resource-group $RESOURCE_GROUP
done

echo "🧹 AKS cleanup completed!"
