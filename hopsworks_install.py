#!/usr/bin/env python3

import os
import sys
import subprocess
import uuid
from datetime import datetime
import json
import requests

BASE_URL = "https://raw.githubusercontent.com/MagicLex/hopsworks-k8s-installer/refs/heads/master/"
SERVER_URL = "https://magiclex--hopsworks-installation-hopsworks-installation.modal.run/"
STARTUP_LICENSE_URL = "https://www.hopsworks.ai/startup-license"
EVALUATION_LICENSE_URL = "https://www.hopsworks.ai/evaluation-license"

HOPSWORKS_LOGO = """
██╗  ██╗    ██████╗    ██████╗    ███████╗   ██╗    ██╗    ██████╗    ██████╗    ██╗  ██╗   ███████╗
██║  ██║   ██╔═══██╗   ██╔══██╗   ██╔════╝   ██║    ██║   ██╔═══██╗   ██╔══██╗   ██║ ██╔╝   ██╔════╝
███████║   ██║   ██║   ██████╔╝   ███████╗   ██║ █╗ ██║   ██║   ██║   ██████╔╝   █████╔╝    ███████╗ 
██╔══██║   ██║   ██║   ██╔═══╝    ╚════██║   ██║███╗██║   ██║   ██║   ██╔══██╗   ██╔═██╗    ╚════██║
██║  ██║   ╚██████╔╝   ██║        ███████║   ╚███╔███╔╝   ╚██████╔╝   ██║  ██║   ██║  ██╗   ███████║     
╚═╝  ╚═╝    ╚═════╝    ╚═╝        ╚══════╝    ╚══╝╚══╝     ╚═════╝    ╚═╝  ╚═╝   ╚═╝  ╚═╝   ╚══════╝
"""

def print_colored(message, color):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "magenta": "\033[95m", "cyan": "\033[96m",
        "white": "\033[97m", "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{message}{colors['reset']}")

def get_user_input(prompt, options=None):
    while True:
        response = input(prompt).strip()
        if options is None or response.lower() in options:
            return response
        else:
            print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "red")

def get_license_agreement():
    print_colored("\nPlease choose a license agreement:", "blue")
    print("1. Startup Software License")
    print("2. Evaluation Agreement")
    
    choice = get_user_input("Enter 1 or 2: ", ["1", "2"])
    license_type = "Startup" if choice == "1" else "Evaluation"
    license_url = STARTUP_LICENSE_URL if choice == "1" else EVALUATION_LICENSE_URL
    
    print_colored(f"\nPlease review the {license_type} License Agreement at:", "blue")
    print_colored(license_url, "blue")
    
    agreement = get_user_input("\nDo you agree to the terms and conditions? (yes/no): ", ["yes", "no"]).lower() == "yes"
    if not agreement:
        print_colored("You must agree to the terms and conditions to proceed.", "red")
        sys.exit(1)
    return license_type, agreement

def get_user_info():
    print_colored("\nPlease provide the following information:", "blue")
    name = input("Your name: ")
    email = input("Your email address: ")
    company = input("Your company name: ")
    return name, email, company

def send_user_data(name, email, company, license_type, agreed_to_license):
    print_colored("\nSending user data...", "blue")
    installation_id = str(uuid.uuid4())
    data = {
        "name": name, "email": email, "company": company,
        "license_type": license_type, "agreed_to_license": agreed_to_license,
        "installation_id": installation_id,
        "action": "install_hopsworks",
        "installation_date": datetime.now().isoformat()
    }
    try:
        response = requests.post(SERVER_URL, json=data, verify=False)
        response.raise_for_status()
        print_colored("User data sent successfully.", "green")
        return True, installation_id
    except requests.RequestException as e:
        print_colored(f"Failed to communicate with server: {e}", "red")
        return False, None

def download_script(script_name):
    url = BASE_URL + script_name
    local_path = script_name
    try:
        response = requests.get(url, verify=False)
        response.raise_for_status()
        with open(local_path, 'wb') as f:
            f.write(response.content)
        os.chmod(local_path, 0o755)
        return local_path
    except requests.RequestException as e:
        print_colored(f"Failed to download {script_name}: {e}", "red")
        return None

def main():
    print_colored(HOPSWORKS_LOGO, "blue")
    print_colored("Welcome to the Hopsworks Installation Script!", "green")

    license_type, agreement = get_license_agreement()
    name, email, company = get_user_info()
    success, installation_id = send_user_data(name, email, company, license_type, agreement)

    if success:
        print_colored(f"Installation ID: {installation_id}", "green")
        print_colored("Please keep this ID for your records and support purposes.", "yellow")
    else:
        print_colored("Failed to process user information. Continuing with installation.", "yellow")
        installation_id = "unknown"

    # Download and run hopsworks_dev_setup.py
    dev_setup_script = download_script("hopsworks_dev_setup.py")
    if dev_setup_script:
        subprocess.run([sys.executable, dev_setup_script])
    else:
        print_colored("Failed to download the Hopsworks setup script. Exiting.", "red")
        sys.exit(1)

    # Ask if user wants to set up ingress
    setup_ingress = get_user_input("Do you want to set up ingress? (yes/no): ", ["yes", "no"]).lower() == 'yes'
    if setup_ingress:
        ingress_script = download_script("setup_ingress.py")
        if ingress_script:
            subprocess.run([sys.executable, ingress_script])
        else:
            print_colored("Failed to download the ingress setup script. Skipping ingress setup.", "yellow")

    print_colored("\nInstallation completed successfully!", "green")
    print_colored(f"Your installation ID is: {installation_id}", "green")
    print_colored("Please keep this ID for your records and support purposes.", "yellow")
    print_colored("If you need any assistance, please contact our support team.", "blue")

if __name__ == "__main__":
    main()