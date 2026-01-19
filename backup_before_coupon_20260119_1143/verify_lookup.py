from app import app, db, Members, Receipts, encrypt_data
from datetime import datetime

def test_lookup_and_count():
    with app.app_context():
        print("Starting lookup verification...")
        
        # Setup specific member
        phone = "010-9999-8888"
        
        # Cleanup
        all_m = Members.query.all()
        for m in all_m:
            if m.phone == phone:
                Receipts.query.filter_by(member_id=m.id).delete()
                db.session.delete(m)
        db.session.commit()

        # Create
        m = Members(name="LookupTest", phone=phone, branch="test", visit_count=5)
        # Note: visit_count manually set to 5
        db.session.add(m)
        db.session.commit()
        
        # Verify 1: Phone Lookup
        print(f"Searching for phone: {phone}")
        # Logic from app.py
        all_members = Members.query.all()
        found_member = None
        for mem in all_members:
            if mem.phone == phone:
                found_member = mem
                break
        
        if found_member:
            print(f"SUCCESS: Found member ID {found_member.id}")
            print(f"Decrypted Name: {found_member.name}")
        else:
            print("FAILURE: Could not find member by phone")
            
        # Verify 2: Visit Count
        if found_member:
             print(f"Visit Count: {found_member.visit_count}")
             assert found_member.visit_count == 5
             print("SUCCESS: Visit count matches")

if __name__ == "__main__":
    test_lookup_and_count()
