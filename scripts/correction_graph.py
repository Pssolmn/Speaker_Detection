"""กราฟสรุป docs/correction_log.csv — AI เสนอผิด / คนแก้ไข กู้คืนจากตาราง history

เรียก: venv/bin/python -m scripts.correction_graph
"""

import csv
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["font.family"] = "Sarabun"


def main():
    csv_path = Path(__file__).resolve().parents[1] / "docs" / "correction_log.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    move = [r for r in rows if r["action"] == "move/split"]
    first_assign = [r for r in move if r["from"] == "(ยังไม่จัดกลุ่ม)"]
    unassign = [r for r in move if r["to"] == "(ยังไม่จัดกลุ่ม)"]
    reassign = [r for r in move if r["from"] != "(ยังไม่จัดกลุ่ม)" and r["to"] != "(ยังไม่จัดกลุ่ม)"]
    deleted = [r for r in rows if r["action"] == "delete profile"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    categories = [
        ("ย้ายข้ามกลุ่ม\n(กลุ่มเดิมผิด ย้ายไปกลุ่มอื่น)", len(reassign), "#791F1F"),
        ("ลบโปรไฟล์ทิ้งถาวร\n(กลุ่มที่ AI สร้างซ้ำซ้อน/ผิด)", len(deleted), "#E24B4A"),
        ("ส่งกลับไม่จัดกลุ่ม\n(ตัดออกจากกลุ่มเดิม)", len(unassign), "#BA7517"),
        ("จัดครั้งแรก\n(ยังไม่จัดกลุ่ม -> มีชื่อ)", len(first_assign), "#185FA5"),
    ]
    labels = [c[0] for c in categories]
    values = [c[1] for c in categories]
    colors = [c[2] for c in categories]
    ax1.bar(range(len(labels)), values, color=colors)
    ax1.set_xticks(range(len(labels)))
    ax1.set_xticklabels(labels, rotation=0, fontsize=9)
    ax1.set_ylabel("จำนวนครั้ง (นับระดับช่วงเสียง/ภาพ หรือกลุ่ม)")
    ax1.set_title("เหตุการณ์แก้ไขที่กู้คืนได้จากประวัติแอป (131 actions)")
    for index, value in enumerate(values):
        ax1.text(index, value + 2, str(value), ha="center")

    pairs = Counter((r["from"], r["to"]) for r in reassign)
    top = pairs.most_common(10)
    pair_labels = [f"{f} -> {t}" for (f, t), _ in top]
    pair_values = [c for _, c in top]
    ax2.barh(range(len(pair_labels)), pair_values[::-1], color="#791F1F")
    ax2.set_yticks(range(len(pair_labels)))
    ax2.set_yticklabels(pair_labels[::-1], fontsize=9)
    ax2.set_xlabel("จำนวนช่วงที่ถูกย้าย")
    ax2.set_title("คู่กลุ่มที่ AI สลับผิดบ่อยที่สุด (เดิม -> แก้เป็น)")

    fig.suptitle("ร่องรอยการแก้ไขผลลัพธ์ AI ที่กู้คืนได้จากระบบ undo ของแอป\n"
                  "(หมายเหตุ: นับเฉพาะที่มีคนมาแก้ไขภายหลังเท่านั้น ไม่รวมตอน AI เสนอครั้งแรกตอนสแกน)",
                  fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    out_path = Path(__file__).resolve().parents[1] / "docs" / "correction_graph.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"บันทึกภาพ: {out_path}")


if __name__ == "__main__":
    main()
