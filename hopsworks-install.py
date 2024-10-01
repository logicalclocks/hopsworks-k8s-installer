#!/usr/bin/env python3
import subprocess
import requests
import sys
import os
import uuid
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

def parse_arguments():
    parser = argparse.ArgumentParser(description="Hopsworks Helm Chart Installer")
    parser.add_argument("--name", help="Your name")
    parser.add_argument("--email", help="Your email address")
    parser.add_argument("--company", help="Your company name")
    parser.add_argument("--license", choices=["startup", "evaluation"], help="License type")
    parser.add_argument("--agree", action="store_true", help="Agree to the license terms")
    parser.add_argument("--skip-requirements", action="store_true", help="Skip requirements check")
    return parser.parse_args()

def get_user_info(args):
    if all([args.name, args.email, args.company, args.license, args.agree]):
        return args.name, args.email, args.company, "Startup" if args.license == "startup" else "Evaluation", args.agree

    print_colored("\nPlease provide the following information:", "blue")
    name = args.name or input("Your name: ")
    email = args.email or input("Your email address: ")
    company = args.company or input("Your company name: ")
    
    if not args.license:
        print_colored("\nPlease choose a license agreement:", "blue")
        print("1. Startup Software License")
        print("2. Evaluation Agreement")
        while True:
            choice = input("Enter 1 or 2: ")
            if choice in ['1', '2']:
                break
            print_colored("Invalid choice. Please enter 1 or 2.", "yellow")
        license_type = "Startup" if choice == '1' else "Evaluation"
    else:
        license_type = "Startup" if args.license == "startup" else "Evaluation"
    
    license_url = STARTUP_LICENSE_URL if license_type == "Startup" else EVALUATION_LICENSE_URL
    print_colored(f"\nPlease review the {license_type} License Agreement at:", "blue")
    print_colored(license_url, "blue")
    
    agreement = args.agree or input("\nDo you agree to the terms and conditions? (yes/no): ").lower() == 'yes'
    
    return name, email, company, license_type, agreement

def main():
    print_colored(HOPSWORKS_LOGO, "blue")
    print_colored("Welcome to the Hopsworks Helm Chart Installer!", "green")
    
    args = parse_arguments()
    
    if not args.skip_requirements:
        check_requirements()
    
    name, email, company, license_type, agreement = get_user_info(args)
    
    if not agreement:
        print_colored("You must agree to the terms and conditions to proceed.", "red")
        sys.exit(1)
    
    success, installation_id = send_user_data(name, email, company, license_type, agreement)
    if not success:
        print_colored("Failed to process user information. Installation cannot proceed.", "red")
        sys.exit(1)
    
    print_colored(f"Installation ID: {installation_id}", "green")
    print_colored("Please keep this ID for your records and support purposes.", "yellow")
    
    install_hopsworks()
    
    print_colored("\nThank you for installing Hopsworks!", "green")
    print_colored("If you need any assistance, please contact our support team.", "blue")

if __name__ == "__main__":
    main()
