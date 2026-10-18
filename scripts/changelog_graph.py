"""สร้างกราฟสรุป docs/changelog.csv — จำนวนตามหมวด และสะสมตามวันที่.

เรียก: venv/bin/python -m scripts.changelog_graph
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["font.family"] = "Sarabun"

CATEGORY_COLOR = {
    "correctness": "#E24B4A",
    "correctness-critical": "#791F1F",
    "ux": "#BA7517",
    "feature": "#1D9E75",
    "reporting": "#185FA5",
}
CATEGORY_LABEL = {
    "correctness": "บั๊กความถูกต้อง",
    "correctness-critical": "บั๊กร้ายแรง (ข้อมูลหาย)",
    "ux": "UX",
    "feature": "ฟีเจอร์ใหม่",
    "reporting": "การรายงานผิด",
}


def main():
    csv_path = Path(__file__).resolve().parents[1] / "docs" / "changelog.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    # กราฟ 1: จำนวนตามหมวด
    counts = Counter(row["category"] for row in rows)
    categories = sorted(counts, key=lambda c: -counts[c])
    ax1.bar(range(len(categories)), [counts[c] for c in categories],
           color=[CATEGORY_COLOR[c] for c in categories])
    ax1.set_xticks(range(len(categories)))
    ax1.set_xticklabels([CATEGORY_LABEL[c] for c in categories], rotation=20, ha="right")
    ax1.set_ylabel("จำนวน")
    ax1.set_title("จำนวนปัญหา/งานที่พบ แยกตามหมวด")
    for index, category in enumerate(categories):
        ax1.text(index, counts[category] + 0.1, str(counts[category]), ha="center")

    # กราฟ 2: สะสมตามวันที่
    by_date = defaultdict(int)
    for row in rows:
        by_date[row["date"]] += 1
    dates = sorted(by_date)
    cumulative, total = [], 0
    for date in dates:
        total += by_date[date]
        cumulative.append(total)
    ax2.plot(dates, cumulative, marker="o", color="#534AB7")
    ax2.set_ylabel("จำนวนสะสม")
    ax2.set_title("จำนวนปัญหาที่พบ/แก้สะสมตามวัน")
    ax2.set_ylim(0, max(cumulative) + 2)

    fig.tight_layout()
    out_path = Path(__file__).resolve().parents[1] / "docs" / "changelog_graph.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"บันทึกภาพ: {out_path}")


if __name__ == "__main__":
    main()
