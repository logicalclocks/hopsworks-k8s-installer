#!/bin/bash
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

# Interactive cleanup script for GKE and related resources
# Usage: ./cleanup-gke.sh "your project id"

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to prompt for yes/no confirmation
confirm() {
    local message="$1"
    while true; do
        read -p "${message} (y/n): " yn
        case $yn in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Please answer yes (y) or no (n).";;
        esac
    done
}

# Function to check if a resource exists
resource_exists() {
    if [ -n "$1" ]; then
        return 0
    else
        return 1
    fi
}

# Default project ID error check
if [ -z "$1" ]; then
    echo -e "${RED}Error: Project ID is required${NC}"
    echo "Usage: $0 <project-id>"
    exit 1
fi

PROJECT_ID="$1"

echo -e "${GREEN}🔍 Analyzing resources in project ${PROJECT_ID}...${NC}"

# Verify project access
if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
    echo -e "${RED}Error: Cannot access project ${PROJECT_ID}. Please check the project ID and your permissions.${NC}"
    exit 1
fi

# Find all GKE clusters in the project
echo -e "\n${YELLOW}Checking for GKE clusters...${NC}"
CLUSTERS=$(gcloud container clusters list --project "$PROJECT_ID" --format="table(name,zone,status)" 2>/dev/null)
if resource_exists "$CLUSTERS"; then
    echo -e "Found clusters:\n$CLUSTERS"
    if confirm "Would you like to delete these GKE clusters?"; then
        while IFS= read -r cluster_info; do
            if [ -n "$cluster_info" ] && [[ ! "$cluster_info" =~ "NAME" ]]; then
                CLUSTER_NAME=$(echo "$cluster_info" | awk '{print $1}')
                ZONE=$(echo "$cluster_info" | awk '{print $2}')
                echo "Deleting cluster $CLUSTER_NAME in zone $ZONE..."
                gcloud container clusters delete "$CLUSTER_NAME" \
                    --zone "$ZONE" \
                    --project "$PROJECT_ID" \
                    --quiet
            fi
        done <<< "$CLUSTERS"
    fi
else
    echo "No GKE clusters found."
fi

# Check for Hopsworks namespaces
echo -e "\n${YELLOW}Checking for Hopsworks resources...${NC}"
CLUSTERS_WITH_CREDS=$(gcloud container clusters list --project "$PROJECT_ID" --format="table(name,zone)" 2>/dev/null)
if resource_exists "$CLUSTERS_WITH_CREDS"; then
    while IFS= read -r cluster_info; do
        if [ -n "$cluster_info" ] && [[ ! "$cluster_info" =~ "NAME" ]]; then
            CLUSTER_NAME=$(echo "$cluster_info" | awk '{print $1}')
            ZONE=$(echo "$cluster_info" | awk '{print $2}')
            if gcloud container clusters get-credentials "$CLUSTER_NAME" --zone "$ZONE" --project "$PROJECT_ID" >/dev/null 2>&1; then
                if kubectl get namespace hopsworks >/dev/null 2>&1; then
                    echo "Found Hopsworks namespace in cluster $CLUSTER_NAME"
                    if confirm "Would you like to delete Hopsworks resources in cluster $CLUSTER_NAME?"; then
                        kubectl delete namespace hopsworks --ignore-not-found=true
                        kubectl delete serviceaccount -n hopsworks hopsworks-sa --ignore-not-found=true
                        kubectl delete configmap -n hopsworks docker-config --ignore-not-found=true
                    fi
                fi
            fi
        fi
    done <<< "$CLUSTERS_WITH_CREDS"
fi

# Check Artifact Registry repositories
echo -e "\n${YELLOW}Checking Artifact Registry repositories...${NC}"
REPOSITORIES=$(gcloud artifacts repositories list --project "$PROJECT_ID" --format="table(name,format,location)" 2>/dev/null | grep "hopsworks-")
if resource_exists "$REPOSITORIES"; then
    echo -e "Found repositories:\n$REPOSITORIES"
    # Ask for region once
    read -p "Enter the region for these repositories (e.g., europe-west1): " REPO_LOCATION
    
    if confirm "Would you like to delete these Artifact Registry repositories?"; then
        while IFS= read -r repo_info; do
            if [ -n "$repo_info" ] && [[ ! "$repo_info" =~ "NAME" ]]; then
                REPO_NAME=$(echo "$repo_info" | awk '{print $1}')
                echo "Deleting repository $REPO_NAME in $REPO_LOCATION..."
                gcloud artifacts repositories delete "$REPO_NAME" \
                    --location="$REPO_LOCATION" \
                    --project="$PROJECT_ID" \
                    --quiet
            fi
        done <<< "$REPOSITORIES"
    fi
else
    echo "No Hopsworks-related Artifact Registry repositories found."
fi

# Check IAM service accounts
echo -e "\n${YELLOW}Checking IAM service accounts...${NC}"
SERVICE_ACCOUNTS=$(gcloud iam service-accounts list --project "$PROJECT_ID" --format="table(email)" | grep "hopsworksai-instances")
if resource_exists "$SERVICE_ACCOUNTS"; then
    echo -e "Found service accounts:\n$SERVICE_ACCOUNTS"
    if confirm "Would you like to delete these service accounts?"; then
        while IFS= read -r sa_email; do
            if [ -n "$sa_email" ]; then
                echo "Deleting service account: $sa_email"
                gcloud iam service-accounts delete "$sa_email" \
                    --project "$PROJECT_ID" \
                    --quiet
            fi
        done <<< "$SERVICE_ACCOUNTS"
    fi
else
    echo "No Hopsworks-related service accounts found."
fi

# Check custom IAM roles
echo -e "\n${YELLOW}Checking custom IAM roles...${NC}"
CUSTOM_ROLES=$(gcloud iam roles list --project "$PROJECT_ID" --format="table(name)" | grep "hopsworksai.instances")
if resource_exists "$CUSTOM_ROLES"; then
    echo -e "Found custom roles:\n$CUSTOM_ROLES"
    if confirm "Would you like to delete these custom roles?"; then
        while IFS= read -r role; do
            if [ -n "$role" ]; then
                ROLE_ID=${role#projects/$PROJECT_ID/roles/}
                echo "Deleting role: $ROLE_ID"
                gcloud iam roles delete "$ROLE_ID" \
                    --project "$PROJECT_ID" \
                    --quiet
            fi
        done <<< "$CUSTOM_ROLES"
    fi
else
    echo "No Hopsworks-related custom roles found."
fi

# Check firewall rules
echo -e "\n${YELLOW}Checking firewall rules...${NC}"
FIREWALL_RULES=$(gcloud compute firewall-rules list --project "$PROJECT_ID" --format="table(name)" | grep "gke-")
if resource_exists "$FIREWALL_RULES"; then
    echo -e "Found firewall rules:\n$FIREWALL_RULES"
    if confirm "Would you like to delete these GKE-related firewall rules?"; then
        while IFS= read -r rule; do
            if [ -n "$rule" ] && [[ ! "$rule" =~ "NAME" ]]; then
                echo "Deleting firewall rule: $rule"
                gcloud compute firewall-rules delete "$rule" --project "$PROJECT_ID" --quiet
            fi
        done <<< "$FIREWALL_RULES"
    fi
else
    echo "No GKE-related firewall rules found."
fi

# Check load balancers and target pools
echo -e "\n${YELLOW}Checking load balancers and target pools...${NC}"
FORWARDING_RULES=$(gcloud compute forwarding-rules list --project "$PROJECT_ID" --format="table(name,region)" | grep "a[0-9a-f]\{12\}")
if resource_exists "$FORWARDING_RULES"; then
    echo -e "Found load balancers:\n$FORWARDING_RULES"
    if confirm "Would you like to delete these load balancers?"; then
        while IFS= read -r lb_info; do
            if [ -n "$lb_info" ] && [[ ! "$lb_info" =~ "NAME" ]]; then
                LB_NAME=$(echo "$lb_info" | awk '{print $1}')
                REGION=$(echo "$lb_info" | awk '{print $2}')
                echo "Deleting load balancer: $LB_NAME in region $REGION"
                gcloud compute forwarding-rules delete "$LB_NAME" \
                    --region "$REGION" \
                    --project "$PROJECT_ID" \
                    --quiet
            fi
        done <<< "$FORWARDING_RULES"
    fi
else
    echo "No matching load balancers found."
fi

echo -e "${GREEN}🧹 Cleanup process completed!${NC}"