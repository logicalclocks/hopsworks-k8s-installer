import modal
import os
import requests
from datetime import datetime

# Define the custom image with only necessary dependencies
image = modal.Image.debian_slim(python_version="3.10").pip_install("requests")

# Create the Modal app
app = modal.App("hopsworks-installation")

# HubSpot API URL
HUBSPOT_API_URL = "https://api.hubapi.com/crm/v3/objects/contacts"

@app.function(image=image, secrets=[modal.Secret.from_name("hubspot-secret")])
@modal.web_endpoint(method="POST")
def hopsworks_installation(body: dict):
    try:
        HUBSPOT_API_KEY = os.environ["HUBSPOT_API_KEY"]
        if not HUBSPOT_API_KEY:
            raise ValueError("HUBSPOT_API_KEY is not set")

        # Prepare the data for HubSpot
        hubspot_data = {
            "properties": {
                "firstname": body.get('name', '').split()[0],
                "lastname": ' '.join(body.get('name', '').split()[1:]),
                "email": body.get('email', ''),
                "company": body.get('company', ''),
                "hopsworks_license_type": body.get('license_type', ''),
                "hopsworks_agreed_to_license": "Yes" if body.get('agreed_to_license', False) else "No",
                "hopsworks_installation_id": body.get('installation_id', ''),
                "hopsworks_installation_date": body.get('installation_date', datetime.now().isoformat())
            }
        }
        
        # Send data to HubSpot
        headers = {
            'Authorization': f'Bearer {HUBSPOT_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(HUBSPOT_API_URL, json=hubspot_data, headers=headers)
        response.raise_for_status()
        
        print(f"Successfully sent data to HubSpot. Status code: {response.status_code}")
        return {"message": "Installation data successfully sent to HubSpot"}

    except ValueError as e:
        print(f"Environment variable error: {str(e)}")
        return {"error": "Missing required environment variable"}, 500
    except requests.exceptions.RequestException as e:
        print(f"Error sending data to HubSpot: {str(e)}")
        print(f"Response content: {e.response.content if e.response else 'No response'}")
        return {"error": "Failed to send data to HubSpot"}, 500
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {"error": "An unexpected error occurred"}, 500

@app.function(image=image, secrets=[modal.Secret.from_name("hubspot-secret")])
def test_hubspot_connection():
    HUBSPOT_API_KEY = os.environ["HUBSPOT_API_KEY"]
    headers = {
        'Authorization': f'Bearer {HUBSPOT_API_KEY}',
        'Content-Type': 'application/json'
    }
    response = requests.get('https://api.hubapi.com/crm/v3/objects/contacts', headers=headers)
    if response.status_code == 200:
        print("Successfully connected to HubSpot API")
        return True
    else:
        print(f"Failed to connect to HubSpot API. Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return False

@app.local_entrypoint()
def main():
    with app.run():
        success = test_hubspot_connection.remote()
        print(f"HubSpot connection test {'succeeded' if success else 'failed'}")

# To run the app: modal run this_file.py
# To deploy the app: modal deploy this_file.py