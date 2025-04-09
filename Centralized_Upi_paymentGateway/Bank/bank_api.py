from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys
import json
from datetime import datetime

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
            blockchain.add_block(transaction_data)
        
        return jsonify({
            "status": "success", 
            "message": "Transaction completed successfully",
            "transaction_data": transaction_data
        })
        
    except Exception as e:
        return jsonify({"status": "failed", "message": f"Transaction processing error: {str(e)}"})

@app.route('/transactions', methods=['GET'])
def get_transactions():
    bank = request.args.get('bank', 'HDFC')
    
    # Get transactions from blockchain for specific bank
    blockchain = blockchains.get(bank)
    if not blockchain:
        return jsonify({"status": "failed", "message": f"Bank {bank} not found"})
    
    chain = blockchain.chain
    return jsonify({"transactions": chain})

@app.route('/bank_branches', methods=['GET'])
def get_bank_branches():
    branches = {
        "HDFC": ["HDFC0001", "HDFC0002", "HDFC0003"],
        "ICICI": ["ICIC0001", "ICIC0002", "ICIC0003"],
        "SBI": ["SBIN0001", "SBIN0002", "SBIN0003"]
    }
    return jsonify(branches)

if __name__ == '__main__':
    print("Starting bank app on port 5008...")
    app.run(host='0.0.0.0', port=5008, debug=True, use_reloader=False)