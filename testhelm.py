class MockInstaller:
    def __init__(self):
        self.environment = "AWS"
        self.namespace = "hopsworks"
        self.managed_registry_info = {
            "domain": "755182613526.dkr.ecr.eu-west-1.amazonaws.com",
            "namespace": "hopsworks-testcluster"
        }

    def construct_helm_command(self):
        """Constructs the helm command with proper configuration"""
        # Base helm command
        helm_command = [
            "helm upgrade --install hopsworks-release hopsworks/hopsworks",
            f"--namespace={self.namespace}",
            "--create-namespace",
            "--values hopsworks/values.yaml"
        ]
        
        # Helper function to flatten nested dictionaries
        def flatten_dict(d, parent_key='', sep='.'):
            items = []
            for k, v in d.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten_dict(v, new_key, sep=sep).items())
                else:
                    items.append((new_key, v))
            return dict(items)

        # Start with base config
        helm_values = HELM_BASE_CONFIG.copy()
        
        # Add cloud-specific values
        if self.environment in CLOUD_SPECIFIC_VALUES:
            cloud_config = CLOUD_SPECIFIC_VALUES[self.environment].copy()
            
            # Handle dynamic registry values for AWS
            if self.environment == "AWS" and self.managed_registry_info:
                cloud_config.update({
                    "global._hopsworks.managedDockerRegistery.domain": self.managed_registry_info['domain'],
                    "global._hopsworks.managedDockerRegistery.namespace": self.managed_registry_info['namespace']
                })
            
            helm_values.update(cloud_config)

        # Flatten nested structures
        flat_values = flatten_dict(helm_values)
        
        # Add each value with proper escaping and formatting
        for key, value in flat_values.items():
            if value is None:
                value = "null"
            elif isinstance(value, bool):
                value = str(value).lower()
            elif isinstance(value, (int, float)):
                value = str(value)
            else:
                # Escape special characters in string values
                value = f'"{str(value)}"'
            
            helm_command.append(f"--set {key}={value}")

        # Add timeout and devel flag
        helm_command.extend([
            "--timeout 60m",
            "--devel"
        ])

        return " ".join(helm_command)

# Your existing constants
HELM_BASE_CONFIG = {
    "hopsworks.service.worker.external.https.type": "LoadBalancer",
    "global._hopsworks.externalLoadBalancers.enabled": "true",
    "global._hopsworks.imagePullPolicy": "Always",
    "hopsworks.replicaCount.worker": "1",
    "rondb.clusterSize.activeDataReplicas": "1",
    "hopsfs.datanode.count": "2"
}

CLOUD_SPECIFIC_VALUES = {
    "AWS": {
        "global._hopsworks.cloudProvider": "AWS",
        "global._hopsworks.ingressController.type": "none",
        "global._hopsworks.managedDockerRegistery.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.enabled": "true",
        "global._hopsworks.managedDockerRegistery.credHelper.secretName": "awsregcred",
        "global._hopsworks.storageClassName": "ebs-gp3",
        "hopsworks.variables.docker_operations_managed_docker_secrets": "awsregcred",
        "hopsworks.variables.docker_operations_image_pull_secrets": "awsregcred",
        "hopsworks.dockerRegistry.preset.secrets[0]": "awsregcred",
        "externalLoadBalancers": {
            "enabled": True,
            "class": None,
            "annotations": {
                "service.beta.kubernetes.io/aws-load-balancer-scheme": "internet-facing"
            }
        }
    }
}

# Test it
installer = MockInstaller()
print("\nGenerated Helm Command:")
print("=" * 80)
print(installer.construct_helm_command())
print("=" * 80)