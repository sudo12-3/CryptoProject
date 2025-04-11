from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys
import json
from datetime import datetime
import argparse
import uuid
import hashlib

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import blockchain module
from blockchan import Blockchain

# Import SpeckCipher from Merchant API
from Merchant.merchant_api import SpeckCipher

app = Flask(__name__)
app.secret_key = "bank_app_secret_key"
app.template_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# Check if Firebase already initialized
if not firebase_admin._apps:
    # Initialize Firebase
    cred_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                           'serviceAccountKey.json')
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Initialize blockchains for each bank
banks = ["HDFC", "ICICI", "SBI"]
blockchains = {}
for bank in banks:
    blockchains[bank] = Blockchain(bank)

@app.route('/')
def home():
    return render_template('bank_dashboard.html')

@app.route('/verify_transaction', methods=['POST'])
def verify_transaction():
    data = request.json
    print(f"Received transaction data: {data}")  # Debug logging
    
    # Extract transaction details
    mmid = data.get('mmid')
    merchant_id = data.get('merchant_id') or data.get('vid')  # Try both fields
    amount = data.get('amount')
    pin = data.get('pin')
    transaction_id = data.get('transaction_id', str(uuid.uuid4()))
    
    if not all([mmid, amount, pin]):
        return jsonify({
            "status": "failed", 
            "message": "Missing required transaction details",
            "transaction_id": transaction_id
        })
    
    print(f"Looking up user with MMID: {mmid}")  # Debug logging
    
    # Look up user by MMID instead of user_id
    users_ref = db.collection('users').where('mmid', '==', mmid).limit(1).get()
    
    # Check if user exists
    if not users_ref or len(users_ref) == 0:
        print(f"No user found with MMID: {mmid}")  # Debug logging
        return jsonify({
            "status": "failed", 
            "message": "User not found with the provided MMID",
            "transaction_id": transaction_id
        })
    
    # Get the first matching user
    user_data = users_ref[0].to_dict()
    user_id = users_ref[0].id
    
    print(f"Found user: {user_id}")  # Debug logging
    
    # Add right after retrieving user_data
    print("User data keys:", user_data.keys())
    print("PIN field:", "pin" if "pin" in user_data else "pin_hash" if "pin_hash" in user_data else "Not found")
    
    # Replace PIN verification section with this:
    print(f"Verifying PIN for user: {user_id}")

    # Look for pin_hash instead of pin
    stored_pin_hash = user_data.get('pin_hash')
    print(f"Stored PIN hash from database: {str(stored_pin_hash)[:10]}...")

    # Hash the input PIN for comparison
    input_pin_hash = hashlib.sha256(str(pin).encode()).hexdigest()
    print(f"Input PIN hash: {input_pin_hash[:10]}...")

    if stored_pin_hash != input_pin_hash:
        print("PIN hash mismatch!")
        return jsonify({
            "status": "failed", 
            "message": "Invalid PIN",
            "transaction_id": transaction_id
        })

    print("PIN verification successful")
    
    # Check if user has sufficient balance
    if user_data.get('balance', 0) < float(amount):
        return jsonify({
            "status": "failed", 
            "message": "Insufficient balance",
            "transaction_id": transaction_id
        })
    
    # Update the merchant lookup section with this improved approach
    # Get merchant details (if merchant_id provided)
    merchant_data = None
    if merchant_id:
        print(f"Looking up merchant using VID: {merchant_id}")  # Debug logging
        
        # First, try direct lookup in case it's actually a MID
        merchant_ref = db.collection('merchants').document(merchant_id)
        merchant_doc = merchant_ref.get()
        
        if merchant_doc.exists:
            merchant_data = merchant_doc.to_dict()
            print(f"Found merchant directly with ID: {merchant_id}")
        else:
            print(f"Direct lookup failed for: {merchant_id}")
            
            # New approach: Get all merchants and check if any of their MIDs
            # when encrypted match the provided VID
            print("Scanning all merchants to find matching VID...")
            
            # Import the encryption function from merchant_api
            from Merchant.merchant_api import encrypt_speck
            
            # Get all merchants from the database
            all_merchants = db.collection('merchants').get()
            found_match = False
            
            # Check each merchant
            for merchant_doc in all_merchants:
                mid = merchant_doc.id
                
                try:
                    # Generate VID from the MID
                    generated_vid = encrypt_speck(mid)
                    
                    # Compare with the provided VID
                    print(f"Comparing - Generated VID: {generated_vid} vs Provided VID: {merchant_id}")
                    
                    if generated_vid == merchant_id:
                        # Found the matching merchant!
                        merchant_data = merchant_doc.to_dict()
                        print(f"✅ Found matching merchant: {mid} for VID: {merchant_id}")
                        merchant_id = mid  # Update merchant_id to use the matched MID
                        found_match = True
                        break
                except Exception as e:
                    print(f"Error generating VID for MID {mid}: {str(e)}")
                    continue
            
            # If no match found after checking all merchants
            if not found_match:
                print(f"❌ No merchant found matching VID: {merchant_id}")
                return jsonify({
                    "status": "failed", 
                    "message": "Merchant not found for the provided VID",
                    "transaction_id": transaction_id
                })
    
    # Process transaction
    try:
        # Update user balance
        user_ref = db.collection('users').document(user_id)
        new_user_balance = user_data.get('balance', 0) - float(amount)
        user_ref.update({"balance": new_user_balance})
        
        # Update merchant balance if applicable
        if merchant_id and merchant_data:
            merchant_ref = db.collection('merchants').document(merchant_id)
            # Use 'account_balance' instead of 'balance' - this matches your merchant schema
            current_merchant_balance = merchant_data.get('account_balance', 0)
            new_merchant_balance = current_merchant_balance + float(amount)
            print(f"Updating merchant {merchant_id} balance from {current_merchant_balance} to {new_merchant_balance}")
            
            # Update with the correct field name
            merchant_ref.update({"account_balance": new_merchant_balance})
            
            # Verify the update worked
            updated_merchant = merchant_ref.get().to_dict()
            print(f"Verified merchant balance after update: {updated_merchant.get('account_balance')}")
        
        # Record transaction in database
        timestamp = datetime.now().timestamp()
        bank_name = user_data.get('bank', 'HDFC')

        transaction_data = {
            "user_id": user_id,
            "merchant_id": merchant_id if merchant_id else "UNKNOWN",
            "amount": float(amount),
            "timestamp": timestamp,
            "status": "success",
            "transaction_id": transaction_id,
            "bank": bank_name,  # Add bank field for querying
            "type": "payment"   # Add type for consistency
        }

        # Add to transactions collection using transaction_id as document ID for easier lookup
        print(f"Creating transaction record with ID: {transaction_id}")
        db.collection('transactions').document(transaction_id).set(transaction_data)
        print(f"Transaction {transaction_id} recorded in database")

        # Verify transaction was recorded
        tx_check = db.collection('transactions').document(transaction_id).get()
        if tx_check.exists:
            print(f"Verified transaction record exists with data: {tx_check.to_dict()}")
        else:
            print(f"ERROR: Failed to create transaction record!")
        
        # Add to blockchain
        bank_name = user_data.get('bank', 'HDFC')
        blockchain = blockchains.get(bank_name)
        if blockchain:
            block_data = {
                "uid": user_id,
                "mid": merchant_id if merchant_id else "UNKNOWN",
                "amount": float(amount),
                "timestamp": timestamp,
                "transaction_id": transaction_id
            }
            
            print(f"Adding transaction to {bank_name} blockchain: {block_data}")
            
            # Use the updated add_block method
            result = blockchain.add_block(block_data)
            
            print(f"Block created with hash: {result.get('hash', 'unknown')}")
            
            # Create a separate record in blocks collection with transaction_id reference
            block_ref = db.collection('blocks').document(transaction_id)
            block_ref.set({
                "hash": result.get('hash'),
                "previous_hash": result.get('previous_hash'),
                "bank_id": bank_name,
                "uid": user_id,
                "mid": merchant_id if merchant_id else "UNKNOWN",
                "amount": float(amount),
                "timestamp": timestamp,
                "transaction_id": transaction_id
            })
            print(f"Block record created with ID: {transaction_id}")
            
            # Verify block was recorded
            block_check = db.collection('blocks').document(transaction_id).get()
            if block_check.exists:
                print(f"Verified block record exists")
            else:
                print(f"ERROR: Failed to create block record!")
        
        return jsonify({
            "status": "success", 
            "message": "Transaction completed successfully",
            "transaction_id": transaction_id,
            "amount": amount,
            "timestamp": timestamp
        })
        
    except Exception as e:
        print(f"Transaction error: {str(e)}")
        import traceback
        traceback.print_exc()  # Print full stack trace
        return jsonify({
            "status": "failed", 
            "message": f"Transaction processing error: {str(e)}",
            "transaction_id": transaction_id
        })

@app.route('/transactions', methods=['GET'])
def get_transactions():
    bank = request.args.get('bank', 'HDFC')
    
    try:
        print(f"Fetching transactions for bank: {bank}")  # Debug log
        
        # Get transactions directly from the transactions collection first
        transactions = []
        
        # Query the transactions collection
        tx_ref = db.collection('transactions').where('bank', '==', bank).get()
        
        print(f"Found {len(list(tx_ref))} transactions in 'transactions' collection")  # Debug log
        
        for doc in tx_ref:
            tx_data = doc.to_dict()
            print(f"Transaction data: {tx_data}")  # Debug log
            
            # Convert server timestamp to regular timestamp if needed
            timestamp = tx_data.get('timestamp')
            if hasattr(timestamp, 'timestamp'):
                timestamp = timestamp.timestamp()
            elif not timestamp:
                timestamp = 0
                
            transactions.append({
                "index": timestamp,
                "hash": doc.id,  # Use document ID as hash
                "previous_hash": "",
                "data": {
                    "user_id": tx_data.get('user_id', ''),
                    "merchant_id": tx_data.get('merchant_id', ''),
                    "amount": tx_data.get('amount', 0),
                    "timestamp": timestamp
                }
            })
        
        # If no transactions found in transactions collection, try the blocks collection
        if not transactions:
            print("No transactions found in 'transactions' collection, trying 'blocks'...")  # Debug log
            blocks_ref = db.collection('blocks').where('bank_id', '==', bank).get()
            
            for doc in blocks_ref:
                block_data = doc.to_dict()
                
                # Skip genesis block
                if block_data.get('uid') == "GENESIS" and block_data.get('mid') == "GENESIS":
                    continue
                
                timestamp = block_data.get('timestamp', 0)
                if hasattr(timestamp, 'timestamp'):
                    timestamp = timestamp.timestamp()
                    
                transactions.append({
                    "index": timestamp,
                    "hash": block_data.get('hash', ''),
                    "previous_hash": block_data.get('previous_hash', ''),
                    "data": {
                        "user_id": block_data.get('uid', ''),
                        "merchant_id": block_data.get('mid', ''),
                        "amount": block_data.get('amount', 0),
                        "timestamp": timestamp
                    }
                })
                
        # Sort transactions by timestamp (most recent first)
        transactions.sort(key=lambda x: x['data']['timestamp'], reverse=True)
        
        print(f"Returning {len(transactions)} transactions")  # Debug log
        return jsonify({"transactions": transactions})
        
    except Exception as e:
        print(f"Error retrieving transactions: {str(e)}")
        import traceback
        traceback.print_exc()  # Print full stack trace
        return jsonify({"transactions": [], "error": str(e)})

@app.route('/bank_branches', methods=['GET'])
def get_bank_branches():
    branches = {
        "HDFC": ["HDFC0001", "HDFC0002", "HDFC0003"],
        "ICICI": ["ICIC0001", "ICIC0002", "ICIC0003"],
        "SBI": ["SBIN0001", "SBIN0002", "SBIN0003"]
    }
    return jsonify(branches)

@app.route('/validate_branch', methods=['POST'])
def validate_branch():
    """Validate that IFSC code belongs to a supported branch"""
    data = request.json
    ifsc_code = data.get('ifsc_code', '')
    
    # List of valid branches
    valid_branches = {
        "HDFC": ["HDFC0001", "HDFC0002", "HDFC0003"],
        "ICICI": ["ICIC0001", "ICIC0002", "ICIC0003"],
        "SBI": ["SBIN0001", "SBIN0002", "SBIN0003"]
    }
    
    # Check if the IFSC code is valid
    for bank, branches in valid_branches.items():
        if ifsc_code in branches:
            return jsonify({
                "valid": True,
                "bank": bank,
                "message": f"Valid branch of {bank} Bank"
            })
    
    return jsonify({
        "valid": False,
        "message": "Invalid IFSC code. Please choose from the supported branches."
    })

@app.route('/test_connection', methods=['GET'])
def test_connection():
    return jsonify({
        "status": "success",
        "message": "Bank API is working correctly",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# Add this function to decrypt VID to MID
def decrypt_vid_to_mid(vid):
    """Convert VID back to MID using Speck cipher decryption"""
    try:
        print(f"Trying to decrypt VID: {vid}")
        # Initialize with same key used in merchant_api.py
        cipher = SpeckCipher(0x12345678901234567890123456789012)
        
        # Convert VID from hex string to integer
        vid_int = int(vid, 16)
        
        # Decrypt to get MID
        mid_int = cipher.decrypt(vid_int)
        
        # Convert back to hex string and ensure uppercase
        mid = format(mid_int, 'X')
        
        print(f"Successfully decrypted VID to MID: {mid}")
        return mid
    except Exception as e:
        print(f"Error decrypting VID: {str(e)}")
        return None

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Bank API')
    parser.add_argument('--port', type=int, default=5053, help='Port to run the server on')
    args = parser.parse_args()
    
    print(f"Starting bank app on port {args.port}...")
    app.run(host='0.0.0.0', port=args.port, debug=True, use_reloader=False)