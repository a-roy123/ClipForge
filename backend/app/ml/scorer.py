import numpy as np
from app.core.config import get_settings

settings = get_settings()


def smooth(scores: np.ndarray, window: int = 3) -> np.ndarray:
    """
    Applies a rolling average convolution kernel to smooth out noisy,
    single-frame signal spikes across temporal windows.
    """

    # Example:
    # Raw scores:
    # [0.1, 0.2, 0.9, 0.2, 0.1]
    #
    # The 0.9 might just be a random spike.
    #
    # Smoothing averages nearby values together so the final
    # highlight score changes more gradually over time.
    #
    # Result might look like:
    # [0.15, 0.4, 0.43, 0.4, 0.15]

    kernel = np.ones(window) / window

    return np.convolve(scores, kernel, mode="same")


def combine_scores(
    rms: np.ndarray,
    cnn: np.ndarray,
    motion: np.ndarray,
    mask: np.ndarray
) -> np.ndarray:
    """
    Combines independent multimodal feature signals using semantic gating
    and binary killcam/score-screen suppression.

    RMS + Motion determine HOW exciting something is.

    CNN determines WHAT KIND of exciting it is.

    Death mask removes moments where the player is dead,
    watching killcam, or viewing post-game screens.
    """

    # All arrays must have the same length.
    #
    # Example:
    #
    # rms     = 600 values
    # cnn     = 598 values
    # motion  = 600 values
    # mask    = 599 values
    #
    # Trim everything to the shortest length so indexing stays aligned.

    min_len = min(len(rms), len(cnn), len(motion), len(mask))

    rms, cnn, motion, mask = (
        rms[:min_len],
        cnn[:min_len],
        motion[:min_len],
        mask[:min_len]
    )

    # ----------------------------------------------------
    # STEP 1: Build base excitement score
    # ----------------------------------------------------
    #
    # RMS:
    # "How loud is the game?"
    #
    # Motion:
    # "How much action is happening?"
    #
    # Example:
    #
    # rms = 0.8
    # motion = 0.7
    #
    # base_activity ≈ 1.5
    #
    # This answers:
    #
    # "Something exciting seems to be happening."

    base_activity = (
        (settings.rms_weight * rms)
        + (settings.motion_weight * motion)
    )

    # ----------------------------------------------------
    # STEP 2: CNN semantic gate
    # ----------------------------------------------------
    #
    # CNN outputs:
    #
    # 0.0 -> doesn't sound like a highlight
    # 1.0 -> definitely sounds like a highlight
    #
    # We convert:
    #
    # 0.0 -> 0.5
    # 1.0 -> 1.0
    #
    # This means:
    #
    # CNN can REDUCE confidence,
    # but cannot completely destroy a clip.
    #
    # Example:
    #
    # base_activity = 1.4
    #
    # cnn = 0.0
    # gate = 0.5
    # final = 0.7
    #
    # cnn = 1.0
    # gate = 1.0
    # final = 1.4
    #
    # Think of CNN as a quality-control filter.
    #
    # RMS + Motion:
    # "Something happened."
    #
    # CNN:
    # "Was it actually a highlight?"

    semantic_gate = 0.5 + (cnn * 0.5)

    # ----------------------------------------------------
    # STEP 3: Apply death mask
    # ----------------------------------------------------
    #
    # mask values:
    #
    # 1.0 = player alive
    # 0.0 = player dead / killcam / scoreboard
    #
    # Multiplication makes dead moments disappear.
    #
    # Example:
    #
    # score = 1.3
    # mask = 0
    #
    # final = 0

    combined = base_activity * semantic_gate * mask

    # Smooth final output so highlight scores
    # don't jump wildly between seconds.

    return smooth(combined)


def find_highlight_windows(
    scores: np.ndarray,
    clip_duration: int,
    max_highlights: int,
    min_threshold: float,
    suppress_radius: int = 30
) -> list[dict]:
    """
    Finds the best highlight clips from the final score array.

    Input:
    [0.1, 0.2, 0.8, 1.2, 1.5, 1.3, 0.7, ...]

    Output:
    Best scoring clip windows.
    """

    # ----------------------------------------------------
    # Special case:
    # Video shorter than desired clip length.
    # ----------------------------------------------------
    #
    # Example:
    #
    # 10-second video
    # 15-second clip target
    #
    # Just return the entire video.

    if len(scores) <= clip_duration:
        return [{
            "start": 0,
            "end": len(scores),
            "score": float(np.mean(scores)) if len(scores) > 0 else 0.0,
            "low_confidence": True
        }]

    scores_copy = scores.copy()

    windows = []

    low_confidence = False

    # ----------------------------------------------------
    # Find top N highlights
    # ----------------------------------------------------
    #
    # Example:
    #
    # max_highlights = 5
    #
    # We'll repeatedly:
    #
    # 1. Find best clip
    # 2. Save it
    # 3. Remove nearby overlap
    # 4. Find next best clip

    for _ in range(max_highlights):

        best_start = 0
        best_score = -1

        # ------------------------------------------------
        # Sliding window search
        # ------------------------------------------------
        #
        # Imagine:
        #
        # scores:
        #
        # [0.2,0.3,1.0,1.1,1.2,0.4,0.2]
        #
        # Clip length = 3
        #
        # Window 1:
        # [0.2,0.3,1.0]
        #
        # Window 2:
        # [0.3,1.0,1.1]
        #
        # Window 3:
        # [1.0,1.1,1.2]
        #
        # etc...
        #
        # Pick whichever window has the
        # largest total score.

        for i in range(len(scores_copy) - clip_duration):

            window_score = float(
                np.sum(scores_copy[i:i + clip_duration])
            )

            if window_score > best_score:
                best_score = window_score
                best_start = i

        avg_score = (
            best_score / clip_duration
            if clip_duration > 0
            else 0
        )

        # ------------------------------------------------
        # Confidence check
        # ------------------------------------------------
        #
        # If score is weak,
        # still return a clip,
        # but mark it as low confidence.

        if avg_score < min_threshold:
            low_confidence = True

        # ------------------------------------------------
        # Add context padding
        # ------------------------------------------------
        #
        # If action starts at second 50,
        # user probably wants to see
        # a few seconds BEFORE the action.
        #
        # Add:
        #
        # 3 seconds before
        # 3 seconds after

        windows.append({
            "start": max(0, best_start - 3),
            "end": best_start + clip_duration + 3,
            "score": avg_score,
            "low_confidence": low_confidence,
        })

        # ------------------------------------------------
        # Non-Maximum Suppression (NMS)
        # ------------------------------------------------
        #
        # Prevent duplicate highlights.
        #
        # Example:
        #
        # Teamfight spans seconds 100-120.
        #
        # Without suppression:
        #
        # Clip 1 = 100-115
        # Clip 2 = 102-117
        # Clip 3 = 104-119
        #
        # Same highlight 3 times.
        #
        # Instead:
        #
        # Zero out nearby scores after selecting
        # a highlight so future clips must come
        # from different parts of the match.

        current_radius = (
            suppress_radius
            if len(scores_copy) > (suppress_radius * 2)
            else len(scores_copy) // 4
        )

        suppress_start = max(
            0,
            best_start - current_radius
        )

        suppress_end = min(
            len(scores_copy),
            best_start + clip_duration + current_radius
        )

        scores_copy[suppress_start:suppress_end] = 0

        # ------------------------------------------------
        # Stop if everything has been suppressed.
        # ------------------------------------------------

        if scores_copy.max() == 0:
            break

    # Return highest scoring clips first.

    return sorted(
        windows,
        key=lambda w: w["score"],
        reverse=True
    )