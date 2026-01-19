
# [New Routes for Receipt Management]

@admin_bp.route("/receipt/<int:receipt_id>/update", methods=["POST"])
def update_receipt(receipt_id):
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")
        
    receipt = Receipts.query.get(receipt_id)
    if receipt:
        new_amount = int(request.form.get("amount", 0))
        receipt.amount = new_amount
        db.session.commit()
    
    return redirect(f"/admin_8848/member/{receipt.member_id}/edit")

@admin_bp.route("/receipt/<int:receipt_id>/delete", methods=["POST"])
def delete_receipt(receipt_id):
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")
        
    receipt = Receipts.query.get(receipt_id)
    if receipt:
        member_id = receipt.member_id
        member = Members.query.get(member_id)
        
        db.session.delete(receipt)
        
        # 방문 횟수 차감 (단, 0 이하로는 안 내려가게)
        if member.visit_count > 0:
            member.visit_count -= 1
            
        db.session.commit()
        return redirect(f"/admin_8848/member/{member_id}/edit")
        
    return redirect("/admin_8848/members")
