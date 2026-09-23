import os
import cv2
import pickle
from extractor import extract_character_features

REFERENCE_DIR = "data/references"
OUTPUT_DB_PATH = "character_db.pkl"

def build_character_database():
    database = {}
    
    # วนลูปอ่านทุกไฟล์ภาพในโฟลเดอร์ references
    for filename in os.listdir(REFERENCE_DIR):
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            continue
            
        # สมมติการตั้งชื่อไฟล์เป็น: characterName_01.jpg -> ดึงชื่อ characterName ออกมา
        character_name = filename.split('_')[0]
        image_path = os.path.join(REFERENCE_DIR, filename)
        image = cv2.imread(image_path)
        
        if image is None:
            continue
            
        # สกัด Feature ทาง Image Processing
        features = extract_character_features(image)
        if features is None:
            continue
            
        # จัดเก็บลง Database
        if character_name not in database:
            database[character_name] = []
            
        database[character_name].append({
            "filename": filename,
            "features": features
        })
        print(f"บันทึกข้อมูลสำเร็จ: {character_name} จากไฟล์ {filename}")
        
    # เซฟข้อมูลทั้งหมดเป็นไฟล์ไบนารี
    with open(OUTPUT_DB_PATH, "wb") as f:
        pickle.dump(database, f)
        
    print(f"\nสร้างฐานข้อมูลตัวละครเสร็จสมบูรณ์ -> บันทึกที่ {OUTPUT_DB_PATH}")

if __name__ == "__main__":
    build_character_database()