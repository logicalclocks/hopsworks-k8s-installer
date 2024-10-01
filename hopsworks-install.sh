#!/bin/bash

# ASCII art for Hopsworks logo
cat << "EOF"
 _   _                                      _        
| | | |                                    | |       
| |_| | ___  _ __  _____      _____  _ __  | | _____ 
|  _  |/ _ \| '_ \/ __\ \ /\ / / _ \| '__| | |/ / __|
| | | | (_) | |_) \__ \\ V  V / (_) | |    |   <\__ \
\_| |_/\___/| .__/|___/ \_/\_/ \___/|_|    |_|\_\___/
            | |                                      
            |_|                                      
EOF

echo "Welcome to the Hopsworks Helm Chart Installer!"

# Configuration
SERVER_URL="https://magiclex--hopsworks-installation-hopsworks-installation.modal.run/"
HELM_REPO="https://repo.hopsworks.ai/helm/hopsworks"
CHART_NAME="hopsworks/hopsworks"
STARTUP_LICENSE_URL="https://www.hopsworks.ai/startup-license"
EVALUATION_LICENSE_URL="https://www.hopsworks.ai/evaluation-license"

# Function to print colored text
print_colored() {
    case $2 in
        "red") echo -e "\033[91m$1\033[0m" ;;
        "green") echo -e "\033[92m$1\033[0m" ;;
        "yellow") echo -e "\033[93m$1\033[0m" ;;
        "blue") echo -e "\033[96m$1\033[0m" ;;
        *) echo "$1" ;;
    esac
}

# Check requirements
check_requirements() {
    print_colored "Checking system requirements..." "blue"
    for tool in helm kubectl curl; do
        if command -v $tool >/dev/null 2>&1; then
            print_colored "✓ $tool is installed" "green"
        else
            print_colored "✗ $tool is not installed or not configured properly" "red"
            exit 1
        fi
    done
    print_colored "System requirements check completed." "green"
}

# Function to validate email format
validate_email() {
    local email=$1
    if [[ "$email" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
        return 0
    else
        return 1
    fi
}

# Get user information
get_user_info() {
    read -p "Your name: " name

    # Ensure valid email
    while true; do
        read -p "Your email address: " email
        if validate_email "$email"; then
            break
        else
            print_colored "Invalid email format. Please enter a valid email." "red"
        fi
    done

    read -p "Your company name: " company
    
    print_colored "\nPlease choose a license agreement:" "blue"
    echo "1. Startup Software License"
    echo "2. Evaluation Agreement"
    while true; do
        read -p "Enter 1 or 2: " choice
        if [[ $choice == "1" || $choice == "2" ]]; then
            break
        fi
        print_colored "Invalid choice. Please enter 1 or 2." "yellow"
    done
    license_type=$([ "$choice" == "1" ] && echo "Startup" || echo "Evaluation")
    
    license_url=$([ "$license_type" == "Startup" ] && echo "$STARTUP_LICENSE_URL" || echo "$EVALUATION_LICENSE_URL")
    print_colored "\nPlease review the $license_type License Agreement at:" "blue"
    print_colored "$license_url" "blue"
    
    read -p "\nDo you agree to the terms and conditions? (yes/no): " agreement
    agree=$(echo $agreement | tr '[:upper:]' '[:lower:]')
}

# Send user data to server
send_user_data() {
    local installation_id=$(uuidgen)
    local data="{\"name\":\"$name\",\"email\":\"$email\",\"company\":\"$company\",\"license_type\":\"$license_type\",\"agreed_to_license\":$([[ $agree == "yes" ]] && echo "true" || echo "false"),\"installation_id\":\"$installation_id\",\"action\":\"install_hopsworks\",\"installation_date\":\"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"}"
    
    local response=$(curl -s -X POST -H "Content-Type: application/json" -d "$data" "$SERVER_URL")
    
    if [[ $? -eq 0 ]]; then
        print_colored "User data sent successfully." "green"
        print_colored "Installation ID: $installation_id" "green"
        print_colored "Please keep this ID for your records and support purposes." "yellow"
        return 0
    else
        print_colored "Failed to send user data to server." "red"
        return 1
    fi
}

# Install Hopsworks
install_hopsworks() {
    print_colored "Installing Hopsworks..." "blue"
    
    helm repo add hopsworks "$HELM_REPO" || { print_colored "Failed to add Helm repo" "red"; exit 1; }
    helm repo update || { print_colored "Failed to update Helm repo" "red"; exit 1; }
    helm install hopsworks "$CHART_NAME" || { print_colored "Failed to install Hopsworks" "red"; exit 1; }
    
    print_colored "Hopsworks installed successfully!" "green"
}

# Main execution
print_colored "Welcome to the Hopsworks Helm Chart Installer!" "green"

check_requirements

get_user_info

if [[ $agree != "yes" ]]; then
    print_colored "You must agree to the terms and conditions to proceed." "red"
    exit 1
fi

send_user_data
if [[ $? -ne 0 ]]; then
    print_colored "Failed to process user information. Do you want to continue anyway? (yes/no)" "yellow"
    read continue_anyway
    if [[ $continue_anyway != "yes" ]]; then
        exit 1
    fi
fi

install_hopsworks

print_colored "\nThank you for installing Hopsworks!" "green"
print_colored "If you need any assistance, please contact our support team." "blue"
