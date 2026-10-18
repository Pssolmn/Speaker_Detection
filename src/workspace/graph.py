"""Read-only graph data: cue membership and sparse voice-similarity links.

One small node per real subtitle. Similarity never confirms identity or changes
the database. Do not compare voice and face embeddings, or different models.
"""
from collections import defaultdict
from hashlib import sha256
import math

import numpy as np

from src.io.result_export import effective_character, format_srt_time
from src.workspace.appearance import canonical_profile, profile_color

MAX_CUES = 500


def build_graph(store, segments, results, *, threshold=.65, include_empty=False):
    profiles = {p["id"]: p for p in store.profiles()}
    media_id = results[0].evidence.get("media_id") if results else None
    observations = {o["id"]: o for o in store.observations(media_id=media_id, kind="voice")} if media_id else {}
    selected = np.linspace(0, len(segments) - 1, min(MAX_CUES, len(segments)), dtype=int) if segments else []
    nodes, groups, vectors, spaces = [], defaultdict(list), {}, {}
    for index in selected:
        segment, result = segments[index], results[index]
        manual = result.evidence.get("manual_profile_id")
        ids = result.evidence.get("profile_ids", [])
        if manual:
            group = canonical_profile(store, manual)
        elif result.manual_character:
            group = "manual:" + result.manual_character
        elif len(ids) == 1 and result.status != "AMBIGUOUS":
            group = ids[0]
        else:
            group = None  # unknowns are independent nodes, not a fictitious shared identity
        name = effective_character(segment, result) or "ยังไม่ทราบ"
        number = len(nodes)
        nodes.append({"key": f"cue:{media_id}:{segment.id}", "cue_id": segment.id,
            "profile_id": group if group in profiles else None, "group": group,
            "label": f"#{segment.id}", "color": profile_color(store, group) if group in profiles else "#8993A6",
            "text": f"#{segment.id} · {format_srt_time(segment.start_ms)} · {name}\n{segment.text}", "hub": False})
        if group:
            groups[group].append(number)
        active = [observations[o] for o in result.evidence.get("observation_ids", []) if o in observations]
        # No averaged "person" from overlapping speakers or mixed model spaces.
        valid = [o for o in active if o["features"] is not None and np.isfinite(o["features"]).all()
                 and np.linalg.norm(o["features"]) > 1e-8]
        signatures = {(o["model_key"], len(o["features"])) for o in valid}
        if valid and len(signatures) == 1 and len({o["profile_id"] for o in active}) <= 1 and not any(o["evidence"].get("overlap") for o in active):
            weights = [max(0, min(segment.end_ms, o["end_ms"]) - max(segment.start_ms, o["start_ms"])) for o in valid]
            if sum(weights):
                vector = np.average(np.stack([o["features"] for o in valid]), axis=0, weights=weights)
                if np.linalg.norm(vector) > 1e-8:
                    vectors[number] = vector / np.linalg.norm(vector)
                    spaces[number] = next(iter(signatures))
    cue_count = len(nodes)
    if include_empty:
        for p in profiles.values():
            if p["count"]:
                groups.setdefault(canonical_profile(store, p["id"]), [])
    edges, hubs = [], {}
    for group, members in groups.items():
        if not members and len(hubs) >= 60:
            continue
        p = profiles.get(group)
        name = p["name"] if p else group.removeprefix("manual:")
        hub = len(nodes)
        hubs[group] = hub
        nodes.append({"key": "group:" + group, "profile_id": group if p else None, "group": group,
            "label": name, "color": profile_color(store, group) if p else "#8993A6", "hub": True,
            "text": f"{name} · {len(members)} บรรทัดที่แสดง"})
        edges.extend((member, hub, "membership", 1.) for member in members)
    # k-nearest neighbours, capped at 3 per cue (union may yield more incident edges).
    # Cosine similarity is for graph exploration, NOT the attribution confidence.
    by_space = defaultdict(list)
    for number in vectors:
        by_space[spaces[number]].append(number)
    positions = np.zeros((len(nodes), 2), dtype=float)
    pairs = set()
    for numbers in by_space.values():
        matrix = np.stack([vectors[n] for n in numbers])
        similarities = matrix @ matrix.T
        np.fill_diagonal(similarities, -np.inf)
        for row, source in enumerate(numbers):
            for col in np.argsort(-similarities[row], kind="stable")[:3]:
                value = float(similarities[row, col])
                pair = tuple(sorted((source, numbers[col])))
                if value >= threshold and pair not in pairs:
                    pairs.add(pair)
                    edges.append((*pair, "similarity", min(1., value)))
        # PCA is only an initial seed. Interactive forces determine the final XY.
        centered = matrix - matrix.mean(axis=0)
        if len(numbers) > 1 and np.linalg.norm(centered) > 1e-8:
            u, s, _ = np.linalg.svd(centered, full_matrices=False)
            coords = u[:, :2] * s[:2]
            for axis in range(coords.shape[1]):
                if coords[np.argmax(np.abs(coords[:, axis])), axis] < 0:
                    coords[:, axis] *= -1
            positions[numbers, :coords.shape[1]] = coords * 260
    # A tiny deterministic separation lets identical embeddings be selected.
    # It is presentation only and must never be reported as a measured distance.
    for index, node in enumerate(nodes[:cue_count]):
        seed = int(sha256(node["key"].encode()).hexdigest()[:8], 16)
        angle = seed % 3600 / 3600 * math.tau
        radius = 22 if index in vectors else 230 + seed % 90
        positions[index] += [math.cos(angle) * radius, math.sin(angle) * radius]
    for group, hub in hubs.items():
        members = groups[group]
        if members:
            positions[hub] = positions[members].mean(axis=0)
        else:
            angle = hub * 2.39996
            positions[hub] = [math.cos(angle) * 340, math.sin(angle) * 340]
    return {"nodes": nodes, "edges": edges, "positions": positions, "hubs": hubs,
            "cue_count": cue_count, "total_cues": len(segments), "embedding_count": len(vectors)}


class ForceLayout:
    """Bounded, damped layout. UI drag pins a position but never changes membership."""
    def __init__(self, graph):
        self.positions = graph["positions"].copy()
        self.velocity = np.zeros_like(self.positions)
        self.edges = graph["edges"]
        self.sources = np.array([e[0] for e in self.edges], dtype=int)
        self.targets = np.array([e[1] for e in self.edges], dtype=int)
        self.rest = np.array([70 if e[2] == "membership" else 55 + (1 - e[3]) * 180 for e in self.edges])
        self.tension = np.array([.025 if e[2] == "membership" else .012 for e in self.edges])
        self.pinned = set()
        self.repulsion, self.attraction, self.gravity = 1., 1., 1.

    def step(self):
        points = self.positions
        if not len(points):
            return 0.
        # Hard cue cap bounds this temporary matrix (<= 1,000 nodes even if
        # each cue has its own group). Rendered connections remain sparse.
        delta = points[:, None, :] - points[None, :, :]
        distance2 = np.sum(delta * delta, axis=2) + 100
        strength = np.where(distance2 < 90000, 100 * self.repulsion / distance2, 0)
        np.fill_diagonal(strength, 0)
        forces = np.sum(delta * strength[:, :, None], axis=1) - points * (.003 * self.gravity)
        if self.edges:
            difference = points[self.targets] - points[self.sources]
            distance = np.maximum(1., np.linalg.norm(difference, axis=1))
            pull = difference * (((distance - self.rest) / distance) * self.tension * self.attraction)[:, None]
            np.add.at(forces, self.sources, pull)
            np.add.at(forces, self.targets, -pull)
        self.velocity = (self.velocity + np.clip(forces, -8, 8)) * .72
        self.velocity = np.clip(self.velocity, -7, 7)
        for index in self.pinned:
            self.velocity[index] = 0
        points += self.velocity
        return float(np.max(np.abs(self.velocity)))
