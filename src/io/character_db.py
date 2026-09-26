"""Build and load character reference profiles from data/references/<character>/."""

import pickle
from pathlib import Path
from typing import Dict, List, Any

from src.core.config import DATABASE_PATH

def load_character_database(db_path: Path = DATABASE_PATH) -> Dict[str, List[Dict[str, Any]]]:
    """
    โหลดฐานข้อมูลตัวละครจากไฟล์ .pkl เข้าสู่หน่วยความจำ
    
    Args:
        db_path: ที่อยู่ของไฟล์ฐานข้อมูล (ค่าเริ่มต้นดึงจาก config.DATABASE_PATH)
        
    Returns:
        Dict ที่มี Key เป็นชื่อตัวละคร และ Value เป็น List ของฟีเจอร์อ้างอิง
        
    Raises
        FileNotFoundError: หากไม่พบไฟล์ฐานข้อมูลบนดิสก์
        ValueError: หากไฟล์ว่างเปล่าหรือโครงสร้างข้อมูลไม่ถูกต้อง
    """
    db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Character database file not found: {db_path}"
                                "\nPlease run build_db.py to create the database.")

    with db_path.open("rb") as file_handle:
        try:
            database = pickle.load(file_handle)
        except Exception as error:
            raise ValueError(f"Failed to load character database from {db_path}: {error}")

    if not isinstance(database, dict) or not database:
        raise ValueError(f"Character database is empty or has an invalid structure: {db_path}")

    for character_name, references in database.items():
        if not isinstance(references, list) or len(references) == 0:
            raise ValueError(f"References for character '{character_name}' should be a list, got {type(references)}")

    return database