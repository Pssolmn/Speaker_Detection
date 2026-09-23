import cv2
import numpy as np

def calculate_histogram_similarity(hist_a, hist_b):
    """
    คำนวณความเหมือนของ 2D Color Histogram ด้วยสมการ Histogram Intersection
    คืนค่าเป็นคะแนนระหว่าง 0.0 ถึง 1.0 (1.0 = เหมือนกันทุกประการ)
    """
    if hist_a is None or hist_b is None:
        return 0.0
    
    # ใช้ฟังก์ชันเปรียบเทียบ Histogram ของ OpenCV
    similarity = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_INTERSECT)
    
    # บังคับช่วงค่าให้อยู่ระหว่าง 0.0 ถึง 1.0
    return float(np.clip(similarity, 0.0, 1.0))

def calculate_dominant_color_similarity(hsv_a, hsv_b):
    """
    วัดระยะห่างของเวกเตอร์สีเด่น [H, S, V] และแปลงเป็นคะแนนความเหมือน (0.0 ถึง 1.0)
    """
    if hsv_a is None or hsv_b is None:
        return 0.0

    hsv_a = np.array(hsv_a, dtype=np.float32)
    hsv_b = np.array(hsv_b, dtype=np.float32)

    # ใน OpenCV ค่า Hue เป็นวงกลม 0-180 องศา จึงต้องคิดระยะทางแบบวงกลม (Circular Distance)
    h_dist = abs(hsv_a[0] - hsv_b[0])
    h_dist = min(h_dist, 180.0 - h_dist) / 90.0  # Normalize ให้อยู่ในช่วง 0.0 - 1.0

    # Saturation (0-255) และ Value (0-255) คิดระยะห่างแบบปกติ
    s_dist = abs(hsv_a[1] - hsv_b[1]) / 255.0
    v_dist = abs(hsv_a[2] - hsv_b[2]) / 255.0

    # ถ่วงน้ำหนัก: Hue สำคัญที่สุด 70%, ความสด 20%, ความสว่าง 10%
    total_distance = (0.7 * h_dist) + (0.2 * s_dist) + (0.1 * v_dist)
    
    # แปลงระยะห่าง (Distance) ให้เป็นคะแนนความเหมือน (Similarity)
    similarity = 1.0 - total_distance
    return float(np.clip(similarity, 0.0, 1.0))

def compare_character_features(features_a, features_b):
    """
    คำนวณคะแนนรวมระหว่าง Feature สองชุด
    คืนค่าเป็นคะแนนรวม (Final Score) พร้อมรายละเอียด
    """
    if features_a is None or features_b is None:
        return {"final_score": 0.0, "hist_score": 0.0, "color_score": 0.0}

    # 1. เทียบ Histogram (การกระจายตัวของสี)
    hist_score = calculate_histogram_similarity(
        features_a["histogram"], 
        features_b["histogram"]
    )

    # 2. เทียบสีเด่น
    color_score = calculate_dominant_color_similarity(
        features_a["dominant_hsv"], 
        features_b["dominant_hsv"]
    )

    # 3. คะแนนรวมถ่วงน้ำหนัก (ให้ความสำคัญกับ Histogram 70% เพราะทนต่อแสงเงามากกว่า)
    final_score = (0.7 * hist_score) + (0.3 * color_score)

    return {
        "final_score": round(final_score, 4),
        "hist_score": round(hist_score, 4),
        "color_score": round(color_score, 4)
    }