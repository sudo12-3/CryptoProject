import hashlib
import time
import sys
import os

# Add the parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firebase_config import db
from firebase_admin import firestore

# Function to Generate MID
def generate_mid(merchant_name, password):
    timestamp = str(int(time.time()))  
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    raw_data = merchant_name + timestamp + password_hash
    final_hash = hashlib.sha256(raw_data.encode()).hexdigest()
    mid = final_hash[:16].upper()  
    return mid

# Function to Register a Merchant
def register_merchant(name, password, balance, ifsc_code):
    mid = generate_mid(name, password)
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    # Insert into Firebase
    merchant_ref = db.collection('merchants').document(mid)
    merchant_data = {
        'name': name,
        'password_hash': password_hash,
        'account_balance': float(balance),
        'ifsc_code': ifsc_code,
        'mid': mid,
        'created_at': firestore.SERVER_TIMESTAMP
    }
    
    merchant_ref.set(merchant_data)
    print(f"Merchant '{name}' registered successfully with MID: {mid}")
    return mid

# Example Usage
# register_merchant("JohnStore", "securePass123", 5000.00, "HDFC0001234")