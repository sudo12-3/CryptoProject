import socket
import json
import hashlib
import time
import threading
import logging
import requests
import os
import sys
import qrcode
import io
import base64
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("upi_machine.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("UPI_Machine")

# Configuration
HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 5055       # UPI Machine port
BANK_API_URL = 'http://172.20.30.143:5053'  # Your main system's IP and Bank port
HTTP_PORT = 5056  # HTTP API port

# Import SpeckCipher from the Merchant API
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from Merchant.merchant_api import SpeckCipher
    # Initialize the cipher with the same key
    cipher = SpeckCipher(0x12345678901234567890123456789012)
    logger.info("SpeckCipher imported successfully")
except Exception as e:
    logger.error(f"Failed to import SpeckCipher: {str(e)}")
    # Create a fallback cipher in case of import failure
    class FallbackCipher:
        def encrypt(self, data):
            return data
        def decrypt(self, data):
            return data
    cipher = FallbackCipher()
    logger.warning("Using fallback cipher implementation")

# Create Flask app for HTTP endpoints
app = Flask(__name__)
CORS(app)

def encrypt_merchant_id(mid):
    """Encrypt merchant ID to get VMID"""
    try:
        # Convert MID to integer
        mid_int = int(mid, 16)
        # Encrypt using SpeckCipher
        vmid_int = cipher.encrypt(mid_int)
        # Convert back to hex string
        vmid = format(vmid_int, 'X')
        logger.info(f"Encrypted merchant ID {mid} to VMID {vmid}")
        return vmid
    except Exception as e:
        logger.error(f"Error encrypting merchant ID: {str(e)}")
        return None

def decrypt_merchant_id(vmid):
    """Decrypt the merchant ID from the encrypted value (VMID)"""
    try:
        # Convert VMID from hex string to integer
        vmid_int = int(vmid, 16)
        # Decrypt using SpeckCipher
        mid_int = cipher.decrypt(vmid_int)
        # Convert back to hex string
        mid = format(mid_int, 'X')
        logger.info(f"Decrypted VMID {vmid} to merchant ID {mid}")
        return mid
    except Exception as e:
        logger.error(f"Error decrypting VMID: {str(e)}")
        return vmid  # Return original value on failure

@app.route('/generate_qr', methods=['POST'])
def generate_qr():
    """Generate QR code for a merchant ID"""
    data = request.json
    merchant_id = data.get('merchant_id')
    
    if not merchant_id:
        logger.error("Missing merchant_id in request")
        return jsonify({"success": False, "error": "Missing merchant_id"}), 400
    
    try:
        # Encrypt merchant ID to get VMID
        vmid = encrypt_merchant_id(merchant_id)
        if not vmid:
            logger.error(f"Failed to encrypt merchant ID: {merchant_id}")
            return jsonify({"success": False, "error": "Failed to encrypt merchant ID"}), 500
        
        logger.info(f"Generating QR code for VMID: {vmid}")
        
        # Generate QR code with the VMID
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(vmid)
        qr.make(fit=True)
        
        img = qr.make_image(fill="black", back_color="white")
        
        # Convert PIL image to base64 string
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        logger.info(f"QR code generated successfully for VMID: {vmid}")
        
        # Return the QR code as base64 image data
        return jsonify({
            "success": True, 
            "vmid": vmid, 
            "qr_code": img_str
        })
        
    except Exception as e:
        logger.error(f"Error generating QR code: {str(e)}")
        return jsonify({
            "success": False, 
            "error": f"Failed to generate QR code: {str(e)}"
        }), 500

class UPIMachine:
    def __init__(self):
        self.client_connections = {}
        self.transaction_counter = 0
        self.transaction_states = {}
        logger.info("UPI Machine initialized")
    
    def forward_to_bank(self, transaction_data):
        """Forward transaction request to the bank server"""
        try:
            # First log what we're doing
            logger.info(f"Forwarding transaction to bank: {transaction_data}")
            
            # Decrypt merchant ID if needed
            if 'vid' in transaction_data:
                merchant_id = decrypt_merchant_id(transaction_data['vid'])
                if merchant_id:
                    transaction_data['merchant_id'] = merchant_id
                    logger.info(f"Merchant ID decoded: {merchant_id}")
            
            # Forward the request to the bank
            logger.info(f"Sending request to bank at {BANK_API_URL}/verify_transaction")
            response = requests.post(
                f"{BANK_API_URL}/verify_transaction",
                json=transaction_data,
                timeout=60
            )
            
            logger.info(f"Bank response: {response.json()}")
            return response.json()
        except Exception as e:
            logger.error(f"Error forwarding to bank: {str(e)}")
            return {"status": "failed", "message": f"Error communicating with bank: {str(e)}"}
    
    def handle_qr_request(self, merchant_id):
        """Handle QR code generation request from socket client"""
        try:
            # Encrypt merchant ID to get VMID
            vmid = encrypt_merchant_id(merchant_id)
            if not vmid:
                return {"success": False, "error": "Failed to encrypt merchant ID"}
            
            # Generate QR code with the VMID
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(vmid)
            qr.make(fit=True)
            
            img = qr.make_image(fill="black", back_color="white")
            
            # Convert PIL image to base64 string
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            return {
                "success": True, 
                "vmid": vmid, 
                "qr_code": img_str
            }
            
        except Exception as e:
            logger.error(f"Error generating QR code: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def handle_client(self, client_socket, client_address):
        """Handle communication with a connected client"""
        logger.info(f"New connection from {client_address}")
        
        # Generate a unique connection ID
        conn_id = f"{client_address[0]}:{client_address[1]}"
        
        # Store the client socket in our connections dictionary
        self.client_connections[conn_id] = client_socket
        logger.info(f"Client {conn_id} added to connections dictionary")
        
        try:
            client_socket.settimeout(60)  # Add timeout
            while True:
                # Receive data from client
                data = client_socket.recv(4096)
                if not data:
                    logger.info(f"Connection closed by {client_address}")
                    break
                
                # Parse the received data
                message = json.loads(data.decode('utf-8'))
                logger.info(f"Received message from {conn_id}: {message}")
                
                if message.get('type') == 'transaction_request':
                    # Increment transaction counter
                    self.transaction_counter += 1
                    
                    # Process transaction request
                    transaction_data = message.get('data', {})
                    logger.info(f"Processing transaction #{self.transaction_counter}: {transaction_data}")
                    
                    # Forward to bank and get response
                    bank_response = self.forward_to_bank(transaction_data)
                    
                    # Send the response back to the client
                    response = {
                        "type": "transaction_result",
                        "data": bank_response
                    }
                    client_socket.sendall(json.dumps(response).encode('utf-8'))
                    logger.info(f"Response sent to client: {response}")
                
                elif message.get('type') == 'qr_request':
                    # Process QR code request
                    merchant_id = message.get('merchant_id')
                    if merchant_id:
                        logger.info(f"Processing QR code request for merchant: {merchant_id}")
                        qr_response = self.handle_qr_request(merchant_id)
                        
                        # Send back response
                        response = {
                            "type": "qr_response",
                            "data": qr_response
                        }
                        client_socket.sendall(json.dumps(response).encode('utf-8'))
                        logger.info(f"QR code response sent to client: {conn_id}")
                    else:
                        response = {
                            "type": "qr_response",
                            "data": {"success": False, "error": "Missing merchant_id"}
                        }
                        client_socket.sendall(json.dumps(response).encode('utf-8'))
                        logger.error(f"Missing merchant_id in QR request from {conn_id}")
                
                elif message.get('type') == 'test_connection':
                    # Send a simple response for connection testing
                    response = {
                        "type": "connection_test",
                        "data": {
                            "status": "success", 
                            "message": "UPI Machine connection successful",
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                    }
                    client_socket.sendall(json.dumps(response).encode('utf-8'))
                    logger.info("Test connection response sent")
                
        except socket.timeout:
            logger.error(f"Connection timed out for {conn_id}")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON data received from {client_address}")
        except Exception as e:
            logger.error(f"Error handling client {conn_id}: {str(e)}")
        finally:
            self.cleanup_connection(conn_id)
    
    def cleanup_connection(self, conn_id):
        """Clean up client connection"""
        if conn_id in self.client_connections:
            self.client_connections[conn_id].close()
            del self.client_connections[conn_id]
            logger.info(f"Cleaned up connection {conn_id}")
    
    def start_server(self):
        """Start the UPI Machine server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((HOST, PORT))
            server_socket.listen(5)
            logger.info(f"UPI Machine server started on {HOST}:{PORT}")
            logger.info(f"Ready to accept connections. Bank API URL: {BANK_API_URL}")
            
            while True:
                client_socket, client_address = server_socket.accept()
                logger.info(f"Accepted connection from {client_address}")
                
                # Create a new thread to handle the client connection
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
                logger.info(f"Started thread for client {client_address}")
        
        except Exception as e:
            logger.error(f"Server error: {str(e)}")
        finally:
            server_socket.close()
            logger.info("UPI Machine server shut down")

# Start Flask app in a separate thread
def run_flask_app():
    app.run(host='0.0.0.0', port=HTTP_PORT, debug=False)

if __name__ == "__main__":
    print("==== UPI MACHINE SERVER STARTING ====")
    print(f"Bank API URL: {BANK_API_URL}")
    print(f"Socket Server Port: {PORT}")
    print(f"HTTP Server Port: {HTTP_PORT}")
    print("====================================")
    
    # Start the Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info(f"HTTP API server started on port {HTTP_PORT}")
    
    # Start the UPI Machine server
    upi_machine = UPIMachine()
    upi_machine.start_server()