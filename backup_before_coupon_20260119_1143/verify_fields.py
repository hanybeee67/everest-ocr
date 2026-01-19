from app import app, db, Members

def test_new_fields():
    with app.app_context():
        print("Testing Gender/AgeGroup fields...")
        
        # Cleanup
        phone = "010-NEW-FIELD"
        existing = Members.query.all()
        for m in existing:
            if m.phone == phone: # Assuming normalized in app logic, but here accessing property
                db.session.delete(m)
        db.session.commit()
        
        # Create
        m = Members(
            name="FieldTest", 
            phone=phone, 
            branch="test", 
            gender="남성", 
            age_group="30대"
        )
        db.session.add(m)
        db.session.commit()
        
        # Verify
        found = False
        all_members = Members.query.all()
        for mem in all_members:
             # Normalized check manually just to be sure we find it
             if mem.phone == phone:
                 found = True
                 print(f"Found Member: {mem.name}")
                 print(f"Gender: {mem.gender}")
                 print(f"Age Group: {mem.age_group}")
                 
                 assert mem.gender == "남성"
                 assert mem.age_group == "30대"
                 break
        
        if found:
            print("SUCCESS: Fields saved and retrieved correctly.")
        else:
            print("FAILURE: Member not found.")

if __name__ == "__main__":
    test_new_fields()
