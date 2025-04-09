import hashlib
import time
from datetime import datetime
from firebase_config import db
from firebase_admin import firestore

class Block:
    def __init__(self, uid, mid, amount, timestamp=None, previous_hash=""):
        self.uid = uid
        self.mid = mid
        self.amount = amount
        self.timestamp = timestamp or time.time()
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()
        
    def calculate_hash(self):
        """Calculate SHA-256 hash of the transaction data."""
        block_data = f"{self.uid}{self.mid}{self.timestamp}{self.amount}{self.previous_hash}"
        return hashlib.sha256(block_data.encode()).hexdigest()

class Blockchain:
    def __init__(self, bank_id):
        self.bank_id = bank_id
        self.chain_ref = db.collection('blockchains').document(bank_id)
        self.initialize_blockchain()
        
    def initialize_blockchain(self):
        """Initialize blockchain if it doesn't exist."""
        doc = self.chain_ref.get()
        
        if not doc.exists:
            # Create genesis block
            genesis_block = Block("GENESIS", "GENESIS", 0)
            self.chain_ref.set({
                'bank_id': self.bank_id,
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_block_hash': genesis_block.hash
            })
            
            # Store genesis block
            self.add_block_to_firestore(genesis_block)
    
    def get_latest_block_hash(self):
        """Get the hash of the latest block in the chain."""
        doc = self.chain_ref.get()
        if doc.exists:
            return doc.to_dict().get('last_block_hash')
        return None
    
    def add_transaction(self, uid, mid, amount):
        """Add a new transaction to the blockchain."""
        last_hash = self.get_latest_block_hash()
        if not last_hash:
            return False
            
        # Create new block
        new_block = Block(uid, mid, amount, previous_hash=last_hash)
        
        # Add block to Firestore
        success = self.add_block_to_firestore(new_block)
        
        if success:
            # Update the last block hash
            self.chain_ref.update({
                'last_block_hash': new_block.hash,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            # Also record the transaction in the transactions collection
            self.record_transaction(uid, mid, amount, new_block.hash)
            
            return True
        return False
    
    def add_block_to_firestore(self, block):
        """Add a block to Firestore."""
        try:
            block_ref = db.collection('blocks').document(block.hash)
            block_ref.set({
                'uid': block.uid,
                'mid': block.mid,
                'amount': block.amount,
                'timestamp': block.timestamp,
                'previous_hash': block.previous_hash,
                'hash': block.hash,
                'bank_id': self.bank_id
            })
            return True
        except Exception as e:
            print(f"Error adding block to Firestore: {e}")
            return False
    
    def record_transaction(self, uid, mid, amount, block_hash):
        """Record transaction in the transactions collection."""
        try:
            transaction_ref = db.collection('transactions').document()
            transaction_ref.set({
                'user_id': uid,
                'merchant_id': mid,
                'amount': amount,
                'block_hash': block_hash,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'type': 'payment',
                'status': 'completed',
                'bank_id': self.bank_id
            })
            return True
        except Exception as e:
            print(f"Error recording transaction: {e}")
            return False
    
    def verify_chain(self):
        """Verify the integrity of the blockchain."""
        blocks_ref = db.collection('blocks').where('bank_id', '==', self.bank_id).order_by('timestamp').get()
        
        previous_hash = ""
        for doc in blocks_ref:
            block_data = doc.to_dict()
            block = Block(
                block_data.get('uid'), 
                block_data.get('mid'), 
                block_data.get('amount'), 
                block_data.get('timestamp'), 
                block_data.get('previous_hash')
            )
            
            # Skip the genesis block
            if block.uid == "GENESIS" and block.mid == "GENESIS":
                previous_hash = block.hash
                continue
            
            # Verify previous hash
            if block.previous_hash != previous_hash:
                return False
            
            # Verify block's hash
            if block.hash != block.calculate_hash():
                return False
            
            previous_hash = block.hash
            
        return True
    
    def add_block(self, data):
        """Add a new block to the blockchain with given transaction data"""
        # Get the latest block for previous hash
        last_block_ref = db.collection('blocks').where('bank_id', '==', self.bank_id).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1).get()
        
        # Default previous hash (for genesis block)
        previous_hash = "0"
        
        # If there's a previous block, get its hash
        for doc in last_block_ref:
            previous_hash = doc.to_dict().get('hash', '0')
            break
        
        # Create timestamp
        timestamp = datetime.now().timestamp()
        
        # Prepare block data
        block_data = {
            'uid': data.get('uid', 'GENESIS'),
            'mid': data.get('mid', 'GENESIS'),
            'amount': data.get('amount', 0),
            'timestamp': timestamp,
            'previous_hash': previous_hash,
            'bank_id': self.bank_id
        }
        
        # Calculate hash for this block
        block_data_string = f"{block_data['uid']}{block_data['mid']}{block_data['amount']}{block_data['timestamp']}{block_data['previous_hash']}{block_data['bank_id']}"
        block_data['hash'] = hashlib.sha256(block_data_string.encode()).hexdigest()
        
        # Save block to Firestore
        db.collection('blocks').add(block_data)
        
        print(f"New block added to {self.bank_id} blockchain with hash: {block_data['hash'][:10]}...")
        
        return block_data