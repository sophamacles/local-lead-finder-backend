import os, requests
from dotenv import load_dotenv
load_dotenv()

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET")
PAYPAL_API_BASE = os.getenv("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")

def get_access_token():
    auth = (PAYPAL_CLIENT_ID, PAYPAL_SECRET)
    headers = {"Accept": "application/json", "Accept-Language": "en_US"}
    data = {"grant_type":"client_credentials"}
    r = requests.post(f"{PAYPAL_API_BASE}/v1/oauth2/token", headers=headers, data=data, auth=auth, timeout=15)
    r.raise_for_status()
    return r.json().get("access_token")

def create_subscription(plan_id, return_url, cancel_url):
    token = get_access_token()
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {token}"}
    payload = {
        "plan_id": plan_id,
        "application_context": {
            "brand_name": "Local Lead Finder",
            "return_url": return_url,
            "cancel_url": cancel_url
        }
    }
    r = requests.post(f"{PAYPAL_API_BASE}/v1/billing/subscriptions", json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

def get_subscription_status(subscription_id):
    token = get_access_token()
    headers = {"Authorization":f"Bearer {token}"}
    r = requests.get(f"{PAYPAL_API_BASE}/v1/billing/subscriptions/{subscription_id}", headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()
