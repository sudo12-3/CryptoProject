import firebase_admin
from firebase_admin import credentials, firestore
import os

# Path to your Firebase service account key JSON file
# You'll need to download this from your Firebase project settings
SERVICE_ACCOUNT_KEY_PATH = "serviceAccountKey.json"

def initialize_firebase():
    """Initialize Firebase Admin SDK and return Firestore client"""
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    return db

# Get Firestore database instance
db = initialize_firebase()