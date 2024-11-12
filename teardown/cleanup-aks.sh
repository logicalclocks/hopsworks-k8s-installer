#!/bin/bash
#chmod +x cleanup-aks.sh
#./cleanup-aks.sh "your-resource-group-name"

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

# Default resource group error check
if [ -z "$1" ]; then
    echo -e "${RED}Error: Resource group is required${NC}"
    echo "Usage: $0 <resource-group>"
    exit 1
fi

RESOURCE_GROUP="$1"

echo -e "${GREEN}🔍 Analyzing resources in resource group ${RESOURCE_GROUP}...${NC}"

# Verify resource group access
if ! az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo -e "${RED}Error: Cannot access resource group ${RESOURCE_GROUP}. Please check the name and your permissions.${NC}"
    exit 1
fi

# Find all AKS clusters in the resource group
echo -e "\n${YELLOW}Checking for AKS clusters...${NC}"
CLUSTERS=$(az aks list --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv 2>/dev/null)
if resource_exists "$CLUSTERS"; then
    echo -e "Found clusters:\n$CLUSTERS"
    if confirm "Would you like to delete these AKS clusters?"; then
        while IFS= read -r CLUSTER_NAME; do
            if [ -n "$CLUSTER_NAME" ]; then
                echo "Deleting cluster $CLUSTER_NAME..."
                az aks delete \
                    --name "$CLUSTER_NAME" \
                    --resource-group "$RESOURCE_GROUP" \
                    --yes \
                    --no-wait
            fi
        done <<< "$CLUSTERS"
    fi
else
    echo "No AKS clusters found."
fi

# Check for Load Balancers
echo -e "\n${YELLOW}Checking for Load Balancers...${NC}"
LBS=$(az network lb list --resource-group "$RESOURCE_GROUP" --query "[].{name:name,type:type}" -o table)
if resource_exists "$LBS"; then
    echo -e "Found load balancers:\n$LBS"
    if confirm "Would you like to delete these Load Balancers?"; then
        while IFS= read -r lb_info; do
            if [ -n "$lb_info" ] && [[ ! "$lb_info" =~ "Name" ]]; then
                LB_NAME=$(echo "$lb_info" | awk '{print $1}')
                echo "Deleting load balancer: $LB_NAME"
                az network lb delete \
                    --name "$LB_NAME" \
                    --resource-group "$RESOURCE_GROUP" \
                    --no-wait
            fi
        done <<< "$LBS"
    fi
else
    echo "No Load Balancers found."
fi

# Check for Public IPs
echo -e "\n${YELLOW}Checking for Public IPs...${NC}"
PIPS=$(az network public-ip list --resource-group "$RESOURCE_GROUP" --query "[].{name:name,ipAddress:ipAddress}" -o table)
if resource_exists "$PIPS"; then
    echo -e "Found public IPs:\n$PIPS"
    if confirm "Would you like to delete these Public IPs?"; then
        while IFS= read -r pip_info; do
            if [ -n "$pip_info" ] && [[ ! "$pip_info" =~ "Name" ]]; then
                PIP_NAME=$(echo "$pip_info" | awk '{print $1}')
                echo "Deleting public IP: $PIP_NAME"
                az network public-ip delete \
                    --name "$PIP_NAME" \
                    --resource-group "$RESOURCE_GROUP" \
                    --no-wait
            fi
        done <<< "$PIPS"
    fi
else
    echo "No Public IPs found."
fi

# Check for Network Security Groups
echo -e "\n${YELLOW}Checking for Network Security Groups...${NC}"
NSGS=$(az network nsg list --resource-group "$RESOURCE_GROUP" --query "[].{name:name}" -o table)
if resource_exists "$NSGS"; then
    echo -e "Found NSGs:\n$NSGS"
    if confirm "Would you like to delete these Network Security Groups?"; then
        while IFS= read -r nsg_info; do
            if [ -n "$nsg_info" ] && [[ ! "$nsg_info" =~ "Name" ]]; then
                NSG_NAME=$(echo "$nsg_info" | awk '{print $1}')
                echo "Deleting NSG: $NSG_NAME"
                az network nsg delete \
                    --name "$NSG_NAME" \
                    --resource-group "$RESOURCE_GROUP" \
                    --no-wait
            fi
        done <<< "$NSGS"
    fi
else
    echo "No Network Security Groups found."
fi

# Check for VNets
echo -e "\n${YELLOW}Checking for Virtual Networks...${NC}"
VNETS=$(az network vnet list --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv)
if resource_exists "$VNETS"; then
    echo -e "Found VNets:\n$VNETS"
    if confirm "Would you like to delete these Virtual Networks?"; then
        while IFS= read -r VNET_NAME; do
            if [ -n "$VNET_NAME" ]; then
                echo "Deleting VNet: $VNET_NAME"
                az network vnet delete \
                    --name "$VNET_NAME" \
                    --resource-group "$RESOURCE_GROUP" \
                    --no-wait
            fi
        done <<< "$VNETS"
    fi
else
    echo "No Virtual Networks found."
fi

# Check for Managed Identities
echo -e "\n${YELLOW}Checking for Managed Identities...${NC}"
IDENTITIES=$(az identity list --resource-group "$RESOURCE_GROUP" --query "[].{name:name}" -o table)
if resource_exists "$IDENTITIES"; then
    echo -e "Found Managed Identities:\n$IDENTITIES"
    if confirm "Would you like to delete these Managed Identities?"; then
        while IFS= read -r identity_info; do
            if [ -n "$identity_info" ] && [[ ! "$identity_info" =~ "Name" ]]; then
                IDENTITY_NAME=$(echo "$identity_info" | awk '{print $1}')
                echo "Deleting Managed Identity: $IDENTITY_NAME"
                az identity delete \
                    --name "$IDENTITY_NAME" \
                    --resource-group "$RESOURCE_GROUP" \
                    --no-wait
            fi
        done <<< "$IDENTITIES"
    fi
else
    echo "No Managed Identities found."
fi

# Check for Role Assignments
echo -e "\n${YELLOW}Checking for Role Assignments...${NC}"
ASSIGNMENTS=$(az role assignment list --resource-group "$RESOURCE_GROUP" --query "[].{principalName:principalName, roleDefinitionName:roleDefinitionName}" -o table)
if resource_exists "$ASSIGNMENTS"; then
    echo -e "Found Role Assignments:\n$ASSIGNMENTS"
    if confirm "Would you like to delete these Role Assignments?"; then
        while IFS= read -r assignment_info; do
            if [ -n "$assignment_info" ] && [[ ! "$assignment_info" =~ "PrincipalName" ]]; then
                PRINCIPAL_ID=$(echo "$assignment_info" | awk '{print $1}')
                echo "Deleting Role Assignment for principal: $PRINCIPAL_ID"
                az role assignment delete \
                    --assignee "$PRINCIPAL_ID" \
                    --resource-group "$RESOURCE_GROUP" \
                    --yes
            fi
        done <<< "$ASSIGNMENTS"
    fi
else
    echo "No Role Assignments found."
fi

# Optional: Delete the resource group itself
if confirm "Would you like to delete the entire resource group ${RESOURCE_GROUP}?"; then
    echo "Deleting resource group ${RESOURCE_GROUP}..."
    az group delete --name "$RESOURCE_GROUP" --yes --no-wait
fi

echo -e "${GREEN}🧹 Cleanup process completed!${NC}"
echo -e "${YELLOW}Note: Some resources are being deleted asynchronously and may take a few minutes to complete.${NC}"
