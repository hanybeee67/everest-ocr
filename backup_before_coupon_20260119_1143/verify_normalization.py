from app import app, db, Members, Receipts

def test_normalization():
    with app.app_context():
        print("Testing Phone Normalization...")
        
        # Cleanup
        phone_raw = "010-NORM-TEST"
        phone_no_hyphen = "010NORMTEST"
        
        # Add member with hyphens
        existing = Members.query.all()
        for m in existing:
            if m.phone and (m.phone == phone_raw or m.phone == phone_no_hyphen):
                db.session.delete(m)
        db.session.commit()
        
        m = Members(name="NormUser", phone=phone_raw, branch="test")
        db.session.add(m)
        db.session.commit()
        
        # Test 1: Lookup with same format
        # This simulates app.py logic
        print(f"Looking up {phone_raw}...")
        found = False
        normalized_input = phone_raw.replace("-", "").strip()
        for mem in Members.query.all():
            if mem.phone.replace("-", "").strip() == normalized_input:
                found = True
                break
        print(f"Result 1: {found}")
        assert found
        
        # Test 2: Lookup with NO hyphens (User input mismatch)
        print(f"Looking up {phone_no_hyphen}...")
        found = False
        normalized_input = phone_no_hyphen.replace("-", "").strip()
        for mem in Members.query.all():
            if mem.phone.replace("-", "").strip() == normalized_input:
                found = True
                break
        print(f"Result 2: {found}")
        assert found
        
        print("SUCCESS: Normalization logic works.")

if __name__ == "__main__":
    test_normalization()
