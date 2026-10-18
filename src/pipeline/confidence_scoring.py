"""รวมหลักฐานและกติกายอมรับแยกกัน เพื่อไม่ให้ภาพคล้ายอย่างเดียวกลายเป็นผู้พูด."""

from dataclasses import replace
from math import isfinite

from src.core import config
from src.core.models import AttributionResult, SubtitleSegment, TrackEvidence


def calculate_script_score(candidate_name: str, script_character: str | None) -> float | None:
    if not script_character or not script_character.strip():
        return None
    return float(candidate_name.strip().casefold() == script_character.strip().casefold())


def combine_scores(visual_score, active_speaker_score=None, script_score=None) -> float:
    """เฉลี่ยตามน้ำหนักเฉพาะข้อมูลที่มี; คืน score ไม่ใช่ calibrated probability"""
    pairs = [(visual_score, config.WEIGHT_FINAL_VISUAL),
             (active_speaker_score, config.WEIGHT_FINAL_ACTIVE_SPEAKER),
             (script_score, config.WEIGHT_FINAL_SCRIPT)]
    numerator = denominator = 0.0
    for value, weight in pairs:
        if not isfinite(weight) or weight < 0:
            raise ValueError("Weights must be finite and non-negative")
        if value is None:
            continue
        if not isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Evidence scores must be in [0, 1]")
        numerator += weight * value
        denominator += weight
    if denominator <= 0:
        raise ValueError("At least one positively weighted score is required")
    return numerator / denominator


def decide_attribution(
    segment: SubtitleSegment,
    tracks: list[TrackEvidence],
    evidence: dict,
) -> AttributionResult:
    """ตัดสินจากหลักฐานที่ pipeline รวบรวมแล้ว โดยไม่เปิดวิดีโอหรืออ่านไฟล์.

    ยอมรับอัตโนมัติต้องมีตัวตนหลายเฟรม, ปากขยับ, คะแนนและ margin เพียงพอ
    ชื่อสคริปต์ถูกเก็บไว้เสมอ แม้หลักฐานที่คำนวณได้จะขัดแย้ง
    """
    all_candidates = []
    plausible = []
    for track in tracks:
        ranked = sorted(track.candidates, key=lambda c: c.visual_score, reverse=True)
        for candidate in ranked:
            script = calculate_script_score(candidate.character_name, segment.script_character)
            scored = replace(candidate, track_id=track.track_id,
                             active_speaker_score=track.active_speaker_score, script_score=script,
                             final_score=combine_scores(candidate.visual_score, track.active_speaker_score, script))
            all_candidates.append(scored)
        if not ranked:
            continue
        top = ranked[0]
        identity_margin = top.visual_score - ranked[1].visual_score if len(ranked) > 1 else top.visual_score
        # ใช้คะแนนแบบไม่รวมชื่อสคริปต์หา conflict เพื่อไม่ให้ prior กลบข้อขัดแย้ง
        if (len(track.sample_times_ms) >= config.MIN_IDENTITY_FRAMES
                and top.visual_score >= config.MIN_VISUAL_SCORE
                and track.active_speaker_score is not None
                and track.active_speaker_score >= config.MIN_ACTIVE_SPEAKER_SCORE):
            # คู่แข่งที่ต่ำกว่า ACCEPT_SCORE เล็กน้อยยังต้องนับตอนตรวจ margin
            # และเก็บอันดับรองใน track เพื่อไม่ซ่อนความกำกวมของตัวตน
            for candidate in ranked:
                plausible.append((combine_scores(candidate.visual_score, track.active_speaker_score),
                                  candidate.character_name, track.track_id,
                                  candidate is top and identity_margin >= config.MIN_SCORE_MARGIN))

    all_candidates.sort(key=lambda c: c.final_score, reverse=True)
    # หลาย track ที่เป็นชื่อเดียวกันไม่ใช่คู่แข่งกัน; เก็บหลักฐานเต็มไว้ใน evidence
    best_by_name = {}
    for score, name, track_id, valid_identity in plausible:
        if name not in best_by_name or score > best_by_name[name][0]:
            best_by_name[name] = (score, track_id, valid_identity)
    winners = sorted(((score, name, track_id, valid_identity)
                      for name, (score, track_id, valid_identity) in best_by_name.items()), reverse=True)
    accepted = (bool(winners) and winners[0][0] >= config.ACCEPT_SCORE and winners[0][3]
                and (len(winners) == 1 or winners[0][0] - winners[1][0] >= config.MIN_SCORE_MARGIN))
    selected_name = winners[0][1] if accepted else None
    score = winners[0][0] if accepted else (all_candidates[0].final_score if all_candidates else 0.0)
    evidence = dict(evidence)
    evidence["policy"] = "colour+absolute_mouth_motion_v1 (uncalibrated)"
    evidence["selected_track_id"] = winners[0][2] if accepted else None
    evidence["reason"] = "sufficient_visual_and_motion_evidence" if accepted else "insufficient_or_ambiguous_evidence"
    if segment.script_character:
        conflict = accepted and calculate_script_score(selected_name, segment.script_character) == 0.0
        status = "SCRIPT_CONFLICT" if conflict else "SCRIPT_PROVIDED"
        name = segment.script_character
        if conflict:
            # score เดิมเป็นคะแนนของ selected_name (ที่ภาพตรวจพบ) ไม่ใช่ของชื่อสคริปต์ที่ใช้แสดงจริง
            # แสดงเป็น 0 เพื่อไม่ให้ชื่อที่ขัดแย้งกับหลักฐานดูมั่นใจเกินจริง
            score = 0.0
        evidence["reason"] = "script_visual_conflict" if conflict else "preserved_script_character"
    elif not tracks:
        status, name = "DEFAULT", config.DEFAULT_SPEAKER
        evidence["reason"] = "no_faces_in_successfully_read_frames"
    elif accepted:
        status, name = "ACCEPTED", selected_name
    else:
        status, name = "UNKNOWN", config.UNKNOWN_SPEAKER
    return AttributionResult(segment.id, name, float(score), status, evidence, all_candidates)
