from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import hashlib
import time
from flask_cors import CORS
import os
import sys
from datetime import datetime
import argparse

# Add the parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use Firebase by default, but support MySQL as a fallback
use_mysql = False
if os.environ.get('USE_FIREBASE_ONLY') != 'True':
    try:
        import mysql.connector
        db_mysql = mysql.connector.connect(
            host="localhost",
            user="root",
            password="your_password",
            database="blockchain_db"
        )
        cursor = db_mysql.cursor()
        use_mysql = True
    except (ImportError, mysql.connector.Error) as e:
        print(f"MySQL error or not available: {e}")
        use_mysql = False

# Make sure firebase is imported
from firebase_config import db
from firebase_admin import firestore

# Add these imports at the top
import sys
import uuid
sys.path.append('..')  # Add parent directory to path
from upi_machine_client import UPIMachineClient
import threading

app = Flask(__name__)
CORS(app)
app.secret_key = "your_secret_key"  # Required for session handling

# Configure Flask to find templates
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
app.template_folder = template_dir

class SpeckCipher(object):
    def encrypt_round(self, x, y, k):
        """Complete one round of enc"""
        rs_x = ((x << (self.word_size - self.alpha_shift)) + (x >> self.alpha_shift)) & self.mod_mask
        add_sxy = (rs_x + y) & self.mod_mask
        new_x = k ^ add_sxy
        ls_y = ((y >> (self.word_size - self.beta_shift)) + (y << self.beta_shift)) & self.mod_mask
        new_y = new_x ^ ls_y
        return new_x, new_y

    def decrypt_round(self, x, y, k):
        """Complete one round of inverse"""
        xor_xy = x ^ y
        new_y = ((xor_xy << (self.word_size - self.beta_shift)) + (xor_xy >> self.beta_shift)) & self.mod_mask
        xor_xk = x ^ k
        msub = ((xor_xk - new_y) + self.mod_mask_sub) % self.mod_mask_sub
        new_x = ((msub >> (self.word_size - self.alpha_shift)) + (msub << self.alpha_shift)) & self.mod_mask
        return new_x, new_y

    def __init__(self, key):
        self.block_size = 64     
        self.key_size = 128      
        self.rounds = 27         
        self.word_size = self.block_size >> 1 
        self.mod_mask = (2 ** self.word_size) - 1
        self.mod_mask_sub = (2 ** self.word_size)
        self.beta_shift = 3
        self.alpha_shift = 8
        try:
            self.key = key & ((2 ** self.key_size) - 1)
        except (ValueError, TypeError):
            raise ValueError("Invalid Key Value! Please provide key as int.")

        # Generate key schedule.
        self.key_schedule = [self.key & self.mod_mask]
        l_schedule = [(self.key >> (x * self.word_size)) & self.mod_mask 
                      for x in range(1, self.key_size // self.word_size)]
        for x in range(self.rounds - 1):
            new_l_k = self.encrypt_round(l_schedule[x], self.key_schedule[x], x)
            l_schedule.append(new_l_k[0])
            self.key_schedule.append(new_l_k[1])

    def encrypt(self, plaintext):
        try:
            b = (plaintext >> self.word_size) & self.mod_mask
            a = plaintext & self.mod_mask
        except TypeError:
            raise ValueError("Invalid plaintext! Please provide plaintext as int.")

        b, a = self.encrypt_function(b, a)
        ciphertext = (b << self.word_size) + a
        return ciphertext

    def decrypt(self, ciphertext):
        # Expect ciphertext as an int.
        try:
            b = (ciphertext >> self.word_size) & self.mod_mask
            a = ciphertext & self.mod_mask
        except TypeError:
            raise ValueError("Invalid ciphertext! Please provide ciphertext as int.")

        b, a = self.decrypt_function(b, a)
        plaintext = (b << self.word_size) + a
        return plaintext

    def encrypt_function(self, upper_word, lower_word):
        x = upper_word
        y = lower_word
        for k in self.key_schedule:
            rs_x = ((x << (self.word_size - self.alpha_shift)) + (x >> self.alpha_shift)) & self.mod_mask
            add_sxy = (rs_x + y) & self.mod_mask
            x = k ^ add_sxy
            ls_y = ((y >> (self.word_size - self.beta_shift)) + (y << self.beta_shift)) & self.mod_mask
            y = x ^ ls_y
        return x, y

    def decrypt_function(self, upper_word, lower_word):
        x = upper_word
        y = lower_word
        for k in reversed(self.key_schedule):
            xor_xy = x ^ y
            y = ((xor_xy << (self.word_size - self.beta_shift)) + (xor_xy >> self.beta_shift)) & self.mod_mask
            xor_xk = x ^ k
            msub = ((xor_xk - y) + self.mod_mask_sub) % self.mod_mask_sub
            x = ((msub >> (self.word_size - self.alpha_shift)) + (msub << self.alpha_shift)) & self.mod_mask
        return x, y

cipher = SpeckCipher(0x12345678901234567890123456789012)

def generate_uid(username, password):
    timestamp = str(int(time.time()))
    raw_string = username + timestamp + password
    uid = hashlib.sha256(raw_string.encode()).hexdigest()[:16]
    return uid.upper()

def generate_mmid(uid, mobile_number):
    mmid = hashlib.sha256((uid + mobile_number).encode()).hexdigest()[:16]
    return mmid.upper()

# Add a global UPI machine client
upi_client = UPIMachineClient("UPI_MACHINE_IP_ADDRESS")  # Replace with actual IP

# Store transaction statuses
transaction_statuses = {}

# Add a function to initialize UPI Machine connection
def init_upi_connection():
    if upi_client.connect():
        app.logger.info("Connected to UPI Machine")
        
        # Register callback for transaction results
        upi_client.register_callback("transaction_result", handle_transaction_result)
    else:
        app.logger.error("Failed to connect to UPI Machine")

# Add a callback handler for transaction results
def handle_transaction_result(message):
    app.logger.info(f"Received transaction result from UPI Machine: {message}")
    result_data = message.get('data', {})
    
    # Update transaction status for retrieval by frontend
    if 'transaction_id' in result_data:
        transaction_id = result_data['transaction_id']
        transaction_statuses[transaction_id] = result_data
        app.logger.info(f"Updated status for transaction {transaction_id}")

@app.route('/')
def home():
    return render_template('user_frontend.html')

@app.route('/homepage')
def homepage():
    if 'username' in session:
        return render_template('user_homepage.html', 
                               username=session['username'],
                               mmid=session.get('mmid', 'Not available'))
    else:
        return redirect(url_for('home'))

@app.route('/register_user', methods=['POST'])
def register_user():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    ifsc_code = data.get('ifsc_code')
    pin = data.get('pin')
    mobile_number = data.get('mobile_number')
    balance = data.get('balance', 0)

    if not all([username, password, ifsc_code, pin, mobile_number]):
        return jsonify({"error": "Missing required fields"}), 400

    # Validate IFSC code with the valid branches
    valid_branches = {
        "HDFC": ["HDFC0001", "HDFC0002", "HDFC0003"],
        "ICICI": ["ICIC0001", "ICIC0002", "ICIC0003"],
        "SBI": ["SBIN0001", "SBIN0002", "SBIN0003"]
    }
    
    bank_name = None
    is_valid_branch = False
    
    for bank, branches in valid_branches.items():
        if ifsc_code in branches:
            bank_name = bank
            is_valid_branch = True
            break
    
    if not is_valid_branch:
        return jsonify({"error": f"Invalid IFSC code: {ifsc_code}. Please choose from the supported branches."}), 400

    uid = generate_uid(username, password)
    mmid = generate_mmid(uid, mobile_number)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()

    if use_mysql:
        sql = """INSERT INTO users (uid, username, ifsc_code, password_hash, pin_hash, mobile_number, mmid, balance, bank) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" 
        values = (uid, username, ifsc_code, password_hash, pin_hash, mobile_number, mmid, balance, bank_name)

        try:
            cursor.execute(sql, values)
            db_mysql.commit()
            return jsonify({"message": "User registered successfully!", "UID": uid, "MMID": mmid, "bank": bank_name})
        except mysql.connector.Error as err:
            return jsonify({"error": str(err)}), 500
    else:
        try:
            # Add user to Firebase
            user_ref = db.collection('users').document(uid)
            user_data = {
                'username': username,
                'password_hash': password_hash,
                'ifsc_code': ifsc_code,
                'bank': bank_name,  # Store bank name based on IFSC
                'pin_hash': pin_hash,
                'mobile_number': mobile_number,
                'mmid': mmid,
                'balance': float(balance),
                'uid': uid,
                'created_at': firestore.SERVER_TIMESTAMP
            }
            user_ref.set(user_data)
            return jsonify({"message": "User registered successfully!", "UID": uid, "MMID": mmid, "bank": bank_name})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route('/user_login', methods=['POST'])
def user_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not all([username, password]):
        return jsonify({"error": "Missing username or password"}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if use_mysql:
        sql = "SELECT uid, mmid FROM users WHERE username = %s AND password_hash = %s"
        cursor.execute(sql, (username, password_hash))
        result = cursor.fetchone()

        if result:
            session['username'] = username
            session['uid'] = result[0]
            session['mmid'] = result[1]  # Store MMID in session
            return jsonify({"success": True, "message": "Login successful!", "uid": result[0], "mmid": result[1]})
        else:
            return jsonify({"error": "Invalid credentials"}), 401
    else:
        users_ref = db.collection('users')
        query = users_ref.where('username', '==', username).where('password_hash', '==', password_hash).limit(1).get()
        
        result = list(query)
        if result:
            user_data = result[0].to_dict()
            uid = user_data.get('uid')
            mmid = user_data.get('mmid')
            session['username'] = username
            session['uid'] = uid
            session['mmid'] = mmid  # Store MMID in session
            return jsonify({"success": True, "message": "Login successful!", "uid": uid, "mmid": mmid})
        else:
            return jsonify({"error": "Invalid credentials"}), 401

@app.route("/check_balance", methods=["GET"])
def check_balance():
    print("Session Data:", session)  # Debug session storage
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_name = session["username"]
    
    if use_mysql:
        sql = "SELECT balance FROM users WHERE username = %s"
        cursor.execute(sql, (user_name,))
        result = cursor.fetchone()

        if result:
            print(f"Fetched balance: {result[0]}")  # Debug output
            return jsonify({"balance": result[0]})
        else:
            print("User not found in database!")
            return jsonify({"error": "User not found"}), 404
    else:
        users_ref = db.collection('users')
        query = users_ref.where('username', '==', user_name).limit(1).get()
        
        result = list(query)
        if result:
            user_data = result[0].to_dict()
            balance = user_data.get('balance', 0)
            return jsonify({"balance": balance})
        else:
            return jsonify({"error": "User not found"}), 404

@app.route('/make_payment', methods=['GET'])
def show_payment_page():
    if 'username' in session:
        return render_template('payment.html', mmid=session.get('mmid', 'Not available'))
    else:
        return redirect(url_for('home'))

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    mmid = data.get('receiver_mmid')
    amount = data.get('amount')
    pin = data.get('pin')
    vid = data.get('vid')
    
    if not all([mmid, amount, pin, vid]):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Generate a transaction ID
    transaction_id = str(uuid.uuid4())
    
    # Prepare transaction data
    transaction_data = {
        'mmid': mmid,
        'amount': amount,
        'pin': pin,
        'vid': vid,
        'transaction_id': transaction_id
    }
    
    # Send transaction to UPI Machine
    try:
        success, result = upi_client.process_transaction(transaction_data)
        
        if success:
            # Store the transaction ID manually
            transaction_statuses[transaction_id] = {"status": "processing", "message": "Payment request sent to UPI Machine"}
            
            return jsonify({
                "status": "processing",
                "message": "Payment request sent to UPI Machine",
                "transaction_id": transaction_id
            })
        else:
            return jsonify({
                "status": "failed",
                "message": f"Failed to send payment to UPI Machine: {result}"
            }), 500
    except Exception as e:
        app.logger.error(f"Error processing payment: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/check_transaction_status/<transaction_id>', methods=['GET'])
def check_transaction_status(transaction_id):
    """Check the status of a transaction by its ID"""
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    status = transaction_statuses.get(transaction_id, {"status": "unknown", "message": "Transaction not found"})
    return jsonify(status)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='User API')
    parser.add_argument('--port', type=int, default=5052, help='Port to run the server on')
    parser.add_argument('--upi-host', type=str, default='localhost')
    args = parser.parse_args()
    
    # Update UPI Machine host
    upi_client.host = args.upi_host
    
    # Start UPI connection in background thread
    threading.Thread(target=init_upi_connection, daemon=True).start()
    
    print(f"Starting user app on port {args.port}...")
    app.run(host='0.0.0.0', port=args.port, debug=True, use_reloader=False)
