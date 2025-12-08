import qrcode
import os

# 1. QR코드를 저장할 폴더 생성
save_folder = "branch_qrs"
if not os.path.exists(save_folder):
    os.makedirs(save_folder)

# 2. 기본 도메인 주소 (나중에 Render 배포 후에는 이 주소를 바꿔야 합니다!)
# 예: base_url = "https://everest-mp.onrender.com"
base_url = "http://127.0.0.1:5000" 

# 3. 지점 목록 (app.py와 동일하게 맞춤)
branches = {
    "dongdaemun": "동대문점",
    "gmc": "굿모닝시티점",
    "yeongdeungpo": "영등포점",
    "yangjae": "양재점",
    "suwon": "수원영통점",
    "dongtan": "동탄점",
    "lumbini": "룸비니"
}

print(f"--- QR코드 생성을 시작합니다 (주소: {base_url}) ---")

# 4. 반복문으로 QR 생성
for code, name in branches.items():
    # 실제 접속할 주소 조합
    target_url = f"{base_url}/start?branch={code}"
    
    # QR 생성
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H, # 손상 복구율 높음
        box_size=10,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    # 이미지로 변환 및 저장
    img = qr.make_image(fill_color="black", back_color="white")
    
    file_name = f"{save_folder}/qr_{name}_{code}.jpg"
    img.save(file_name)
    
    print(f"✅ 생성 완료: {name} -> {file_name}")

print("\n모든 QR코드가 'branch_qrs' 폴더에 저장되었습니다!")