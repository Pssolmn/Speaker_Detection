"""Rank character candidates from one set of visual features.

This is the baseline visual-only matcher.  It answers "which reference character
looks most similar?"; it does not yet decide who is speaking.
"""

from src.core.models import Candidate, CharacterDatabase, ColorSimilarity, VisualFeatures
from src.vision.color_similarity import compare_color_features

def rank_visual_candidates(
    query_features: VisualFeatures | None,
    database: CharacterDatabase,
    top_k: int = 3,
) -> list[Candidate]:
    """Return character candidates sorted by their visual similarity.

    Args:
        query_features: Features from one already-cropped hair/head ROI.
        database: Mapping returned by ``load_character_database()``.
        top_k: Number of best reference-image scores to average per character.

    The averaged score makes a character with several reference images less
    dependent on one unusually bright, dark, or badly cropped image.
    """
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    if query_features is None:
        return []

    candidates: list[Candidate] = []
    for character_name, references in database.items():
        scores: list[ColorSimilarity] = []
        for reference in references:
            reference_features = reference.get("features")
            if reference_features is None:
                continue
            scores.append(compare_color_features(query_features, reference_features))

        if not scores:
            continue

        best_scores = sorted(scores, key=lambda score: score["score"], reverse=True)[:top_k]
        visual_score = sum(score["score"] for score in best_scores) / len(best_scores)

        candidates.append(
            Candidate(
                character_name=character_name,
                visual_score=round(visual_score, 4),
                # Remaining scores stay None until the speaker pipeline evaluates them.
            )
        )

    return sorted(candidates, key=lambda candidate: candidate.visual_score, reverse=True)
