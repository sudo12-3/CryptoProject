from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys
import json
from datetime import datetime
import argparse

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import blockchain module
from blockchan import Blockchain

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
    
    # Extract transaction details
    user_id = data.get('user_id')
    merchant_id = data.get('merchant_id')
    amount = data.get('amount')
    pin = data.get('pin')
    mmid = data.get('mmid')
    
    # Verify user credentials
    user_ref = db.collection('users').document(user_id)
    user_data = user_ref.get()
    
    if not user_data.exists:
        return jsonify({"status": "failed", "message": "User not found"})
    
    user_data = user_data.to_dict()
    
    # Verify PIN and MMID
    if user_data.get('pin') != pin or user_data.get('mmid') != mmid:
        return jsonify({"status": "failed", "message": "Invalid PIN or MMID"})
    
    # Check if user has sufficient balance
    if user_data.get('balance', 0) < float(amount):
        return jsonify({"status": "failed", "message": "Insufficient balance"})
    
    # Get merchant details
    merchant_ref = db.collection('merchants').document(merchant_id)
    merchant_data = merchant_ref.get()
    
    if not merchant_data.exists:
        return jsonify({"status": "failed", "message": "Merchant not found"})
    
    merchant_data = merchant_data.to_dict()
    
    # Process transaction
    try:
        # Update user balance
        new_user_balance = user_data.get('balance', 0) - float(amount)
        user_ref.update({"balance": new_user_balance})
        
        # Update merchant balance
        new_merchant_balance = merchant_data.get('balance', 0) + float(amount)
        merchant_ref.update({"balance": new_merchant_balance})
        
        # Record transaction in database
        timestamp = datetime.now().timestamp()
        transaction_data = {
            "user_id": user_id,
            "merchant_id": merchant_id,
            "amount": float(amount),
            "timestamp": timestamp,
            "status": "success"
        }
        
        # Add to transactions collection
        db.collection('transactions').add(transaction_data)
        
        # Add to blockchain
        bank_name = user_data.get('bank', 'HDFC')
        blockchain = blockchains.get(bank_name)
        if blockchain:
            blockchain.add_block({
                "uid": user_id,
                "mid": merchant_id,
                "amount": float(amount),
                "timestamp": timestamp
            })
            print(f"Transaction added to {bank_name} blockchain")
        
        return jsonify({
            "status": "success", 
            "message": "Transaction completed successfully",
            "transaction_data": transaction_data
        })
        
    except Exception as e:
        print(f"Transaction error: {str(e)}")
        return jsonify({"status": "failed", "message": f"Transaction processing error: {str(e)}"})

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

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Bank API')
    parser.add_argument('--port', type=int, default=5053, help='Port to run the server on')
    args = parser.parse_args()
    
    print(f"Starting bank app on port {args.port}...")
    app.run(host='0.0.0.0', port=args.port, debug=True, use_reloader=False)