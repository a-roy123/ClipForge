import pytest
import numpy as np
import cv2
from unittest.mock import patch, MagicMock

from app.ml.features import extract_rms_scores, extract_mel_chunk
from app.ml.motion import compute_motion_and_mask
from app.ml.scorer import combine_scores, find_highlight_windows

# ============================================================================
# 1. AUDIO FEATURE EXTRACTION TESTS
# ============================================================================

@patch("app.ml.features.librosa.load")
def test_rms_scores_shape(mock_load):
    """Verify that a 10-second audio stream results in exactly 10 RMS downsamples."""
    sr = 22050
    synthetic_signal = np.random.uniform(-1.0, 1.0, sr * 10)
    mock_load.return_value = (synthetic_signal, sr)
    
    rms_scores = extract_rms_scores("mock_path.wav", sr=sr)
    assert len(rms_scores) == 10


@patch("app.ml.features.librosa.load")
def test_rms_scores_normalized(mock_load):
    """Verify that the extracted RMS energy values are strictly bounded between 0 and 1."""
    sr = 22050
    synthetic_signal = np.random.uniform(-0.5, 0.5, sr * 5)
    mock_load.return_value = (synthetic_signal, sr)
    
    rms_scores = extract_rms_scores("mock_path.wav", sr=sr)
    assert np.all(rms_scores >= 0.0)
    assert np.all(rms_scores <= 1.0)


@patch("app.ml.features.librosa.load")
def test_rms_scores_silence_no_div_by_zero(mock_load):
    """Pure silence (all zeros) must not produce NaN from division by a zero max."""
    sr = 22050
    synthetic_signal = np.zeros(sr * 5)
    mock_load.return_value = (synthetic_signal, sr)
    
    rms_scores = extract_rms_scores("mock_path.wav", sr=sr)
    assert not np.any(np.isnan(rms_scores))
    assert np.all(rms_scores == 0)


def test_mel_chunk_shape():
    """Verify that a 2-second audio sample scales precisely into a (64, 44) CNN tensor shape."""
    sr = 22050
    synthetic_chunk = np.random.uniform(-1.0, 1.0, sr * 2)
    
    mel_spectrogram = extract_mel_chunk(synthetic_chunk, sr=sr)
    assert mel_spectrogram.shape == (64, 44)


def test_mel_chunk_short_audio_pads_to_shape():
    """A chunk shorter than 2 seconds should still pad to exactly (64, 44)."""
    sr = 22050
    short_chunk = np.random.uniform(-1.0, 1.0, sr // 2)  # 0.5 seconds
    
    mel_spectrogram = extract_mel_chunk(short_chunk, sr=sr)
    assert mel_spectrogram.shape == (64, 44)


def test_mel_chunk_values_normalized():
    """Mel-spectrogram values should be normalized into [0, 1] after dB scaling."""
    sr = 22050
    synthetic_chunk = np.random.uniform(-1.0, 1.0, sr * 2)
    
    mel_spectrogram = extract_mel_chunk(synthetic_chunk, sr=sr)
    assert mel_spectrogram.min() >= 0.0
    assert mel_spectrogram.max() <= 1.0


# ============================================================================
# 2. VIDEO MOTION AND DEATH MASK TESTS
# ============================================================================

@patch("app.ml.motion.cv2.VideoCapture")
def test_motion_scores_shape(mock_video_capture):
    """Verify optical flow processing array sizes match targeted frame sampling intervals."""
    mock_cap = MagicMock()
    mock_video_capture.return_value = mock_cap
    mock_cap.get.return_value = 30.0  # 30fps
    
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # 60 frames -> samples at frame_idx 0 and 30 -> 2 checkpoints
    mock_cap.read.side_effect = [(True, dummy_frame)] * 60 + [(False, None)]
    
    motion_delta, death_mask = compute_motion_and_mask("mock_video.mp4")
    assert len(motion_delta) == 2
    assert len(death_mask) == 2


@patch("app.ml.motion.cv2.VideoCapture")
def test_motion_empty_video_returns_empty_arrays(mock_video_capture):
    """If cap.read() returns False immediately, both arrays should be empty (no crash)."""
    mock_cap = MagicMock()
    mock_video_capture.return_value = mock_cap
    mock_cap.get.return_value = 30.0
    mock_cap.read.return_value = (False, None)
    
    motion_delta, death_mask = compute_motion_and_mask("mock_video.mp4")
    assert len(motion_delta) == 0
    assert len(death_mask) == 0


@patch("app.ml.motion.cv2.VideoCapture")
def test_death_mask_detects_dark_respawn_region(mock_video_capture):
    """
    A frame with a dark top-right corner (RESPAWN IN overlay, brightness < 40)
    should mark death_mask as 0.0 for that second.
    """
    mock_cap = MagicMock()
    mock_video_capture.return_value = mock_cap
    mock_cap.get.return_value = 30.0
    
    # Bright frame overall, but darken the top-right corner specifically
    frame = np.full((1080, 1920, 3), 200, dtype=np.uint8)
    ymin, ymax = int(1080 * 0.00), int(1080 * 0.12)
    xmin, xmax = int(1920 * 0.85), int(1920 * 1.00)
    frame[ymin:ymax, xmin:xmax] = 10  # dark respawn overlay
    
    # Need 2 sampled frames (frame 0 and frame 30) so optical flow runs at least once
    mock_cap.read.side_effect = [(True, frame)] * 31 + [(False, None)]
    
    motion_delta, death_mask = compute_motion_and_mask("mock_video.mp4")
    assert len(death_mask) == 2
    assert death_mask[0] == 0.0
    assert death_mask[1] == 0.0


@patch("app.ml.motion.cv2.VideoCapture")
def test_death_mask_alive_when_corner_bright(mock_video_capture):
    """A uniformly bright frame (no respawn overlay) should mark death_mask as 1.0 (alive)."""
    mock_cap = MagicMock()
    mock_video_capture.return_value = mock_cap
    mock_cap.get.return_value = 30.0
    
    frame = np.full((1080, 1920, 3), 200, dtype=np.uint8)  # uniformly bright
    mock_cap.read.side_effect = [(True, frame)] * 31 + [(False, None)]
    
    motion_delta, death_mask = compute_motion_and_mask("mock_video.mp4")
    assert len(death_mask) == 2
    assert death_mask[0] == 1.0
    assert death_mask[1] == 1.0


# ============================================================================
# 3. SCORE AGGREGATION TESTS
# ============================================================================

def test_combine_scores_length():
    """Ensure score fusion honors array alignment constraints and outputs equal lengths."""
    length = 50
    rms = np.random.rand(length)
    cnn = np.random.rand(length)
    motion = np.random.rand(length)
    mask = np.ones(length)
    
    combined = combine_scores(rms, cnn, motion, mask)
    assert len(combined) == length


def test_combine_scores_death_mask_zeroes_output():
    """When the death mask is entirely 0, the combined score must be entirely 0."""
    length = 50
    rms = np.ones(length)
    cnn = np.ones(length)
    motion = np.ones(length)
    mask = np.zeros(length)
    
    combined = combine_scores(rms, cnn, motion, mask)
    assert np.all(combined == 0)


def test_combine_scores_cnn_amplifies_not_adds():
    """
    With identical rms/motion but cnn=0 vs cnn=1, the cnn=1 case should score
    higher because the semantic gate multiplies (0.5 to 1.0x), not adds.
    """
    length = 50
    rms = np.full(length, 0.5)
    motion = np.full(length, 0.5)
    mask = np.ones(length)
    cnn_low = np.zeros(length)
    cnn_high = np.ones(length)
    
    combined_low = combine_scores(rms, cnn_low, motion, mask)
    combined_high = combine_scores(rms, cnn_high, motion, mask)
    
    # cnn_high should be exactly 2x cnn_low (gate goes from 0.5 to 1.0)
    assert np.allclose(combined_high, combined_low * 2, atol=1e-5)


def test_combine_scores_mismatched_lengths_truncate_to_shortest():
    """Arrays of different lengths should be truncated to the shortest input."""
    rms = np.random.rand(60)
    cnn = np.random.rand(45)
    motion = np.random.rand(50)
    mask = np.ones(70)
    
    combined = combine_scores(rms, cnn, motion, mask)
    assert len(combined) == 45


# ============================================================================
# 4. NMS / WINDOW SELECTION TESTS
# ============================================================================

def test_find_windows_low_confidence():
    """Verify that all-zero arrays trigger windows flagged explicitly as low confidence."""
    scores = np.zeros(100)
    windows = find_highlight_windows(
        scores, clip_duration=10, max_highlights=2, min_threshold=0.3, suppress_radius=5
    )
    assert len(windows) > 0
    assert all(w["low_confidence"] is True for w in windows)


def test_find_windows_no_overlap():
    """Ensure Non-Maximum Suppression handles peaks cleanly with zero temporal overlapping."""
    scores = np.zeros(120)
    scores[15:25] = 1.0
    scores[80:90] = 1.0
    
    windows = find_highlight_windows(
        scores, clip_duration=10, max_highlights=2, min_threshold=0.3, suppress_radius=20
    )
    assert len(windows) == 2
    w1, w2 = windows[0], windows[1]
    assert (w1["end"] <= w2["start"]) or (w2["end"] <= w1["start"])


def test_find_windows_short_clip():
    """Verify that video timelines shorter than a clip block return the full asset safely."""
    scores = np.ones(12)  # 12 seconds total
    windows = find_highlight_windows(
        scores, clip_duration=30, max_highlights=1, min_threshold=0.3
    )
    assert len(windows) == 1
    assert windows[0]["start"] == 0
    assert windows[0]["end"] == 12
    assert windows[0]["low_confidence"] is True


def test_find_windows_respects_max_highlights():
    """Should never return more windows than max_highlights, even with a flat high score."""
    scores = np.ones(300)
    windows = find_highlight_windows(
        scores, clip_duration=20, max_highlights=3, min_threshold=0.1, suppress_radius=30
    )
    assert len(windows) <= 3


def test_find_windows_sorted_by_score_descending():
    """Returned windows should be sorted highest score first (index 0 = top highlight)."""
    scores = np.zeros(200)
    scores[10:30] = 0.5   # weaker peak
    scores[100:120] = 1.0  # stronger peak
    
    windows = find_highlight_windows(
        scores, clip_duration=20, max_highlights=2, min_threshold=0.1, suppress_radius=30
    )
    assert len(windows) == 2
    assert windows[0]["score"] >= windows[1]["score"]


def test_find_windows_padding_clamped_to_bounds():
    """Window padding (+-3 seconds) should not produce a negative start index."""
    scores = np.zeros(50)
    scores[0:10] = 1.0  # peak right at the start
    
    windows = find_highlight_windows(
        scores, clip_duration=10, max_highlights=1, min_threshold=0.1, suppress_radius=10
    )
    assert windows[0]["start"] >= 0