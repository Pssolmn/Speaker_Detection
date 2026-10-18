"""จุดตรวจ Cancel ร่วมกันของ CLI/GUI และงานวิเคราะห์ ไม่ขึ้นกับ Qt."""

from collections.abc import Callable

CancelCheck = Callable[[], bool] | None


class AnalysisCancelled(Exception):
    """ผู้ใช้ยกเลิกงาน; แยกจาก error เพื่อไม่แสดงว่าโมเดลเสีย"""


def check_cancel(cancel: CancelCheck = None) -> None:
    if cancel is not None and cancel():
        raise AnalysisCancelled("Analysis cancelled")
