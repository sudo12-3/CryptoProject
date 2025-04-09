import hashlib
import time
from firebase_config import db
from firebase_admin import firestore

def generate_uid(user_name, password):
    """Generate a 16-digit User ID (UID) using SHA-256."""
    timestamp = str(int(time.time()))  
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    raw_data = user_name + timestamp + password_hash
    final_hash = hashlib.sha256(raw_data.encode()).hexdigest()
    uid = final_hash[:16].upper()  
    return uid

def register_user(name, password, balance, ifsc_code, pin):
    """Register a new user in Firebase."""
    uid = generate_uid(name, password)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()

    # Insert into Firebase
    user_ref = db.collection('users').document(uid)
    user_data = {
        'name': name,
        'password_hash': password_hash,
        'account_balance': float(balance),
        'ifsc_code': ifsc_code,
        'uid': uid,
        'pin_hash': pin_hash,
        'created_at': firestore.SERVER_TIMESTAMP
    }
    
    user_ref.set(user_data)
    print(f"User '{name}' registered successfully with UID: {uid}")
    return uid

def generate_mmid(uid, mobile_number):
    """Generate MMID (Mobile Money Identifier) for UPI transactions."""
    combined = uid + mobile_number
    mmid_hash = hashlib.sha256(combined.encode()).hexdigest()
    mmid = mmid_hash[:7].upper()  # 7-digit MMID
    
    # Store MMID in Firebase
    mmid_ref = db.collection('mmids').document(mmid)
    mmid_ref.set({
        'uid': uid,
        'mobile_number': mobile_number,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    
    # Update user document with MMID
    user_ref = db.collection('users').document(uid)
    user_ref.update({
        'mmid': mmid,
        'mobile_number': mobile_number
    })
    
    return mmid

def verify_user_pin(mmid, pin):
    """Verify user's PIN for a transaction."""
    # Get UID from MMID
    mmid_ref = db.collection('mmids').document(mmid).get()
    if not mmid_ref.exists:
        return False, "Invalid MMID"
    
    mmid_data = mmid_ref.to_dict()
    uid = mmid_data.get('uid')
    
    # Get user details
    user_ref = db.collection('users').document(uid).get()
    if not user_ref.exists:
        return False, "User not found"
    
    user_data = user_ref.to_dict()
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    
    if pin_hash != user_data.get('pin_hash'):
        return False, "Invalid PIN"
    
    return True, uid

def process_payment(mmid, pin, merchant_vmid, amount):
    """Process a payment from user to merchant."""
    from merchant import encrypt_speck  # Import here to avoid circular imports
    
    # Verify user
    is_valid, user_id = verify_user_pin(mmid, pin)
    if not is_valid:
        return False, user_id  # Error message
    
    # Get merchant ID from VMID
    merchant_id = None
    merchants_ref = db.collection('merchants').get()
    for doc in merchants_ref:
        merchant_data = doc.to_dict()
        mid = merchant_data.get('mid')
        if encrypt_speck(mid) == merchant_vmid:
            merchant_id = mid
            break
    
    if not merchant_id:
        return False, "Invalid merchant QR code"
    
    # Check user balance
    user_ref = db.collection('users').document(user_id)
    user_data = user_ref.get().to_dict()
    user_balance = user_data.get('account_balance', 0)
    
    if user_balance < float(amount):
        return False, "Insufficient balance"
    
    # Get merchant details
    merchant_ref = db.collection('merchants').document(merchant_id)
    merchant_data = merchant_ref.get().to_dict()
    
    # Begin transaction
    transaction = db.transaction()
    
    @firestore.transactional
    def update_balances(transaction, user_ref, merchant_ref, amount):
        # Update user balance
        transaction.update(user_ref, {
            'account_balance': firestore.Increment(-float(amount))
        })
        
        # Update merchant balance
        transaction.update(merchant_ref, {
            'account_balance': firestore.Increment(float(amount))
        })
        
        return True
    
    try:
        success = update_balances(transaction, user_ref, merchant_ref, amount)
        
        if success:
            # Add to blockchain
            from blockchain import Blockchain
            bank_id = user_data.get('ifsc_code')[:4]  # Assuming first 4 chars are bank ID
            blockchain = Blockchain(bank_id)
            blockchain.add_transaction(user_id, merchant_id, float(amount))
            
            return True, "Payment successful"
    except Exception as e:
        return False, f"Transaction failed: {str(e)}"