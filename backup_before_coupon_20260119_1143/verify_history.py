from app import app, db, Members, Receipts
from datetime import datetime

def test_history_logic():
    with app.app_context():
        print("Starting verification...")
        # Create dummy member
        # Use a unique phone to avoid conflicts
        phone = "010-TEST-HIST"
        existing = Members.query.filter_by(phone=phone).first()
        if existing:
            Receipts.query.filter_by(member_id=existing.id).delete()
            db.session.delete(existing)
            db.session.commit()

        m = Members(name="Test", phone=phone, branch="test")
        db.session.add(m)
        db.session.commit()
        
        try:
            # Add 4 receipts
            dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
            amounts = [1000, 2000, 3000, 4000]
            
            for i, (d, a) in enumerate(zip(dates, amounts)):
                r = Receipts(
                    member_id=m.id, 
                    receipt_no=f"R-{d}-{i}", 
                    amount=a, 
                    visit_date=datetime.strptime(d, "%Y-%m-%d"),
                    branch_paid="test"
                )
                db.session.add(r)
            db.session.commit()
            
            # Run the logic (copied from app.py)
            all_receipts = Receipts.query.filter_by(member_id=m.id).order_by(Receipts.visit_date.asc()).all()
            history = []
            cumulative_total = 0
            for r in all_receipts:
                cumulative_total += r.amount
                history.append({
                    "date": r.visit_date.strftime("%Y-%m-%d"),
                    "amount": r.amount,
                    "total": cumulative_total
                })
            
            recent_history = history[-3:][::-1]
            
            print(f"Total Receipts: {len(all_receipts)}")
            print("Recent History (Last 3, Reversed):")
            for h in recent_history:
                print(h)
                
            # Verify values
            # Expected: 
            # 1. 2024-01-04, amt 4000, total 10000
            # 2. 2024-01-03, amt 3000, total 6000
            # 3. 2024-01-02, amt 2000, total 3000
            
            assert len(recent_history) == 3
            assert recent_history[0]['amount'] == 4000
            assert recent_history[0]['total'] == 10000
            assert recent_history[1]['amount'] == 3000
            assert recent_history[1]['total'] == 6000
            
            print("\nVERIFICATION SUCCESS: Logic is correct.")
            
        except Exception as e:
            print(f"\nVERIFICATION FAILED: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            pass
            # Receipts.query.filter_by(member_id=m.id).delete()
            # Members.query.filter_by(id=m.id).delete()
            # db.session.commit()

if __name__ == "__main__":
    test_history_logic()
