import librosa
import numpy as np
# FEATURES.PY
#
# Purpose:
# Convert raw audio into ML-friendly features.
#
# Pipeline:
# Raw Audio
#     ↓
# RMS Scores (how loud is each second?)
#     ↓
# Mel Spectrogram (what does the audio sound like?)
#     ↓
# CNN Highlight Classifier
#
# RMS helps locate potentially exciting moments.
# Mel Spectrograms help the neural network understand
# the type of sound occurring during those moments.
import librosa
import numpy as np


def extract_rms_scores(audio_path: str, sr: int = 22050) -> np.ndarray:
    """
    Compute a normalized loudness score for each second of audio.

    RMS (Root Mean Square) is essentially a loudness meter:
    - Quiet moments -> low RMS
    - Loud moments (gunshots, explosions, yelling) -> high RMS

    Returns:
        np.ndarray of shape (n_seconds,)
        Values normalized to [0, 1].
    """

    # Load audio as a single mono channel.
    # y = raw waveform samples (millions of amplitude values).
    y, _ = librosa.load(audio_path, sr=sr, mono=True)

    # Compute RMS on small sliding windows throughout the audio.
    # This gives us a loudness measurement many times per second.
    rms_frames = librosa.feature.rms(
        y=y,
        frame_length=2048,
        hop_length=512
    )[0]

    # Determine roughly how many RMS measurements occur per second.
    frames_per_second = sr // 512

    # Number of complete seconds available in the audio.
    n_seconds = len(rms_frames) // frames_per_second

    # Average all RMS measurements that belong to the same second.
    # Result:
    #   second 1 -> loudness score
    #   second 2 -> loudness score
    #   ...
    rms_per_second = np.array([
        np.mean(
            rms_frames[
                i * frames_per_second:
                (i + 1) * frames_per_second
            ]
        )
        for i in range(n_seconds)
    ])

    # Normalize scores to [0, 1].
    # Makes thresholds and ML features easier to work with.
    max_val = rms_per_second.max()

    if max_val == 0:
        return rms_per_second

    return rms_per_second / max_val


def extract_mel_chunk(y_chunk: np.ndarray, sr: int = 22050) -> np.ndarray:
    """
    Convert a chunk of audio into a Mel Spectrogram.

    Think of a Mel Spectrogram as an image:
        Rows    = frequency bands (low pitch -> high pitch)
        Columns = time
        Values  = sound energy

    This representation is much easier for a CNN to learn from than
    raw waveform samples.

    Returns:
        np.ndarray with fixed shape (64, 44)

    Why fixed size?
        Neural networks expect a consistent input shape.
        Every audio chunk must become the exact same dimensions.
    """

    # Convert waveform -> Mel Spectrogram.
    #
    # n_mels=64:
    #     Split frequency space into 64 bands.
    #
    # hop_length=512:
    #     Controls how frequently we sample along time.
    mel = librosa.feature.melspectrogram(
        y=y_chunk,
        sr=sr,
        n_mels=64,
        n_fft=1024,
        hop_length=512
    )

    # Convert raw power values into decibels.
    # Human hearing is logarithmic, so dB is a more useful scale.
    mel_db = librosa.power_to_db(mel, ref=np.max)

    # Normalize spectrogram values to [0, 1].
    # Neural networks generally train and infer better on normalized data.
    mel_norm = (
        mel_db - mel_db.min()
    ) / (
        mel_db.max() - mel_db.min() + 1e-8
    )

    # CNN expects shape (64, 44).
    #
    # If the spectrogram is too short:
    #     pad with zeros on the right.
    #
    # If the spectrogram is too long:
    #     crop extra columns.
    #
    # This guarantees every example has identical dimensions.
    if mel_norm.shape[1] < 44:
        mel_norm = np.pad(
            mel_norm,
            ((0, 0), (0, 44 - mel_norm.shape[1]))
        )
    else:
        mel_norm = mel_norm[:, :44]

    # Final output:
    #   64 frequency bands
    #   44 time slices
    #
    # This acts like an image that can be fed directly into a CNN.
    return mel_norm