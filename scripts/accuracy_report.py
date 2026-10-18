"""รายงานความแม่นยำของข้อเสนอ AI เทียบกับที่คุณตรวจยืนยัน/แก้ไขแล้ว — อ่านอย่างเดียว ไม่เขียนอะไร.

หาค่า profile_id แรกสุดที่เคยบันทึกไว้ใน undo history ของแต่ละ observation (คือสิ่งที่ AI เสนอ
ก่อนมนุษย์แตะเป็นครั้งแรก) แล้วเทียบกับค่าปัจจุบัน:
  - เท่ากัน + ล็อกแล้ว      → AI เสนอถูก (คุณยืนยันตามที่เสนอ)
  - ไม่เท่ากัน + ล็อกแล้ว   → AI เสนอผิด (คุณย้าย/แก้ไปกลุ่มอื่น)
  - เดิมไม่มีข้อเสนอ (None) + ล็อกแล้ว → AI ไม่ได้เสนอ (คุณกำหนดเอง)
  - ยังไม่ล็อก (ยังไม่ตรวจ) → ไม่นับในเปอร์เซ็นต์ความแม่นยำ
  - observation ที่ถูกลบไปแล้วไม่อยู่ในฐานข้อมูล จึงไม่ถูกนับโดยอัตโนมัติ อยู่แล้ว

เรียก: venv/bin/python -m scripts.accuracy_report data/output/workspace-demo --kind visual
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.workspace.store import WorkspaceStore

matplotlib.rcParams["font.family"] = "Sarabun"


def earliest_known_assignment(store):
    """profile_id แรกสุดที่เคยปรากฏใน history snapshot ของแต่ละ observation (ก่อนแก้มือครั้งแรก)"""
    earliest = {}
    for row in store.rows("SELECT snapshot FROM history ORDER BY id ASC"):
        snapshot = json.loads(row["snapshot"])
        for membership in snapshot["memberships"]:
            obs_id = membership["observation_id"]
            if obs_id not in earliest:
                earliest[obs_id] = membership["profile_id"]
    return earliest


def classify(store, kind):
    earliest = earliest_known_assignment(store)
    current = store.rows(
        "SELECT o.id,o.start_ms,o.end_ms,m.profile_id,m.locked FROM observations o "
        "JOIN memberships m ON m.observation_id=o.id WHERE o.kind=?", (kind,))
    correct, wrong, no_proposal, unreviewed = [], [], [], []
    for item in current:
        if not item["locked"]:
            unreviewed.append(item)
            continue
        # ไม่เคยปรากฏใน history แปลว่าไม่เคยถูกแก้มือเลย -> ค่าปัจจุบันคือค่าที่ AI เสนอไว้ตั้งแต่แรก
        original = earliest.get(item["id"], item["profile_id"])
        if original is None:
            no_proposal.append(item)
        elif original == item["profile_id"]:
            correct.append(item)
        else:
            wrong.append(item)
    return correct, wrong, no_proposal, unreviewed


def plot_timeline(correct, wrong, no_proposal, unreviewed, title, out_path):
    fig, ax = plt.subplots(figsize=(12, 1.8))
    groups = [("ถูก", correct, "#1D9E75"), ("ผิด", wrong, "#E24B4A"),
              ("AI ไม่เสนอ", no_proposal, "#BA7517"), ("ยังไม่ตรวจ", unreviewed, "#B4B2A9")]
    for _, items, color in groups:
        for item in items:
            start_s, duration_s = item["start_ms"] / 1000, max((item["end_ms"] - item["start_ms"]) / 1000, 0.05)
            ax.broken_barh([(start_s, duration_s)], (0, 1), facecolors=color)
    handles = [plt.Rectangle((0, 0), 1, 1, color=color) for _, _, color in groups]
    ax.legend(handles, [name for name, _, _ in groups], loc="upper center",
             bbox_to_anchor=(0.5, -0.55), ncol=4, frameon=False)
    ax.set_yticks([])
    all_items = correct + wrong + no_proposal + unreviewed
    ax.set_xlim(0, max((item["end_ms"] for item in all_items), default=1000) / 1000 + 1)
    ax.set_xlabel("เวลาในตอน (วินาที)", labelpad=10)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--kind", choices=["visual", "voice"], default="visual")
    parser.add_argument("--out", type=Path, default=Path("accuracy_report.png"))
    args = parser.parse_args()

    with WorkspaceStore(args.workspace) as store:
        correct, wrong, no_proposal, unreviewed = classify(store, args.kind)

    reviewed = len(correct) + len(wrong)
    accuracy = len(correct) / reviewed if reviewed else None

    print(f"ตรวจแล้ว (ล็อก/ยืนยัน): {reviewed + len(no_proposal)} ช่วง · ยังไม่ตรวจ: {len(unreviewed)} ช่วง")
    print(f"  AI เสนอถูก (ยืนยันตามที่เสนอ): {len(correct)}")
    print(f"  AI เสนอผิด (ย้ายไปกลุ่มอื่น):   {len(wrong)}")
    print(f"  AI ไม่ได้เสนอ (กำหนดเอง):      {len(no_proposal)}")
    if accuracy is not None:
        print(f"\nความแม่นยำของ AI (เฉพาะที่เสนอแล้วตรวจแล้ว): {accuracy:.1%}")
    else:
        print("\nยังไม่มีข้อมูลพอคำนวณความแม่นยำ — ต้องยืนยัน/แก้ไขอย่างน้อย 1 ช่วงก่อน (กดยืนยันกลุ่ม/ย้าย/แยก ในแอป)")

    title = f"ความแม่นยำของข้อเสนอ AI ตามเวลา — {args.kind}" + (f" ({accuracy:.0%} ถูก)" if accuracy is not None else "")
    plot_timeline(correct, wrong, no_proposal, unreviewed, title, args.out)
    print(f"บันทึกภาพ: {args.out}")


if __name__ == "__main__":
    main()
