
from flask import Blueprint, render_template, request, jsonify
from services.coupon_service import redeem_coupon_service
from config import BRANCH_MAP

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')

@staff_bp.route("/redeem", methods=["GET", "POST"])
def redeem():
    if request.method == "POST":
        coupon_code = request.form.get("coupon_code")
        staff_pin = request.form.get("staff_pin")
        branch_code = request.form.get("branch_code")
        
        if not all([coupon_code, staff_pin, branch_code]):
            return render_template("staff_redeem.html", branches=BRANCH_MAP, message="모든 정보를 입력해주세요.", success=False)
            
        result = redeem_coupon_service(coupon_code, staff_pin, branch_code)
        
        return render_template("staff_redeem.html", 
                               branches=BRANCH_MAP, 
                               message=result["message"], 
                               success=result["success"],
                               last_coupon=coupon_code if result["success"] else None)
                               
    return render_template("staff_redeem.html", branches=BRANCH_MAP)
