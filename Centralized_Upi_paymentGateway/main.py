from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import os
import sys
from flask_cors import CORS

# Add necessary modules from the project
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set environment variable to disable MySQL
os.environ['USE_FIREBASE_ONLY'] = 'True'

# Import the blockchain module
from blockchan import Blockchain

# Create main application
app = Flask(__name__)
CORS(app)
app.secret_key = "centralized_upi_main_app"
app.template_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/merchant')
def merchant_redirect():
    return redirect('http://127.0.0.1:5001/')

@app.route('/user')
def user_redirect():
    return redirect('http://127.0.0.1:5003/')

if __name__ == '__main__':
    # Initialize blockchains for each bank
    banks = ["HDFC", "ICICI", "SBI"]
    for bank in banks:
        blockchain = Blockchain(bank)
        print(f"Blockchain initialized for {bank}")
    
    # Start services separately rather than importing them
    import subprocess
    import threading
    
    def run_merchant_app():
        try:
            subprocess.run([sys.executable, 'Merchant/merchant_api.py'], 
                          cwd=os.path.dirname(os.path.abspath(__file__)))
        except Exception as e:
            print(f"Error running merchant app: {e}")
    
    def run_user_app():
        try:
            subprocess.run([sys.executable, 'User/user_api.py'], 
                          cwd=os.path.dirname(os.path.abspath(__file__)))
        except Exception as e:
            print(f"Error running user app: {e}")
    
    def run_bank_app():
        try:
            subprocess.run([sys.executable, 'Bank/bank_api.py'], 
                          cwd=os.path.dirname(os.path.abspath(__file__)))
        except Exception as e:
            print(f"Error running bank app: {e}")
    
    # Start the apps in separate threads
    merchant_thread = threading.Thread(target=run_merchant_app)
    user_thread = threading.Thread(target=run_user_app)
    bank_thread = threading.Thread(target=run_bank_app)
    
    merchant_thread.daemon = True
    user_thread.daemon = True
    bank_thread.daemon = True
    
    merchant_thread.start()
    user_thread.start()
    bank_thread.start()
    
    print("Starting merchant app on port 5001...")
    print("Starting user app on port 5003...")
    print("Starting bank app on port 5008...")
    print("Starting main app on port 5000...")
    
    # Run the main app
    app.run(host='0.0.0.0', port=5000, debug=True)