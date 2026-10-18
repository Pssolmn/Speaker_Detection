"""รายการงานตรวจที่เหลือ (backlog) ระดับ "บรรทัดซับ" — ไม่ใช่ระดับคลิปเสียง/ภาพ.

สถานะ "confirmed" ในตาราง observations (ที่เห็นในแอป) หมายถึง "คลิปนี้ถูกล็อกไว้ในกลุ่มที่
ยืนยันแล้ว" เท่านั้น ไม่ได้แปลว่ามีคนเปิดฟัง/ดูคลิปนั้นทีละอันจริง ๆ — สคริปต์นี้มองข้ามสถานะนั้น
ไปเลย แล้วดูที่ผลลัพธ์จริงระดับบรรทัดซับแทน (MANUAL / PROPOSED / AMBIGUOUS / UNKNOWN /
MULTIPLE_SPEAKERS) ซึ่งเป็นสิ่งเดียวที่บอกได้ว่า "บรรทัดนี้มีคนยืนยันเองหรือยัง"

จัดลำดับความสำคัญให้: ตัวละครที่มีบทเยอะที่สุดก่อน (ตรวจกลุ่มเดียวแก้ได้หลายบรรทัดพร้อมกัน)
แล้วค่อยไล่บรรทัดที่ยังไม่มีชื่อเลย (AMBIGUOUS/UNKNOWN/MULTIPLE_SPEAKERS) ทีละจุดเวลา

เรียก:
  venv/bin/python -m scripts.review_backlog data/output/workspace-demo
  venv/bin/python -m scripts.review_backlog data/output/workspace-demo --out backlog.csv
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from src.io.result_export import format_srt_time
from src.workspace.attribution import subtitle_results
from src.workspace.store import WorkspaceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--media-id", default=None, help="ไม่ใส่ = ใช้วิดีโอแรกในโปรเจกต์")
    parser.add_argument("--out", type=Path, default=Path("review_backlog.csv"))
    args = parser.parse_args()

    with WorkspaceStore(args.workspace) as store:
        media_id = args.media_id or store.media()[0]["id"]
        media_title = next(m["title"] for m in store.media() if m["id"] == media_id)
        segments, results = subtitle_results(store, media_id)

    rows = []
    for segment, result in zip(segments, results):
        name = result.manual_character or (
            segment.script_character if segment.script_character else None) or result.detected_character
        rows.append({
            "id": segment.id, "start_ms": segment.start_ms, "end_ms": segment.end_ms,
            "text": segment.text.replace("\n", " ")[:60], "status": result.status, "name": name,
        })

    by_status = Counter(row["status"] for row in rows)
    manual = by_status.get("MANUAL", 0)

    print(f"=== {media_title} — {len(rows)} บรรทัด ===")
    print(f"ตรวจเองแล้วจริง (MANUAL): {manual} ({manual/len(rows):.1%})")
    print(f"ยังไม่ตรวจ: {len(rows) - manual} ({(len(rows)-manual)/len(rows):.1%})\n")

    # ลำดับความสำคัญ 1: ตัวละครที่มีบทเยอะสุด ยังไม่มี MANUAL เลยสักบรรทัด
    per_character = defaultdict(lambda: {"total": 0, "manual": 0})
    for row in rows:
        if row["status"] in ("PROPOSED", "MANUAL") and row["name"]:
            per_character[row["name"]]["total"] += 1
            if row["status"] == "MANUAL":
                per_character[row["name"]]["manual"] += 1

    print("ลำดับที่ 1 — ตรวจกลุ่มตัวละครที่มีบทเยอะสุดก่อน (คุ้มเวลาที่สุด):")
    ranked = sorted(per_character.items(), key=lambda pair: -pair[1]["total"])
    for name, info in ranked[:10]:
        done = info["manual"]
        print(f"  {name:<18} {info['total']:>3} บรรทัด · ตรวจแล้ว {done}/{info['total']}")

    # ลำดับความสำคัญ 2: บรรทัดที่ยังไม่มีชื่อเลย เรียงตามเวลา พร้อม timecode กดไปดูได้ตรง ๆ
    unresolved = [row for row in rows if row["status"] in ("AMBIGUOUS", "UNKNOWN", "MULTIPLE_SPEAKERS")]
    print(f"\nลำดับที่ 2 — {len(unresolved)} บรรทัดที่ยังไม่มีชื่อเลย (เรียงตามเวลา ใช้ timecode กดไปดูในแอปได้ตรงจุด):")
    for row in unresolved[:30]:
        print(f"  {format_srt_time(row['start_ms'])}  [{row['status']:<17}] \"{row['text']}\"")
    if len(unresolved) > 30:
        print(f"  ... อีก {len(unresolved) - 30} บรรทัด (ดูทั้งหมดในไฟล์ CSV)")

    with open(args.out, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "timecode", "status", "name", "text"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"id": row["id"], "timecode": format_srt_time(row["start_ms"]),
                             "status": row["status"], "name": row["name"] or "", "text": row["text"]})
    print(f"\nบันทึกรายการทั้งหมด {len(rows)} บรรทัดไว้ที่: {args.out}")


if __name__ == "__main__":
    main()
