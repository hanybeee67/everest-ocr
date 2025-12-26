
import sqlite3
from app import app, db, Members, encrypt_data, decrypt_data

def test_encryption():
    print("=== Testing Encryption ===")
    # 1. Check Raw DB (Should be encrypted)
    conn = sqlite3.connect('instance/members.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, phone FROM members LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        raw_name, raw_phone = row
        print(f"Raw DB Name: {raw_name}")
        print(f"Raw DB Phone: {raw_phone}")
        
        # Check if it looks like Fernet token (starts with gAAAA...)
        if raw_name.startswith("gAAAA") and raw_phone.startswith("gAAAA"):
            print("PASS: Data is encrypted in DB")
        else:
            print("FAIL: Data is NOT encrypted in DB")
    else:
        print("SKIP: No members in DB")

    # 2. Check ORM Access (Should be decrypted)
    with app.app_context():
        member = Members.query.first()
        if member:
            print(f"ORM Name: {member.name}")
            print(f"ORM Phone: {member.phone}")
            
            if not member.name.startswith("gAAAA"):
                print("PASS: partial decryption working (or plaintext)")
            
            # Verify full cycle
            original_name = member.name
            member.name = "테스트변경"
            db.session.commit()
            
            # Check DB again
            conn = sqlite3.connect('instance/members.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM members WHERE id=?", (member.id,))
            new_raw_name = cursor.fetchone()[0]
            conn.close()
            
            print(f"New Raw Name: {new_raw_name}")
            if new_raw_name != "테스트변경" and new_raw_name.startswith("gAAAA"):
                 print("PASS: Update encrypted successfully")
            else:
                 print("FAIL: Update failed to encrypt")
                 
            # Restore
            member.name = original_name
            db.session.commit()

if __name__ == "__main__":
    test_encryption()
