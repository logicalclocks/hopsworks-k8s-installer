![alt text](assets/logo.png)

## Prerequisites
You will need the following packages; yaml, kubectl, helm 

For your cloud provider, you will need to install their dedicated CLI;
- _gcloud_ CLI for Google Cloud
- _aws-cli_ and _eksctl_ for AWS 
- _Azure CLI_ for Azure 

For **OVHCloud**; you can download the kubeconfig.yml file locally and use it during the installation. Regardless of the cloud provider, be sure to to have the approriate permissions to access ressources and create new ones. 

## Requirements
Hopsworks requires a minimum of 6 nodes and Kubernetes >= 1.27.0.
Be sure to have a stable connection, you might need to use some of the command line options to continue the installation if you lose connection during the installation. 

# gcloud additional components
```bash
gcloud components install gke-gcloud-auth-plugin kubectl
```
## Usage
```bash
python3 install-hopsworks.py | tee installation_log.txt
```

## Command-line Options
- `--loadbalancer-only`: Skip installation and jump to LoadBalancer setup
- `--no-user-data`: Skip sending user data
- `--skip-license`: Skip license agreement step
- `--namespace NAMESPACE`: Specify a custom namespace (default: 'hopsworks')

## Post-Installation
After successful installation, the script will provide:

LoadBalancer address
Hopsworks UI URL
Default login credentials

## Cleaning Up ressources
We provide _cleanup-aks.sh_, _cleanup-eks.sh_ and _cleanup-gke.sh_ to help cleanup ressources, roles and registry in case you need to re-install or are attempting to reinstall. Be careful using those script as they might remove additional roles and permissions.

### Example Usage:
```bash
chmod +x cleanup-gke.sh
./cleanup-gke.sh "your project id" " your project zone (eg:us-central1-a)" "your project region (eg:us-central1)" "your cluster name"
```


## Troubleshooting
If you encounter issues:

Check the `installation_log.txt` file for detailed logs
Ensure all prerequisites are met
Verify your Kubernetes cluster is properly configured

## Support
If you need assistance, contact our support team and provide your _installation ID_ or _email_.