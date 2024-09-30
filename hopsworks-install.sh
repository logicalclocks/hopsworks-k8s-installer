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

echo "Welcome to the Hopsworks Helm Chart Installer! (Local Testing Version)"

# Configuration
SERVER_URL="http://localhost:8000/mock-server"  # Mock server URL for testing
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
    for tool in helm kubectl; do
        if command -v $tool >/dev/null 2>&1; then
            print_colored "✓ $tool is installed" "green"
        else
            print_colored "✗ $tool is not installed or not configured properly" "red"
            print_colored "This is a test run, so we'll continue anyway." "yellow"
        fi
    done
    print_colored "System requirements check completed." "green"
}

# Get user information
get_user_info() {
    print_colored "\nPlease provide the following information:" "blue"
    read -p "Your name: " name
    read -p "Your email address: " email
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
    
    if [[ $choice == "1" ]]; then
        license_url=$STARTUP_LICENSE_URL
        license_type="Startup"
    else
        license_url=$EVALUATION_LICENSE_URL
        license_type="Evaluation"
    fi
    
    print_colored "\nPlease review the $license_type License Agreement at:" "blue"
    print_colored "$license_url" "blue"
    
    read -p "\nDo you agree to the terms and conditions? (yes/no): " agreement
    agreement=$(echo $agreement | tr '[:upper:]' '[:lower:]')
}

# Send user data to server (mocked for local testing)
send_user_data() {
    installation_id=$(uuidgen 2>/dev/null || echo "test-installation-id-$(date +%s)")
    print_colored "Sending user data to server (mocked for local testing)..." "blue"
    print_colored "Installation ID: $installation_id" "green"
    print_colored "Please keep this ID for your records and support purposes." "yellow"
    return 0
}

# Install Hopsworks (mocked for local testing)
install_hopsworks() {
    print_colored "Installing Hopsworks (mocked for local testing)..." "blue"
    print_colored "Hopsworks installation simulated successfully!" "green"
}

# Main execution
check_requirements
get_user_info

if [[ $agreement != "yes" ]]; then
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

print_colored "\nThank you for testing the Hopsworks installation!" "green"
print_colored "This was a local test run. In a real installation, Hopsworks would now be installed on your system." "blue"
print_colored "If you need any assistance, please contact our support team." "blue"