#!/usr/bin/env python3
import subprocess
import requests
import sys
import os
import uuid
import re
from datetime import datetime

# ASCII art for Hopsworks logo
HOPSWORKS_LOGO = """
 _   _                                      _        
| | | |                                    | |       
| |_| | ___  _ __  _____      _____  _ __  | | _____ 
|  _  |/ _ \| '_ \/ __\ \ /\ / / _ \| '__| | |/ / __|
| | | | (_) | |_) \__ \\ V  V / (_) | |    |   <\__ \\
\_| |_/\___/| .__/|___/ \_/\_/ \___/|_|    |_|\_\___/
            | |                                      
            |_|                                      
"""

# Configuration
SERVER_URL = "https://magiclex--hopsworks-installation-hopsworks-installation.modal.run/"
HELM_REPO = "https://repo.hopsworks.ai/helm/hopsworks"
CHART_NAME = "hopsworks/hopsworks"

# License agreement URLs
STARTUP_LICENSE_URL = "https://www.hopsworks.ai/startup-license"
EVALUATION_LICENSE_URL = "https://www.hopsworks.ai/evaluation-license"

def print_colored(text, color):
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[96m',
        'reset': '\033[0m'
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")

def check_requirements():
    print_colored("Checking system requirements...", "blue")
    
    requirements = [
        ("helm", "helm version"),
        ("kubectl", "kubectl version --client"),
    ]
    
    for tool, command in requirements:
        try:
            subprocess.run(command.split(), check=True, capture_output=True)
            print_colored(f"✓ {tool} is installed", "green")
        except subprocess.CalledProcessError:
            print_colored(f"✗ {tool} is not installed or not configured properly", "red")
            sys.exit(1)
    
    print_colored("All system requirements are met.", "green")

def is_valid_email(email):
    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(email_regex, email) is not None

def get_valid_email():
    while True:
        email = input("Your email address: ")
        if is_valid_email(email):
            return email
        else:
            print_colored("Invalid email format. Please try again.", "red")

def get_user_info():
    print_colored("\nPlease provide the following information:", "blue")
    name = input("Your name: ")
    
    email = get_valid_email()
    
    company = input("Your company name: ")
    
    print_colored("\nPlease choose a license agreement:", "blue")
    print("1. Startup Software License")
    print("2. Evaluation Agreement")
    
    while True:
        choice = input("Enter 1 or 2: ")
        if choice in ['1', '2']:
            break
        print_colored("Invalid choice. Please enter 1 or 2.", "yellow")
    
    license_url = STARTUP_LICENSE_URL if choice == '1' else EVALUATION_LICENSE_URL
    license_type = "Startup" if choice == '1' else "Evaluation"
    
    print_colored(f"\nPlease review the {license_type} License Agreement at:", "blue")
    print_colored(license_url, "blue")
    
    agreement = input("\nDo you agree to the terms and conditions? (yes/no): ").lower() == 'yes'
    
    return name, email, company, license_type, agreement

def send_user_data(name, email, company, license_type, agreed_to_license):
    try:
        installation_id = str(uuid.uuid4())
        data = {
            "name": name,
            "email": email,
            "company": company,
            "license_type": license_type,
            "agreed_to_license": agreed_to_license,
            "installation_id": installation_id,
            "action": "install_hopsworks",
            "installation_date": datetime.now().isoformat()
        }
        response = requests.post(SERVER_URL, json=data)
        response.raise_for_status()
        return True, installation_id
    except requests.exceptions.RequestException as e:
        print_colored(f"Failed to communicate with server: {e}", "red")
        return False, None

def install_hopsworks():
    print_colored("Installing Hopsworks...", "blue")
    
    helm_commands = [
        ["helm", "repo", "add", "hopsworks", HELM_REPO],
        ["helm", "repo", "update"],
        ["helm", "install", "hopsworks", CHART_NAME]
    ]
    
    for cmd in helm_commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print_colored(f"✓ {' '.join(cmd)} executed successfully", "green")
        else:
            print_colored(f"✗ Failed to execute {' '.join(cmd)}", "red")
            print(result.stderr)
            sys.exit(1)
    
    print_colored("Hopsworks installed successfully!", "green")

def main():
    print_colored(HOPSWORKS_LOGO, "blue")
    print_colored("Welcome to the Hopsworks Helm Chart Installer!", "green")
    
    check_requirements()
    
    name, email, company, license_type, agreement = get_user_info()
    
    if not agreement:
        print_colored("You must agree to the terms and conditions to proceed.", "red")
        sys.exit(1)
    
    success, installation_id = send_user_data(name, email, company, license_type, agreement)
    if not success:
        print_colored("Failed to process user information. Do you want to continue anyway? (yes/no)", "yellow")
        if input().lower() != 'yes':
            sys.exit(1)
    else:
        print_colored(f"Installation ID: {installation_id}", "green")
        print_colored("Please keep this ID for your records and support purposes.", "yellow")
    
    install_hopsworks()
    
    print_colored("\nThank you for installing Hopsworks!", "green")
    print_colored("If you need any assistance, please contact our support team.", "blue")

if __name__ == "__main__":
    main()
