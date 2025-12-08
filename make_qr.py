import qrcode
import os

# 1. 저장할 폴더 확인
save_folder = "branch_qrs"
if not os.path.exists(save_folder):
    os.makedirs(save_folder)

# ======================================================
# ★★★ Render 배포 주소 적용 완료! ★★★
# ======================================================
base_url = "https://everest-ocr.onrender.com" 


# 3. 지점 목록 (URL 파라미터용 코드 : 한글 지점명)
branches = {
    "dongdaemun": "동대문점",
    "gmc": "굿모닝시티점",
    "yeongdeungpo": "영등포점",
    "yangjae": "양재점",
    "suwon": "수원영통점",
    "dongtan": "동탄점",
    "lumbini": "룸비니"
}

print(f"--- 실전용 QR코드 생성을 시작합니다 (주소: {base_url}) ---")

for code, name in branches.items():
    # 접속 주소: https://.../start?branch=지점코드
    target_url = f"{base_url}/start?branch={code}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # 파일명 예: qr_동대문점.jpg
    file_name = f"{save_folder}/qr_{name}.jpg"
    img.save(file_name)
    
    print(f"✅ 생성 완료: {name} ({target_url})")

print(f"\n🎉 모든 QR코드가 '{save_folder}' 폴더에 저장되었습니다!")