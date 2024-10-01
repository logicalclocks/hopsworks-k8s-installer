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

#!/bin/bash

# (Previous code for ASCII art and configuration variables remains the same)

# Parse command-line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --name) name="$2"; shift ;;
            --email) email="$2"; shift ;;
            --company) company="$2"; shift ;;
            --license) license="$2"; shift ;;
            --agree) agree=true ;;
            --skip-requirements) skip_requirements=true ;;
            *) echo "Unknown option: $1" >&2; exit 1 ;;
        esac
        shift
    done
}

# Get user information (interactive or from arguments)
get_user_info() {
    if [[ -z $name ]]; then
        read -p "Your name: " name
    fi
    if [[ -z $email ]]; then
        read -p "Your email address: " email
    fi
    if [[ -z $company ]]; then
        read -p "Your company name: " company
    fi
    
    if [[ -z $license ]]; then
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
    else
        license_type=$([ "$license" == "startup" ] && echo "Startup" || echo "Evaluation")
    fi
    
    license_url=$([ "$license_type" == "Startup" ] && echo "$STARTUP_LICENSE_URL" || echo "$EVALUATION_LICENSE_URL")
    print_colored "\nPlease review the $license_type License Agreement at:" "blue"
    print_colored "$license_url" "blue"
    
    if [[ -z $agree ]]; then
        read -p "\nDo you agree to the terms and conditions? (yes/no): " agreement
        agree=$(echo $agreement | tr '[:upper:]' '[:lower:]')
    fi
}

# Main execution
parse_arguments "$@"

print_colored "$HOPSWORKS_LOGO" "blue"
print_colored "Welcome to the Hopsworks Helm Chart Installer!" "green"

if [[ -z $skip_requirements ]]; then
    check_requirements
fi

get_user_info

if [[ $agree != "yes" && $agree != "true" ]]; then
    print_colored "You must agree to the terms and conditions to proceed." "red"
    exit 1
fi

send_user_data
if [[ $? -ne 0 ]]; then
    print_colored "Failed to process user information. Installation cannot proceed." "red"
    exit 1
fi

install_hopsworks

print_colored "\nThank you for installing Hopsworks!" "green"
print_colored "If you need any assistance, please contact our support team." "blue"