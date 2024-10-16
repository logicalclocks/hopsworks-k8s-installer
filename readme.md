# Hopsworks Installer

This script automates the installation of Hopsworks on Kubernetes clusters, with specific optimizations for AWS EKS.

## Prerequisites

- Kubernetes cluster (1.27.0 or later)
- `kubectl` CLI tool
- `helm` CLI tool
- For AWS: Configured AWS CLI with appropriate permissions
- For AZURE: Configured AZURE CLI with appropriate permissions

## Usage
```bash
python3 hop-deploy.py | tee installation_log.txt
```

## Command-line Options
`--loadbalancer-only`: Skip installation and jump to LoadBalancer setup
`--no-user-data`: Skip sending user data
`--skip-license`: Skip license agreement step
`--namespace NAMESPACE`: Specify a custom namespace (default: 'hopsworks')

## Features

Supports multiple cloud environments (AWS, GCP, Azure, OVH, On-Premise/VM)
Automatic kubeconfig setup and verification
AWS EKS-specific optimizations
LoadBalancer address retrieval
Basic health checks post-installation

## Post-Installation
After successful installation, the script will provide:

LoadBalancer address
Hopsworks UI URL
Default login credentials

## Troubleshooting
If you encounter issues:

Check the `installation_log.txt` file for detailed logs
Ensure all prerequisites are met
Verify your Kubernetes cluster is properly configured

## Support
If you need assistance, contact our support team and provide your _installation ID_.


