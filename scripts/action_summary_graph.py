"""กราฟสรุป Action รวม: AI เสนอ vs คนย้าย/แก้ไข แยกฝั่งภาพ-เสียง

ตัวเลขมาจาก 2 แหล่ง:
  1. docs/correction_log.csv (กู้จาก history — ดู scripts/ai_correction_log.py)
  2. จำนวน observation ทั้งหมด/ที่ล็อกแล้วในฐานข้อมูลปัจจุบัน (data/output/workspace-demo)

เรียก: venv/bin/python -m scripts.action_summary_graph
"""

import csv
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.workspace.store import WorkspaceStore

matplotlib.rcParams["font.family"] = "Sarabun"

WORKSPACE = Path(__file__).resolve().parents[1] / "data" / "output" / "workspace-demo"


def main():
    with WorkspaceStore(WORKSPACE) as store:
        obs_kind = {o["id"]: o["kind"] for o in store.observations()}
        total_by_kind = Counter(obs_kind.values())
        locked_by_kind = Counter()
        for m in store.rows("SELECT observation_id,locked FROM memberships"):
            k = obs_kind.get(m["observation_id"])
            if k and m["locked"]:
                locked_by_kind[k] += 1

    csv_path = Path(__file__).resolve().parents[1] / "docs" / "correction_log.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    move = [r for r in rows if r["action"] == "move/split"]
    reassign = [r for r in move if r["from"] != "(ยังไม่จัดกลุ่ม)" and r["to"] != "(ยังไม่จัดกลุ่ม)"]
    unassign = [r for r in move if r["to"] == "(ยังไม่จัดกลุ่ม)"]

    def by_kind(events):
        c = Counter()
        for r in events:
            k = obs_kind.get(r["observation_id"])
            if k:
                c[k] += 1
        return c

    reassign_by_kind = by_kind(reassign)
    unassign_by_kind = by_kind(unassign)
    deleted_visual_profiles, deleted_visual_members = 46, 155  # จาก scripts/ai_correction_log.py (ลบโปรไฟล์ทิ้งถาวร เป็นฝั่งภาพล้วน)

    kinds = ["visual", "voice"]
    kind_label = {"visual": "ฝั่งภาพ", "voice": "ฝั่งเสียง"}

    categories = [
        ("AI จัดกลุ่มทั้งหมด", [total_by_kind[k] for k in kinds], "#B0B0B0"),
        ("ยืนยันแล้ว (คงกลุ่มเดิมของ AI)", [locked_by_kind[k] for k in kinds], "#1D9E75"),
        ("ย้ายข้ามกลุ่ม (AI จัดผิดกลุ่ม)", [reassign_by_kind[k] for k in kinds], "#791F1F"),
        ("ตัดออก/ส่งกลับไม่จัดกลุ่ม", [unassign_by_kind[k] for k in kinds], "#BA7517"),
        ("ลบกลุ่มซ้ำซ้อนทิ้ง (ผูกช่วง)", [deleted_visual_members, 0], "#E24B4A"),
    ]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = range(len(kinds))
    bar_width = 0.15
    for i, (label, values, color) in enumerate(categories):
        offsets = [pos + (i - (len(categories) - 1) / 2) * bar_width for pos in x]
        bars = ax.bar(offsets, values, width=bar_width, label=label, color=color)
        for bar, value in zip(bars, values):
            if value:
                ax.text(bar.get_x() + bar.get_width() / 2, value + 5, str(value), ha="center", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{kind_label[k]}\n(AI จัดมาให้ {total_by_kind[k]} ช่วง)" for k in kinds], fontsize=11)
    ax.set_ylabel("จำนวนช่วง (observation)")
    ax.set_title("สรุป Action: AI เสนอ vs คนแก้ไข — เทียบฝั่งภาพกับฝั่งเสียง\n"
                  "(นับเฉพาะที่มีคนมาแก้ภายหลังเท่านั้น; ไม่รวมตอน AI เสนอครั้งแรกตอนสแกน)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=9)

    fig.tight_layout()
    out_path = Path(__file__).resolve().parents[1] / "docs" / "action_summary_graph.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"บันทึกภาพ: {out_path}")

    print("\nสรุปตัวเลขดิบ:")
    for k in kinds:
        print(f"  {kind_label[k]}: AI จัดมาให้ {total_by_kind[k]} ช่วง, ยืนยันคงกลุ่มเดิม {locked_by_kind[k]}, "
              f"ย้ายข้ามกลุ่ม {reassign_by_kind[k]}, ตัดออก {unassign_by_kind[k]}"
              + (f", ลบกลุ่มทิ้ง {deleted_visual_profiles} กลุ่ม({deleted_visual_members} ช่วง)" if k == "visual" else ""))
        pct = reassign_by_kind[k] / total_by_kind[k] * 100 if total_by_kind[k] else 0
        print(f"    -> สัดส่วนที่ AI จัด 'ผิดกลุ่ม' (ย้ายข้ามกลุ่ม/ช่วงทั้งหมด): {pct:.1f}%")


if __name__ == "__main__":
    main()
