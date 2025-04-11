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

# Define new ports for each service
MAIN_PORT = 5050
MERCHANT_PORT = 5051
USER_PORT = 5052
BANK_PORT = 5053

# Add UPI Machine configuration
UPI_MACHINE_HOST = "172.20.31.42"  # Replace with actual IP

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/merchant')
def merchant_redirect():
    return redirect(f'http://127.0.0.1:{MERCHANT_PORT}/')

@app.route('/user')
def user_redirect():
    return redirect(f'http://127.0.0.1:{USER_PORT}/')

@app.route('/bank')
def bank_redirect():
    return redirect(f'http://127.0.0.1:{BANK_PORT}/')

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
        print(f"Starting merchant app on port {MERCHANT_PORT}...")
        subprocess.Popen([sys.executable, 'Merchant/merchant_api.py', '--port', str(MERCHANT_PORT)], 
                       cwd=os.path.dirname(os.path.abspath(__file__)))

    def run_user_app():
        print(f"Starting user app on port {USER_PORT}...")
        subprocess.Popen([
            sys.executable, 
            'User/user_api.py', 
            '--port', str(USER_PORT),
            '--upi-host', UPI_MACHINE_HOST
        ], cwd=os.path.dirname(os.path.abspath(__file__)))

    def run_bank_app():
        print(f"Starting bank app on port {BANK_PORT}...")
        subprocess.Popen([sys.executable, 'Bank/bank_api.py', '--port', str(BANK_PORT)], 
                       cwd=os.path.dirname(os.path.abspath(__file__)))
    
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
    
    print(f"Starting main app on port {MAIN_PORT}...")
    
    # Run the main app - DISABLE use_reloader for stability
    app.run(host='0.0.0.0', port=MAIN_PORT, debug=True, use_reloader=False)