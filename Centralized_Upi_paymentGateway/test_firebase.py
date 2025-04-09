from firebase_config import db

def test_connection():
    try:
        # Try to access a collection
        test_ref = db.collection('test_collection').document('test_document')
        test_ref.set({'test': 'Hello Firebase!'})
        print("✅ Successfully connected to Firebase and wrote data!")
        
        # Read it back
        doc = test_ref.get()
        print(f"Retrieved data: {doc.to_dict()}")
        
        # Clean up
        test_ref.delete()
        print("Test document deleted.")
        
        return True
    except Exception as e:
        print(f"❌ Firebase connection failed: {e}")
        return False

if __name__ == "__main__":
    test_connection()