from app import app, db, Members, Receipts, Coupons
import os

def reproduction_test():
    with app.app_context():
        print("=== Reproduction Test Start ===")
        # 1. Setup: Clean DB and add 2 members
        db.create_all()
        # Clean specific test members if needed, or just add new ones to be safe
        # But to be safe for user's existing data, let's just add new ones and assume existing data is fine.
        # However, to test the "wiping" issue, we need to correct verify counts.
        
        initial_count = Members.query.count()
        print(f"Initial Member Count: {initial_count}")
        
        m1 = Members(name="TestUser1", phone="010-0000-0001", branch="test", birth="000101")
        m2 = Members(name="TestUser2", phone="010-0000-0002", branch="test", birth="000102")
        db.session.add(m1)
        db.session.add(m2)
        db.session.commit()
        
        updated_count = Members.query.count()
        print(f"Count after adding 2 members: {updated_count}")
        
        if updated_count != initial_count + 2:
            print("ERROR: Failed to add members.")
            return

        print(f"Deleting user {m1.name} (ID: {m1.id})...")
        
        # Reproduce the exact logic from existing code
        # Receipts.query.filter_by(member_id=id).delete()
        # Coupons.query.filter_by(member_id=id).delete()
        # db.session.delete(member)
        
        member_to_delete = Members.query.get(m1.id)
        if member_to_delete:
            Receipts.query.filter_by(member_id=m1.id).delete()
            Coupons.query.filter_by(member_id=m1.id).delete()
            db.session.delete(member_to_delete)
            db.session.commit()
        
        final_count = Members.query.count()
        print(f"Final Member Count: {final_count}")
        
        remaining_member = Members.query.get(m2.id)
        if remaining_member:
             print(f"Remaining member found: {remaining_member.name}")
        else:
             print("ERROR: Remaining member ALSO disappeared!")

        if final_count == updated_count - 1:
            print("PASS: Only 1 member deleted.")
        else:
            print(f"FAIL: Expected {updated_count - 1} members, found {final_count}.")

if __name__ == "__main__":
    reproduction_test()
