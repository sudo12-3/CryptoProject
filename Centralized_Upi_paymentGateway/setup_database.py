from firebase_config import db
from firebase_admin import firestore
import hashlib
import time

def setup_database():
    """
    Initialize the database structure and create sample data.
    """
    # Create banks
    banks = [
        {"id": "HDFC", "name": "HDFC Bank", "description": "HDFC Bank Limited"},
        {"id": "ICICI", "name": "ICICI Bank", "description": "ICICI Bank Limited"},
        {"id": "SBI", "name": "State Bank of India", "description": "State Bank of India"}
    ]
    
    for bank in banks:
        bank_ref = db.collection('banks').document(bank["id"])
        bank_ref.set(bank)
        print(f"Added bank: {bank['name']}")
        
        # Create branches for each bank
        for i in range(1, 4):  # 3 branches per bank
            branch_id = f"{bank['id']}000{i}"
            branch_ref = db.collection('branches').document(branch_id)
            branch_ref.set({
                "bank_id": bank["id"],
                "branch_name": f"{bank['name']} Branch {i}",
                "ifsc_code": branch_id,
                "address": f"Sample Address {i}",
                "created_at": firestore.SERVER_TIMESTAMP
            })
            print(f"Added branch: {bank['name']} Branch {i}")
    
    # Initialize blockchain for each bank
    for bank in banks:
        blockchain_ref = db.collection('blockchains').document(bank["id"])
        
        # Check if blockchain already exists
        if not blockchain_ref.get().exists:
            # Create genesis block
            genesis_hash = hashlib.sha256("GENESIS".encode()).hexdigest()
            genesis_block_ref = db.collection('blocks').document(genesis_hash)
            genesis_block_ref.set({
                'uid': "GENESIS",
                'mid': "GENESIS",
                'amount': 0,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'previous_hash': "",
                'hash': genesis_hash,
                'bank_id': bank["id"]
            })
            
            # Initialize blockchain document
            blockchain_ref.set({
                'bank_id': bank["id"],
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_block_hash': genesis_hash
            })
            
            print(f"Initialized blockchain for {bank['name']}")
    
    print("\nDatabase setup completed successfully!")

if __name__ == "__main__":
    setup_database()