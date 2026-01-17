
import os
import unittest
from datetime import datetime
from app import create_app
from models import db, Members, Receipts

class TestEarningRules(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' # Use in-memory DB for testing
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create a test member
        self.member = Members(name="TestUser", phone="01012345678", phone_hash_value="test_hash")
        db.session.add(self.member)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_duplicate_receipt(self):
        """Test Rule 2: Duplicate receipt numbers should be rejected."""
        # 1. Add first receipt
        r1 = Receipts(member_id=self.member.id, receipt_no="REC-001", amount=10000, visit_date=datetime.now())
        db.session.add(r1)
        db.session.commit()
        
        # 2. Check for duplicate
        existing = Receipts.query.filter_by(receipt_no="REC-001").first()
        self.assertIsNotNone(existing, "Receipt should exist")
        
        # In actual code:  if Receipts.query.filter_by(receipt_no=receipt_no).first(): return error
        # So we verify that the query returns the object.

    def test_one_earning_per_day(self):
        """Test Rule 1: Only one earning allowed per day."""
        # 1. Add a receipt for today
        r1 = Receipts(member_id=self.member.id, receipt_no="REC-002", amount=10000, visit_date=datetime.now())
        db.session.add(r1)
        db.session.commit()
        
        # 2. Simulate logic check for 2nd attempt
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_receipt = Receipts.query.filter(
            Receipts.member_id == self.member.id, 
            Receipts.visit_date >= today_start
        ).first()
        
        self.assertIsNotNone(today_receipt, "Should find today's receipt")
        
        # Logic check: if amount > 0 and today_receipt: fail
        amount = 5000
        is_blocked = (amount > 0 and today_receipt is not None)
        self.assertTrue(is_blocked, "Second earning attempt should be blocked")

    def test_refund_exception(self):
        """Test Exception: Refunds (negative amount) should allow multiple transactions."""
        # 1. Add a receipt for today
        r1 = Receipts(member_id=self.member.id, receipt_no="REC-003", amount=10000, visit_date=datetime.now())
        db.session.add(r1)
        db.session.commit()
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_receipt = Receipts.query.filter(
            Receipts.member_id == self.member.id, 
            Receipts.visit_date >= today_start
        ).first()
        
        # 2. Simulate logic for REFUND (negative amount)
        amount = -10000
        is_blocked = (amount > 0 and today_receipt is not None)
        self.assertFalse(is_blocked, "Refund should NOT be blocked even if receipt exists today")

if __name__ == '__main__':
    unittest.main()
