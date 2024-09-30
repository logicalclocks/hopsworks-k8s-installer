import requests

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