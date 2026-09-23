import cv2
import numpy as np
from sklearn.cluster import KMeans

def crop_hair_roi(image, bbox = None, face_mask=None, hair_mask=None):
    """
    Crop the region of interest (ROI) containing hair from the input image using the provided hair mask.

    Parameters:
        image (numpy.ndarray): The input image from which to crop the hair ROI.
        bbox (tuple): The bounding box coordinates (x, y, w, h) for the region of interest.
        face_mask (numpy.ndarray, optional): A binary mask indicating the face region.

        hair_mask (numpy.ndarray, optional): A binary mask indicating the hair region.
    
    Outputs:
        numpy.ndarray: The cropped hair ROI image.
    """
    img_height, img_width = image.shape[:2]

    # กรณีที่ 1: มี hair_mask ส่งเข้ามา (วิธีของคุณ: แม่นยำที่สุดระดับพิกเซล)
    if hair_mask is not None:
        # Ensure the hair mask is binary
        hair_mask_bin = (hair_mask > 0).astype(np.uint8)
        x, y, w, h = cv2.boundingRect(hair_mask_bin)

        if w == 0 or h == 0:
            raise ValueError("Hair mask does not contain any hair region.")
        
        hair_roi = image[y:y+h, x:x+w]
        return hair_roi
    # กรณีที่ 2: ไม่มี mask แต่มี bbox ส่งเข้ามา (วิธีของคุณ: แม่นยำระดับ bounding box)
    elif bbox is not None:
        x, y, w, h = bbox

        # กะประมาณเชิงเรขาคณิต: ขยายขึ้นด้านบนศีรษะ 40% และกินลงมาในส่วนหน้าผาก 20%
        y_start = max(0, y - int(0.4 * h))  # ขยายขึ้นด้านบนศีรษะ 40%
        y_end = min(img_height, int(y + 0.2 * h))  # กินลงมาในส่วนหน้าผาก 20%
        x_start = max(0, int(x - 0.1 * w))  # ขยายออกด้านข้างซ้าย 10%
        x_end = min(img_width, int(x + 1.1 * w))  # ขยายออกด้านข้างขวา 10%

        hair_roi = image[y_start:y_end, x_start:x_end]
        if hair_roi.size == 0:
            raise ValueError("Bounding box does not contain any hair region.")
        return hair_roi
    # กรณีที่ 3: ไม่มีทั้ง Mask และ Bbox (เป็นภาพพอร์ตเทรตที่ครอปส่วนหัวมาแล้ว)
    else:
        # ตัดเอาพื้นที่ครึ่งบน (45%) ของภาพไปใช้งาน
        return image[0:int(img_height * 0.45), 0:img_width]


def filter_lineart_and_background(hsv_roi):
    """
    filter out lineart and background colors from the hair ROI in HSV color space.
    """

    # Channel 0 = Hue, Channel 1 = Saturation, Channel 2 = Value
    v_channel = hsv_roi[:, :, 2]
    s_channel = hsv_roi[:, :, 1]

    # เงื่อนไข: ตัดพิกเซลที่มืดเกินไป (V < 40 คือเส้นตัดขอบ) 
    # และตัดพิกเซลที่สว่างจัดแต่ไร้สี (S < 25 และ V > 230 คือแสงสะท้อนหรือพื้นหลังขาว)
    valid_mask = (v_channel >= 40) & ~((s_channel < 25) & (v_channel > 230))
    
    return valid_mask

def extract_dominant_hair_color(hsv_roi, mask, k=3):
    """
    Extract colors K-means Clustering
    Parameters:
        hsv_roi (numpy.ndarray): The cropped hair ROI image in HSV color space.
        mask (numpy.ndarray): A binary mask indicating valid hair pixels.
        k (int): The number of dominant colors to extract.
    """
    valid_pixels = hsv_roi[mask]

    if len(valid_pixels) == 0:
        raise ValueError("No valid hair pixels found for color extraction.")
    elif len(valid_pixels) < 10:
        return np.array([0.0, 0.0, 0.0])  # Return black if not enough valid pixels

    kmeans = KMeans(n_clusters=k, random_state=42, n_init=5)
    kmeans.fit(valid_pixels)

    count = np.bincount(kmeans.labels_)
    dominant_hsv = kmeans.cluster_centers_[np.argmax(count)]
    return dominant_hsv

def extract_color_histogram(hsv_roi, mask, h_bins=30, s_bins=32):
    """
    สร้าง 2D Color Histogram (Hue & Saturation)
    ตัดแกน Value ทิ้งเพื่อไม่ให้ความมืด-สว่างของแสงในฉากมารบกวนการตัดสิน
    """
    # แปลง mask เป็น uint8 เพื่อให้ OpenCV ใช้งานได้ (255 = จุดที่คิด, 0 = จุดที่ตัดทิ้ง)
    cv_mask = (mask.astype(np.uint8)) * 255
    
    # คำนวณ 2D Histogram: แกน H (0-180), แกน S (0-256)
    hist = cv2.calcHist(
        [hsv_roi], 
        channels=[0, 1], 
        mask=cv_mask, 
        histSize=[h_bins, s_bins], 
        ranges=[0, 180, 0, 256]
    )
    
    # Normalize ให้ผลรวมของพิกเซลในตารางเท่ากับ 1.0 เพื่อให้เปรียบเทียบข้ามภาพที่มีขนาดต่างกันได้
    hist = cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    
    return hist

def extract_character_features(image, bbox=None):
    """
    ฟังก์ชันรวม (Wrapper): รับภาพเข้ามา -> ส่งคืนค่าความ Unique ครบชุด
    """
    # 1. ตัดพื้นที่ผม
    hair_roi = crop_hair_roi(image, bbox)
    if hair_roi.size == 0:
        return None
        
    # 2. แปลงเป็น HSV
    hsv_roi = cv2.cvtColor(hair_roi, cv2.COLOR_BGR2HSV)
    
    # 3. ตัด Noise (เส้นขอบและแสงสะท้อน)
    mask = filter_lineart_and_background(hsv_roi)
    
    # 4. ดึงค่าสีเด่น และสร้าง Histogram
    dominant_color = extract_dominant_hair_color(hsv_roi, mask, k=3)
    color_hist = extract_color_histogram(hsv_roi, mask)
    
    return {
        "dominant_hsv": dominant_color.tolist(),
        "histogram": color_hist
    }