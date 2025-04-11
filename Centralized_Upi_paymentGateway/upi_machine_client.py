import socket
import json
import time
import threading
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("UPI_Client")

class UPIMachineClient:
    def __init__(self, host, port=5055):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.callback_handlers = {}
        self.lock = threading.Lock()
        
    def connect(self):
        """Connect to the UPI Machine server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # Start a thread to handle incoming messages
            listener_thread = threading.Thread(target=self._listen_for_messages)
            listener_thread.daemon = True
            listener_thread.start()
            
            logger.info(f"Connected to UPI Machine at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to UPI Machine: {str(e)}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the UPI Machine server"""
        if self.connected and self.socket:
            try:
                self.socket.close()
                self.connected = False
                logger.info("Disconnected from UPI Machine")
            except Exception as e:
                logger.error(f"Error disconnecting from UPI Machine: {str(e)}")
    
    def send_message(self, message_type, data):
        """Send a message to the UPI Machine server"""
        if not self.connected:
            if not self.connect():
                return False, "Not connected to UPI Machine"
        
        message = {
            "type": message_type,
            "data": data
        }
        
        try:
            with self.lock:
                self.socket.sendall(json.dumps(message).encode('utf-8'))
            logger.info(f"Sent {message_type} to UPI Machine")
            return True, "Message sent"
        except Exception as e:
            logger.error(f"Error sending message to UPI Machine: {str(e)}")
            # Try reconnecting
            self.connected = False
            return False, str(e)
    
    def register_callback(self, message_type, callback):
        """Register a callback to handle specific message types"""
        self.callback_handlers[message_type] = callback
    
    def test_connection(self):
        """Test connection to the UPI Machine"""
        success, result = self.send_message("test_connection", {})
        return success
    
    def process_transaction(self, transaction_data):
        """Send a transaction request to the UPI Machine"""
        return self.send_message("transaction_request", transaction_data)
    
    def register_merchant(self, merchant_id):
        """Register this client as a merchant with the UPI Machine"""
        return self.send_message("merchant_registration", {"merchant_id": merchant_id})
    
    def _listen_for_messages(self):
        """Listen for messages from the UPI Machine server"""
        while self.connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    logger.warning("Connection to UPI Machine closed")
                    self.connected = False
                    break
                
                # Parse the message
                message = json.loads(data.decode('utf-8'))
                logger.info(f"Received message from UPI Machine: {message.get('type', 'unknown')}")
                
                # Handle message by type
                message_type = message.get('type')
                if message_type in self.callback_handlers:
                    self.callback_handlers[message_type](message)
                
            except json.JSONDecodeError:
                logger.error("Received invalid JSON data from UPI Machine")
            except Exception as e:
                logger.error(f"Error receiving message from UPI Machine: {str(e)}")
                self.connected = False
                break
        
        # Try to reconnect if disconnected unexpectedly
        if not self.connected:
            logger.info("Attempting to reconnect to UPI Machine...")
            time.sleep(5)  # Wait before reconnecting
            self.connect()