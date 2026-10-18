"""จัดกลุ่มแบบ incremental โดยเทียบกับตัวแทนที่จำกัดจำนวน ไม่กิน RAM แบบ N².

ผลอัตโนมัติเป็น proposed เสมอ; locked คือการแก้/ยืนยันของคน ห้ามเขียนทับ.
ระยะต่ำแปลว่าคล้าย คะแนนที่แสดงคือ 1-distance ไม่ใช่โอกาสถูกต้อง.
"""

import numpy as np

from src.core.control import check_cancel


def reset_unlocked_memberships(store, kind, media_id=None):
    """คืนค่า observation ที่ยังไม่ล็อกกลับเป็นยังไม่จัดกลุ่ม ก่อนเรียก cluster_observations() ใหม่

    ไม่แตะอันที่ล็อก/ยืนยันแล้วเด็ดขาด; เก็บกวาดโปรไฟล์ว่างที่ยังไม่ยืนยันซึ่งไม่เหลือสมาชิกแล้วด้วย
    ใช้ร่วมกันทั้ง scripts/recluster.py (CLI) และปุ่ม "จัดกลุ่มใหม่จากที่ยืนยันแล้ว" ใน GUI
    """
    clause = "o.kind=?" + (" AND o.media_id=?" if media_id else "")
    parameters = (kind, media_id) if media_id else (kind,)
    affected = store.rows(
        "SELECT m.observation_id FROM memberships m JOIN observations o ON o.id=m.observation_id "
        f"WHERE {clause} AND m.locked=0 AND m.profile_id IS NOT NULL", parameters)
    with store.lock, store.db:
        store.db.execute(
            f"UPDATE memberships SET profile_id=NULL,score=NULL,state='pending' WHERE observation_id IN "
            f"(SELECT o.id FROM observations o WHERE {clause} AND o.id IN "
            "(SELECT observation_id FROM memberships WHERE locked=0))", parameters)
        # เก็บกวาดโปรไฟล์ที่ไม่มีสมาชิกเหลือแล้วและยังไม่ยืนยัน ไม่แตะโปรไฟล์ที่ยืนยันแล้วแม้จะว่าง
        # กันสำรอง: ไม่ลบโปรไฟล์ที่ยังมี link ผูกอยู่เด็ดขาด แม้ confirmed จะหลุดจากที่อื่นมาก็ตาม
        empty = store.rows(
            "SELECT p.id FROM profiles p LEFT JOIN memberships m ON m.profile_id=p.id "
            "WHERE p.kind=? AND p.confirmed=0 "
            "AND p.id NOT IN (SELECT voice_id FROM links UNION SELECT visual_id FROM links) "
            "GROUP BY p.id HAVING COUNT(m.observation_id)=0", (kind,))
        for row in empty:
            store.db.execute("DELETE FROM profiles WHERE id=?", (row["id"],))
    return len(affected)


def cosine_distances(query, references):
    query = np.asarray(query, np.float32)
    references = np.asarray(references, np.float32)
    norm = np.linalg.norm(query)
    lengths = np.linalg.norm(references, axis=1)
    if norm <= 0 or np.any(lengths <= 0):
        raise ValueError("Cannot compare zero-length embeddings")
    return np.clip(1 - (references @ query) / (lengths * norm), 0, 2)


def cluster_observations(store, kind, distance_fn, threshold, *, margin=.025, cancel=None):
    """หนึ่งตัวแทนต่อ track/voice turn; รุ่นโมเดลต่างกันจะไม่ถูกเปรียบเทียบ."""
    if not np.isfinite(threshold) or threshold <= 0 or margin < 0:
        raise ValueError("Invalid clustering thresholds")
    records = store.observations(kind=kind)
    prototypes = {}
    intervals = {}
    # โหลดตัวแทนสูงสุด 6 ชิ้นต่อกลุ่ม; หลักฐานยืนยันมาก่อนคำเดา
    for item in sorted(records, key=lambda x: not x["locked"]):
        if item["profile_id"] and item["features"] is not None:
            key = (item["profile_id"], item["model_key"])
            prototypes.setdefault(key, [])
            if len(prototypes[key]) < 6:
                prototypes[key].append(item["features"])
            intervals.setdefault(item["profile_id"], []).append(item)
    for item in records:
        check_cancel(cancel)
        if item["locked"] or item["profile_id"] is not None:
            continue
        if item["features"] is None or item["evidence"].get("low_quality"):
            continue
        candidates = []
        for (profile_id, model_key), vectors in prototypes.items():
            if model_key != item["model_key"]:
                continue
            # ใบหน้าสอง track ที่พบเวลาเดียวกันไม่ควรถูกรวมเพียงเพราะหน้าคล้าย
            collision = any(other["media_id"] == item["media_id"] and
                            min(other["end_ms"], item["end_ms"]) - max(other["start_ms"], item["start_ms"]) > 100
                            for other in intervals.get(profile_id, []))
            if collision:
                continue
            distances = np.sort(distance_fn(item["features"], vectors))
            distance = float(np.mean(distances[:min(2, len(distances))]))
            candidates.append((distance, profile_id))
        candidates.sort()
        profile_id = None
        if candidates and candidates[0][0] <= threshold:
            if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < margin:
                store.auto_assign(item["id"], state="ambiguous")
                continue
            profile_id = store.auto_assign(item["id"], candidates[0][1],
                                           score=float(np.clip(1 - candidates[0][0], 0, 1)))
        elif candidates and candidates[0][0] <= threshold + margin:
            store.auto_assign(item["id"], state="ambiguous")
            continue
        else:
            profile_id = store.auto_assign(item["id"], new=True)
        if profile_id:
            key = (profile_id, item["model_key"])
            bucket = prototypes.setdefault(key, [])
            if len(bucket) < 6:
                bucket.append(item["features"])
            intervals.setdefault(profile_id, []).append(item)
