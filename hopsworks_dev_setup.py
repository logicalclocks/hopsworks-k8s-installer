#!/usr/bin/env python3

import subprocess
import sys
import os
import shutil

def print_colored(message, color):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "cyan": "\033[96m", "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{message}{colors['reset']}")

def run_command(command, verbose=True):
    if verbose:
        print_colored(f"Running command: {command}", "cyan")
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if verbose:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print_colored(result.stderr, "yellow")
    return result.returncode == 0, result.stdout, result.stderr

def setup_kubeconfig():
    print_colored("\nSetting up kubeconfig...", "blue")
    
    kubeconfig_path = input("Enter the path to your kubeconfig file: ").strip()
    kubeconfig_path = os.path.expanduser(kubeconfig_path)

    if not os.path.exists(kubeconfig_path):
        print_colored(f"The file {kubeconfig_path} does not exist. Please check the path and try again.", "red")
        return None

    default_kubeconfig = os.path.expanduser("~/.kube/config")
    os.makedirs(os.path.dirname(default_kubeconfig), exist_ok=True)
    shutil.copy2(kubeconfig_path, default_kubeconfig)
    
    print_colored(f"Copied kubeconfig to {default_kubeconfig}", "green")

    try:
        os.chmod(default_kubeconfig, 0o600)
        print_colored("Updated kubeconfig file permissions to 600.", "green")
    except Exception as e:
        print_colored(f"Failed to update kubeconfig file permissions: {str(e)}", "yellow")
        print_colored(f"Please manually run: chmod 600 {default_kubeconfig}", "yellow")

    success, output, error = run_command("kubectl config current-context", verbose=False)
    if not success:
        print_colored("Failed to get current context. Please check if the kubeconfig is valid.", "red")
        print_colored("Error output:", "red")
        print(error)
        return None
    
    print_colored(f"Current context: {output.strip()}", "green")
    return default_kubeconfig

def install_hopsworks_dev(namespace):
    print_colored("\nPreparing to install Hopsworks (Development Setup)...", "blue")
    
    helm_repo_add_cmd = "helm repo add hopsworks https://nexus.hops.works/repository/hopsworks-helm --force-update"
    success, _, error = run_command(helm_repo_add_cmd)
    if not success:
        print_colored("Failed to add Helm repository.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    run_command("helm repo update")
    
    if os.path.exists('hopsworks'):
        shutil.rmtree('hopsworks')
    
    helm_pull_cmd = "helm pull hopsworks/hopsworks --untar --devel"
    success, _, error = run_command(helm_pull_cmd)
    if not success:
        print_colored("Failed to pull Hopsworks chart.", "red")
        print_colored(f"Error: {error}", "red")
        sys.exit(1)
    
    print_colored("Installing Hopsworks...", "blue")
    helm_command = (
        f"helm install hopsworks-release ./hopsworks "
        f"--namespace={namespace} "
        f"--create-namespace "
        f"--values hopsworks/values.services.yaml "
        f"--values hopsworks/values.yaml "
        f"--values hopsworks/values.dev.yaml "
        f"--timeout 60m "
        f"--wait "
        f"--debug "
        f"--devel"
    )
    
    process = subprocess.Popen(helm_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
    
    rc = process.poll()
    
    if rc == 0:
        print_colored("✓ Hopsworks (Development Setup) installed successfully!", "green")
    else:
        print_colored("⚠ Helm command completed with non-zero exit code", "yellow")
        print_colored("The installation might have partially succeeded. Checking status...", "yellow")
        
        status_command = f"helm status hopsworks-release -n {namespace}"
        success, status_output, _ = run_command(status_command)
        
        if success and "STATUS: deployed" in status_output:
            print_colored("✓ Hopsworks release is showing as deployed!", "green")
            print_colored("You may need to wait for all pods to be ready.", "yellow")
        else:
            print_colored("✗ Hopsworks installation seems to have failed", "red")
            print_colored("Please check the Helm and Kubernetes logs for more details.", "red")
        
    print_colored("\nChecking status of pods in the hopsworks namespace:", "blue")
    run_command(f"kubectl get pods -n {namespace}")

def main():
    print_colored("Starting Hopsworks Development Setup...", "blue")
    
    kubeconfig_path = setup_kubeconfig()
    if kubeconfig_path is None:
        print_colored("Failed to set up a valid kubeconfig. Exiting.", "red")
        sys.exit(1)
    
    namespace = input("Enter the namespace for Hopsworks installation (default: hopsworks): ").strip() or "hopsworks"
    
    install_hopsworks_dev(namespace)
    
    print_colored("Hopsworks Development Setup completed.", "green")

if __name__ == "__main__":
    main()