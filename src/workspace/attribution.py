"""เชื่อมหลักฐาน/แสดงชื่อจาก ID ล่าสุด ไม่เขียนชื่อซ้ำลงทุกแถว.

เสียง↔ภาพที่ระบบแนะนำยังไม่เป็น link ถาวรจนกว่าคนจะยืนยัน.
ภาพคนที่อยู่ในจอเพียงอย่างเดียวไม่ใช่หลักฐานว่าคนนั้นพูด.
"""

from collections import defaultdict
from bisect import bisect_left, bisect_right
import json
import re

from src.core.models import AttributionResult, SubtitleSegment


def _overlap(a, b):
    return max(0, min(a["end_ms"], b["end_ms"]) - max(a["start_ms"], b["start_ms"]))


def _speech_motion(voice, visual):
    """ใช้เฉพาะคู่เฟรมที่อยู่ใน speech turn ไม่ใช้ค่าเฉลี่ยปากทั้ง 8 วินาที."""
    duration = voice["end_ms"] - voice["start_ms"]
    activity = visual["evidence"].get("mouth_activity")
    if activity is None:
        # รอบเก่ายังเปิดได้ แต่ข้อมูลแบบเก่าไม่เลื่อนเป็นคู่มั่นใจสูง.
        motion = visual["evidence"].get("motion")
        if motion is not None and motion >= .15:
            return {"score": .25, "motion": motion, "coverage": _overlap(voice, visual) / duration,
                    "legacy": True, "pairs": 0}
        return None
    pairs = []
    for start, end, motion in activity.get("pairs", []):
        overlap = max(0, min(end, voice["end_ms"]) - max(start, voice["start_ms"]))
        if overlap >= (end - start) * .5:
            pairs.append((overlap, motion))
    covered = sum(pair[0] for pair in pairs)
    if len(pairs) < 3 or covered < min(350, duration * .4):
        return None
    motion = sum(length * value for length, value in pairs) / covered
    coverage = min(1., covered / duration)
    if motion < .08 or coverage < .2:
        return None  # ใบหน้าที่นิ่ง/อยู่ใน reaction shot ไม่ได้คะแนนจาก visibility อย่างเดียว
    score = .55 * min(1., motion / .45) + .3 * coverage + .15 * min(1., len(pairs) / 8)
    return {"score": score, "motion": motion, "coverage": coverage, "legacy": False, "pairs": len(pairs)}


def _subtitle_evidence(store, voices, media_id):
    """จับช่วงซับกับเสียงก่อน แล้วใช้ชื่อเฉพาะบรรทัดที่ระบุตัวละครชัดเจน.

    ชื่อทั่วไปจาก SRT ไม่ได้บอกตัวตนเอง: ต้องตรงกับชื่อกลุ่มภาพที่มีอยู่แบบหนึ่งต่อหนึ่ง
    และช่วงซับต้องมีเสียงเพียงกลุ่มเดียว. ไม่อ่านความหมายของข้อความหรือสร้าง link.
    """
    visuals = {item["id"]: item for item in store.profiles("visual") if item["count"]}
    by_name = defaultdict(list)
    for profile in visuals.values():
        name = " ".join(profile["name"].split()).casefold()
        if not re.fullmatch(r"ตัวละคร \d+", name):
            by_name[name].append(profile["id"])
    by_media = defaultdict(list)
    for voice in voices:
        by_media[voice["media_id"]].append(voice)
    # ช่วงเสียงเรียงเวลาไว้ครั้งเดียว; ซับยาวทั้งเรื่องไม่ต้องเทียบทุกบรรทัดกับทุกช่วงเสียง.
    indexes = {}
    for media, items in by_media.items():
        items.sort(key=lambda item: item["start_ms"])
        starts, latest_ends = [], []
        for item in items:
            starts.append(item["start_ms"])
            latest_ends.append(max(latest_ends[-1] if latest_ends else 0, item["end_ms"]))
        indexes[media] = items, starts, latest_ends
    votes = defaultdict(lambda: defaultdict(list))
    aligned = defaultdict(list)
    rows = store.rows("SELECT * FROM subtitles" + (" WHERE media_id=?" if media_id else "") +
                      " ORDER BY media_id,json_extract(segment,'$.start_ms'),segment_id",
                      (media_id,) if media_id else ())
    for row in rows:
        segment = json.loads(row["segment"])
        if row["manual_profile_id"]:
            target = row["manual_profile_id"] if row["manual_profile_id"] in visuals else None
            source = "ชื่อที่เลือกยืนยันในซับ"
        else:
            name = row["manual_name"] or segment.get("script_character")
            matches = by_name.get(" ".join(name.split()).casefold(), []) if name else []
            target = matches[0] if len(matches) == 1 else None
            source = "ชื่อที่แก้ในซับ" if row["manual_name"] else "ชื่อที่ระบุใน SRT"
        start, end = segment["start_ms"], segment["end_ms"]
        if end - start < 200:
            continue
        items, starts, latest_ends = indexes.get(row["media_id"], ([], [], []))
        first = bisect_right(latest_ends, start)
        last = bisect_left(starts, end)
        active = [(voice, _overlap(voice, {"start_ms": start, "end_ms": end}))
                  for voice in items[first:last]]
        active = [(voice, duration) for voice, duration in active if duration >= 100]
        identities = {voice["profile_id"] for voice, _ in active}
        if len(identities) != 1 or None in identities or any(voice["evidence"].get("overlap") for voice, _ in active):
            continue  # หลายเสียง/เสียงไม่ทราบกลุ่ม ห้ามนำชื่อหนึ่งบรรทัดไปปะทั้งกลุ่ม
        covered = []
        for voice, _ in active:
            covered.append((max(start, voice["start_ms"]), min(end, voice["end_ms"])))
        covered.sort()
        merged = []
        for left, right in covered:
            if merged and left <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
            else:
                merged.append((left, right))
        if sum(right - left for left, right in merged) < max(200, .4 * (end - start)):
            continue  # ซับอาจคลาดเวลา: ไม่ใช้เสียงสั้นที่เฉียดขอบบรรทัด
        voice, _ = max(active, key=lambda pair: pair[1])
        if segment["text"].strip():
            aligned[voice["id"]].append({"media_id": row["media_id"], "subtitle_id": row["segment_id"],
                                          "start_ms": start, "end_ms": end,
                                          "named": bool(row["manual_profile_id"] or row["manual_name"] or segment.get("script_character"))})
        if target is None:
            continue
        votes[voice["profile_id"]][target].append({
            "media_id": row["media_id"], "subtitle_id": row["segment_id"], "source": source,
            "voice_observation_id": voice["id"], "visual_observation_id": None,
            "start_ms": start, "end_ms": end, "score": 0.0, "margin": 0.0})
    return votes, aligned


def suggest_links(store, media_id=None):
    """จัดอันดับคู่เสียง-ภาพ พร้อมเหตุผลและหลักฐาน; ไม่เขียน links.

    score 0–1 เป็น heuristic ไม่ใช่ P(correct); เสียงซ้อน/ผู้สมัครสูสีต้องตรวจ.
    media_id=None รวมหลักฐานทั้งเรื่อง แต่ห้ามเทียบเวลาข้ามตอน.
    """
    visuals = defaultdict(list)
    for item in store.observations(media_id=media_id, kind="visual"):
        if item["profile_id"]:
            visuals[item["media_id"]].append(item)
    voices = store.observations(media_id=media_id, kind="voice")
    subtitle_votes, aligned_cues = _subtitle_evidence(store, voices, media_id)
    by_media = defaultdict(list)
    for item in voices:
        by_media[item["media_id"]].append(item)
    aggregates, voiced_turns = {}, defaultdict(int)
    for voice in voices:
        identifier = voice["profile_id"]
        if not identifier:
            continue
        voiced_turns[identifier] += 1
        if voice["evidence"].get("overlap") or any(
                other["id"] != voice["id"] and other["profile_id"] != identifier and _overlap(voice, other) >= 100
                for other in by_media[voice["media_id"]]):
            continue
        candidates = {}
        for visual in visuals[voice["media_id"]]:
            if _overlap(voice, visual) < min(350, (voice["end_ms"] - voice["start_ms"]) * .4):
                continue
            measurement = _speech_motion(voice, visual)
            if measurement and measurement["score"] > candidates.get(visual["profile_id"], {}).get("score", -1):
                candidates[visual["profile_id"]] = {**measurement, "visual_observation_id": visual["id"]}
        ranked = sorted(candidates.items(), key=lambda pair: pair[1]["score"], reverse=True)
        for index, (visual_id, measurement) in enumerate(ranked[:2]):
            margin = measurement["score"] - (ranked[1][1]["score"] if len(ranked) > 1 else 0) if index == 0 else 0
            key = (identifier, visual_id)
            entry = aggregates.setdefault(key, {"measurements": [], "examples": [], "wins": 0, "ties": 0})
            win = index == 0 and margin >= .12 and not measurement["legacy"]
            entry["wins"] += int(win)
            entry["ties"] += int(not win)
            entry["measurements"].append(measurement)
            entry["examples"].append({"media_id": voice["media_id"], "voice_observation_id": voice["id"],
                "visual_observation_id": measurement["visual_observation_id"],
                "start_ms": max(voice["start_ms"], next(v["start_ms"] for v in visuals[voice["media_id"]] if v["id"] == measurement["visual_observation_id"])),
                "end_ms": min(voice["end_ms"], next(v["end_ms"] for v in visuals[voice["media_id"]] if v["id"] == measurement["visual_observation_id"])),
                "score": measurement["score"], "margin": margin})
    results = []
    for (voice_id, visual_id), entry in aggregates.items():
        measurements = entry["measurements"]
        legacy = all(item["legacy"] for item in measurements)
        support = len(measurements)
        competing_wins = sum(value["wins"] for (voice, visual), value in aggregates.items() if voice == voice_id and visual != visual_id)
        consistency = entry["wins"] / max(1, entry["wins"] + competing_wins + entry["ties"])
        score = sum(item["score"] for item in measurements) / support
        score *= (.6 + .4 * min(1., entry["wins"] / 3)) * (.5 + .5 * consistency)
        if legacy:
            score = min(.25, sum(item["score"] for item in measurements) / support)
        reasons = [f"พบปากขยับตรงช่วงเสียง {entry['wins']}/{voiced_turns[voice_id]} ช่วง"]
        if entry["ties"]:
            reasons.append("มีช่วงที่หลักฐานน้อยหรือผู้สมัครสูสี")
        if competing_wins:
            reasons.append("กลุ่มเสียงเดียวมีหลักฐานไปคนละตัวละคร ควรตรวจ/แยกกลุ่ม")
        if legacy:
            reasons = ["ใช้ motion แบบเก่า — กดตรวจคู่ภาพ–เสียงเพื่อวัดตาม speech turn ก่อน"]
        cue_keys, unnamed_keys = set(), set()
        for example in entry["examples"]:
            for cue in aligned_cues.get(example["voice_observation_id"], ()):
                if cue["media_id"] == example["media_id"] and _overlap(cue, example) >= min(350, .4 * (cue["end_ms"] - cue["start_ms"])):
                    key = cue["media_id"], cue["subtitle_id"]
                    cue_keys.add(key)
                    if not cue["named"]:
                        unnamed_keys.add(key)
        if cue_keys:
            reasons.append(f"ช่วงเสียง/ภาพทับบทซับ {len(cue_keys)} บรรทัด (ยังไม่บอกว่าใครพูด)")
            if unnamed_keys and not legacy and entry["wins"]:
                score = min(1., score + min(.06, .02 * len(unnamed_keys)))
        named_targets = subtitle_votes.get(voice_id, {})
        named_conflict = len(named_targets) > 1 or bool(named_targets and visual_id not in named_targets)
        if len(named_targets) > 1:
            reasons.append("ชื่อที่ระบุในซับขัดกันสำหรับกลุ่มเสียงนี้ — ไม่ใช้ซับเพิ่มคะแนน")
        elif named_targets:
            named_id, cues = next(iter(named_targets.items()))
            if named_id == visual_id:
                reasons.append(f"ซับระบุชื่อตรงกัน {len(cues)} บรรทัด (ตรวจเวลาและฟังเสียงก่อนยืนยัน)")
                if legacy:
                    # ชื่อในซับเป็นหลักฐานคนละชนิดกับ motion รุ่นเก่า ไม่ยก motion เป็น lip-sync.
                    score = max(score, min(.49, .34 + .06 * len(cues)))
                else:
                    score = min(1., score + min(.18, .06 * len(cues)))
            else:
                reasons.append("ชื่อในซับชี้ไปตัวละครอื่น — ตรวจว่าซับ/กลุ่มเสียง/ภาพใดคลาดเคลื่อน")
                score = max(0., score - .12)
        results.append({"voice_id": voice_id, "visual_id": visual_id, "support": support,
            "reliable_support": entry["wins"], "motion": sum(item["motion"] for item in measurements) / support,
            "score": round(score, 4), "status": "suggestion_only", "legacy": legacy,
            "subtitle_support": len(named_targets.get(visual_id, [])), "cue_support": len(cue_keys),
            "evidence_kind": "av+subtitle" if len(named_targets) == 1 and visual_id in named_targets else "av",
            "level": "สูง" if score >= .75 and entry["wins"] >= 2 and not competing_wins and not named_conflict else "ปานกลาง" if score >= .45 else "ต่ำ",
            "reasons": reasons, "examples": sorted(entry["examples"], key=lambda item: -item["score"])[:8]})
    for voice_id, targets in subtitle_votes.items():
        if len(targets) != 1:
            continue  # ชื่อที่ขัดกันต้องให้คนแก้ ไม่สุ่มเลือกหนึ่งตัวละคร
        visual_id, cues = next(iter(targets.items()))
        if (voice_id, visual_id) in aggregates:
            continue
        score = min(.49, .34 + .06 * len(cues) + (.05 if any(item["source"] != "ชื่อที่ระบุใน SRT" for item in cues) else 0))
        reasons = [f"{cues[0]['source']} ตรงกับกลุ่มภาพ และมีเสียงกลุ่มเดียวทับเวลา {len(cues)} บรรทัด",
                   "ข้อเสนอจากซับเท่านั้น ยังไม่มีหลักฐานปากตรงเสียง; โปรดดู/ฟังก่อนผูก"]
        if any(item["voice_id"] == voice_id and item["reliable_support"] for item in results):
            reasons.append("หลักฐานปากเสนออีกตัวละครหนึ่ง — ตรวจความขัดแย้งก่อนยืนยัน")
        results.append({"voice_id": voice_id, "visual_id": visual_id, "support": len(cues),
            "reliable_support": 0, "subtitle_support": len(cues), "cue_support": 0, "motion": 0.0,
            "score": round(score, 4), "status": "suggestion_only", "legacy": False, "evidence_kind": "subtitle",
            "level": "ปานกลาง" if score >= .45 else "ต่ำ", "reasons": reasons,
            "examples": cues[:8]})
    return sorted(results, key=lambda item: (-item["score"], item["voice_id"], item["visual_id"]))


def subtitle_results(store, media_id):
    """คืน dataclass แบบเดิมเพื่อใช้ exporter เดิมได้ และ rename มีผลทุกครั้งที่อ่าน."""
    profiles = {item["id"]: item for item in store.profiles()}
    links = defaultdict(list)
    for item in store.rows("SELECT * FROM links"):
        links[item["voice_id"]].append(item["visual_id"])
    voices = store.observations(media_id=media_id, kind="voice")
    av_candidates = defaultdict(list)
    for suggestion in suggest_links(store, media_id):
        av_candidates[suggestion["voice_id"]].append({key: suggestion[key] for key in
            ("visual_id", "score", "level", "status", "reasons", "evidence_kind", "cue_support", "subtitle_support")})
    media_digest = store.db.execute("SELECT digest FROM media WHERE id=?", (media_id,)).fetchone()
    if media_digest is None:
        raise KeyError("Unknown media")
    segments, results = [], []
    # cue ID ไม่ใช่ลำดับแถว: เพิ่ม/แยกบรรทัดได้โดยไม่ทำ ID ของคำตอบแก้มือเปลี่ยน.
    for row in store.rows("SELECT * FROM subtitles WHERE media_id=? "
                          "ORDER BY json_extract(segment,'$.start_ms'),segment_id", (media_id,)):
        segment = SubtitleSegment(**json.loads(row["segment"]))
        segments.append(segment)
        active = [item for item in voices if _overlap(item, {"start_ms": segment.start_ms, "end_ms": segment.end_ms}) >= 100]
        identifiers = sorted({item["profile_id"] for item in active if item["profile_id"]})
        labels, resolved_ids = [], []
        for identifier in identifiers:
            # หลายตัวละครแชร์นักพากย์ได้: ถ้า link หลายปลายทาง ไม่เดาเลือกหนึ่งชื่อ
            target = links[identifier][0] if len(links[identifier]) == 1 else identifier
            if target not in resolved_ids:
                resolved_ids.append(target)
                labels.append(profiles[target]["name"])
        status = "PROPOSED" if labels else "UNKNOWN"
        if len(labels) > 1:
            status = "MULTIPLE_SPEAKERS"
        elif active and any(item["profile_id"] is None for item in active):
            status = "AMBIGUOUS"  # อย่าซ่อนเสียงอีกคนที่ระบบยังจัดกลุ่มไม่ได้
        manual = row["manual_name"]
        if row["manual_profile_id"]:
            manual_id = row["manual_profile_id"]
            target = links[manual_id][0] if len(links[manual_id]) == 1 else manual_id
            manual = profiles[target]["name"]
        if manual:
            status = "MANUAL"
        proposed = " / ".join(labels) or "UNKNOWN"
        if status == "AMBIGUOUS":
            proposed = "UNKNOWN"  # exporter ต้องไม่เอาคำตอบที่คลุมเครือไปแสดงเหมือนยืนยันแล้ว
        results.append(AttributionResult(segment.id, proposed, 0.0, status,
            {"workspace_id": store.db.execute("SELECT value FROM meta WHERE key='id'").fetchone()[0],
             "media_id": media_id, "profile_ids": resolved_ids, "voice_profile_ids": identifiers,
             "media_digest": media_digest[0], "manual_profile_id": row["manual_profile_id"],
             "observation_ids": [item["id"] for item in active],
             "av_candidates": {identifier: av_candidates[identifier] for identifier in identifiers},
             "identity_status": "confirmed_link" if identifiers and all(len(links[item]) == 1 for item in identifiers) else "unlinked",
             "note": "Anonymous AI groups / manually confirmed links; confidence is not calibrated"},
            manual_character=manual))
    return segments, results
