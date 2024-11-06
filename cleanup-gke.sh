#!/bin/bash

# chmod +x cleanup-gke.sh
#./cleanup-gke.sh "your project id" " your project zone (eg:us-central1-a)" "your project region (eg:us-central1)" "your cluster name"

# Default values
DEFAULT_PROJECT_ID="lexkube"
DEFAULT_ZONE="europe-west1-b"
DEFAULT_REGION="europe-west1"
DEFAULT_CLUSTER_NAME="le-gke"

# Accepting inputs with defaults
PROJECT_ID="${1:-$DEFAULT_PROJECT_ID}"
ZONE="${2:-$DEFAULT_ZONE}"
REGION="${3:-$DEFAULT_REGION}"
CLUSTER_NAME="${4:-$DEFAULT_CLUSTER_NAME}"

echo "🗑️  Starting cleanup for project $PROJECT_ID..."

# Delete GKE cluster first (this will clean up most GKE-specific resources)
echo "Deleting GKE cluster..."
gcloud container clusters delete $CLUSTER_NAME \
    --zone $ZONE \
    --project $PROJECT_ID \
    --quiet

# Delete Artifact Registry repositories
echo "Cleaning up Artifact Registry..."
gcloud artifacts repositories list --project $PROJECT_ID --format="value(name)" | while read repo; do
    echo "Deleting repository: $repo"
    gcloud artifacts repositories delete $repo \
        --location $REGION \
        --project $PROJECT_ID \
        --quiet
done

# List and delete custom IAM roles
echo "Cleaning up custom IAM roles..."
gcloud iam roles list --project $PROJECT_ID --format="value(name)" | while read role; do
    if [[ $role == projects/$PROJECT_ID/roles/hopsworks* ]] || [[ $role == projects/$PROJECT_ID/roles/hopsworksai* ]]; then
        echo "Deleting role: $role"
        gcloud iam roles delete ${role#projects/$PROJECT_ID/roles/} \
            --project $PROJECT_ID \
            --quiet
    fi
done

# Delete service accounts
echo "Cleaning up service accounts..."
gcloud iam service-accounts list --project $PROJECT_ID --format="value(email)" | while read sa; do
    if [[ $sa == hopsworks* ]] || [[ $sa == *@$PROJECT_ID.iam.gserviceaccount.com ]]; then
        echo "Deleting service account: $sa"
        gcloud iam service-accounts delete $sa \
            --project $PROJECT_ID \
            --quiet
    fi
done

# Clean up any leftover firewall rules
gcloud compute firewall-rules list --filter="name~'gke-'" --format="value(name)" | while read rule; do
    echo "Deleting firewall rule: $rule"
    gcloud compute firewall-rules delete $rule --quiet
done

# Clean up any leftover target pools
gcloud compute target-pools list --format="value(name)" | while read pool; do
    if [[ $pool == k8s* ]]; then
        echo "Deleting target pool: $pool"
        gcloud compute target-pools delete $pool --region $REGION --quiet
    fi
done

echo "🧹 Cleanup completed!"
