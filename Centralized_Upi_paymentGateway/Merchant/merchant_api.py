from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import hashlib
import time
import base64
import qrcode
from flask_cors import CORS
from io import BytesIO
import os
import sys

# Add the parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firebase_config import db
from firebase_admin import firestore

app = Flask(__name__)
CORS(app) 
app.secret_key = 'super_secret_key'  # Needed for session handling

# Configure Flask to find templates and static files
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
app.template_folder = template_dir
app.static_folder = os.path.join(template_dir, 'static')

# Speck Cipher Implementation
class SpeckCipher:
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

def generate_qr(vmid):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(vmid)
    qr.make(fit=True)

    img = qr.make_image(fill="black", back_color="white")

    # Ensure the 'static' folder exists
    static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    if not os.path.exists(static_folder):
        os.makedirs(static_folder)

    qr_path = os.path.join(static_folder, "qr_code.png")
    img.save(qr_path)

    print("QR Code saved as static/qr_code.png")
    return "qr_code.png"
    
def generate_mid(merchant_name, password):
    timestamp = str(int(time.time()))  
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    raw_data = merchant_name + timestamp + password_hash
    final_hash = hashlib.sha256(raw_data.encode()).hexdigest()
    mid = final_hash[:16].upper()  
    return mid

def encrypt_speck(mid):
    """Encrypt MID using SpeckCipher."""
    mid_int = int(mid, 16)  
    vmid_int = cipher.encrypt(mid_int)  
    return hex(vmid_int)[2:].upper()  

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/homepage")
def homepage():
    if 'name' in session:
        user_name = session['name']
        return render_template("a.html", name=user_name)  
    else:
        return redirect(url_for("home"))  

@app.route('/login', methods=['POST'])
def login():
    print("Login API Called") 
    data = request.json
    print("Received Data:", data)

    if not data:
        return jsonify({"error": "No data received"}), 400

    name = data.get('name')
    password = data.get('password')

    if not all([name, password]):
        return jsonify({"error": "Missing username or password"}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    # Query Firestore for the merchant
    merchants_ref = db.collection('merchants')
    query = merchants_ref.where('name', '==', name).where('password_hash', '==', password_hash).limit(1).get()
    
    result = list(query)
    if result:
        merchant_data = result[0].to_dict()
        mid = merchant_data.get('mid')
        session['name'] = name
        session['mid'] = mid

        print("Login Successful")
        return jsonify({
            "success": True, 
            "message": "Login successful!", 
            "redirect_url": "/homepage",
        }), 200
    else:
        print("Invalid Credentials")
        return jsonify({"error": "Invalid credentials"}), 401

@app.route("/qr_page", methods=["GET"])
def generate_qr_code():
    if "name" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    merchant_name = session["name"]
    
    # Query Firestore for the merchant
    merchants_ref = db.collection('merchants')
    query = merchants_ref.where('name', '==', merchant_name).limit(1).get()
    
    result = list(query)
    
    if result:
        merchant_data = result[0].to_dict()
        mid = merchant_data.get('mid')
        vmid = encrypt_speck(mid)
    else:
        return jsonify({"error": "Merchant not found"}), 404
    
    qr_path = generate_qr(vmid)
    return render_template("qr_code.html")

@app.route("/check_balance", methods=["GET"])
def check_balance():
    if "name" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    merchant_name = session["name"]
    
    # Query Firestore for the merchant
    merchants_ref = db.collection('merchants')
    query = merchants_ref.where('name', '==', merchant_name).limit(1).get()
    
    result = list(query)
    if result:
        merchant_data = result[0].to_dict()
        balance = merchant_data.get('account_balance', 0)
        return jsonify({"balance": balance})
    else:
        return jsonify({"error": "Merchant not found"}), 404

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()  
    return jsonify({"message": "Logged out successfully"}), 200

@app.route('/register_merchant', methods=['POST'])
def register_merchant():
    data = request.json
    name = data.get('name')
    password = data.get('password')
    balance = data.get('balance')
    ifsc_code = data.get('ifsc_code')

    if not all([name, password, balance, ifsc_code]):
        return jsonify({"error": "Missing data"}), 400

    mid = generate_mid(name, password)
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    try:
        # Add merchant to Firestore
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
        return jsonify({"message": f"Merchant '{name}' registered successfully!", "MID": mid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/show_transactions', methods=['GET'])
def show_transactions():
    if "name" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    merchant_name = session["name"]
    
    # First, get the merchant's MID
    merchants_ref = db.collection('merchants')
    merchant_query = merchants_ref.where('name', '==', merchant_name).limit(1).get()
    
    merchant_result = list(merchant_query)
    if not merchant_result:
        return jsonify({"error": "Merchant not found"}), 404
    
    merchant_data = merchant_result[0].to_dict()
    mid = merchant_data.get('mid')
    
    # Get transactions for this merchant
    transactions_ref = db.collection('transactions')
    query = transactions_ref.where('merchant_id', '==', mid).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10).get()
    
    transactions = []
    for doc in query:
        transaction = doc.to_dict()
        transactions.append({
            "id": doc.id,
            "amount": transaction.get('amount', 0),
            "type": transaction.get('type', 'unknown'),
            "date": transaction.get('timestamp', firestore.SERVER_TIMESTAMP).strftime('%Y-%m-%d %H:%M:%S') if hasattr(transaction.get('timestamp'), 'strftime') else str(transaction.get('timestamp'))
        })
    
    return jsonify({"transactions": transactions})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)