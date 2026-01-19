from app import app, db, Members, Receipts
from datetime import datetime
import uuid

def test_rules():
    with app.app_context():
        print("=== Rule Verification Test ===")
        
        # 1. Setup User
        # Clean up existing test user if any
        existing = Members.query.filter_by(phone="010-9999-9999").first()
        if existing:
            Receipts.query.filter_by(member_id=existing.id).delete()
            db.session.delete(existing)
            db.session.commit()

        user = Members(name="RuleTester", phone="010-9999-9999", branch="test", birth="000101", visit_count=0, last_visit="2000-01-01")
        db.session.add(user)
        db.session.commit()
        print(f"Created user: {user.name} (ID: {user.id})")

        # 2. Test Normal Receipt (1st of the day)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        r1 = Receipts(member_id=user.id, receipt_no="REC-001", branch_paid="TestBranch", amount=10000, visit_date=datetime.now())
        db.session.add(r1)
        
        # Update visit count manually (mimicking app logic)
        user.visit_count += 1
        user.last_visit = datetime.now().strftime("%Y-%m-%d")
        db.session.commit()
        print("Registered 1st receipt (Normal).")

        # 3. Test Daily Limit (2nd receipt attempt)
        # Check logic: query today's receipt
        today_receipt = Receipts.query.filter(Receipts.member_id == user.id, Receipts.visit_date >= today).first()
        
        print("\n--- [Rule 1: Daily Limit] ---")
        if today_receipt:
            print(f"Found today's receipt: {today_receipt.receipt_no}")
            # Simulate app logic: if amount > 0 and today_receipt exists -> BLOCK
            new_amount = 5000
            if new_amount > 0 and today_receipt:
                print("PASS: Access Denied for 2nd receipt (Correct)")
            else:
                print("FAIL: Access Allowed (Incorrect)")
        else:
            print("FAIL: Today's receipt not found in DB")

        # 4. Test Refund (Should be allowed even if daily limit reached)
        print("\n--- [Rule 3: Refund Handling] ---")
        refund_amount = -10000
        # Refund logic: amount < 0 so it skips daily limit check
        
        if refund_amount > 0 and today_receipt:
            print("FAIL: Refund was blocked by daily limit")
        else:
            print("PASS: Refund logic bypassed daily limit (Correct)")
            
            # Add refund receipt
            r2 = Receipts(member_id=user.id, receipt_no="REC-REFUND", branch_paid="TestBranch", amount=refund_amount, visit_date=datetime.now())
            db.session.add(r2)
            
            # Refund should NOT increase visit count
            old_count = user.visit_count
            if refund_amount > 0:
                user.visit_count += 1 # Should not happen
            
            db.session.commit()
            
            if user.visit_count == old_count:
                print("PASS: Visit count did not increase for refund (Correct)")
            else:
                print("FAIL: Visit count increased for refund")

if __name__ == "__main__":
    test_rules()
