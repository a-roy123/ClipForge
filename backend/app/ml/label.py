import librosa
import numpy as np
import soundfile as sf
import os
import sys

def label_recording(wav_path: str, output_dir: str, sr: int = 22050):
    print(f"Processing {wav_path}...")
    y, _ = librosa.load(wav_path, sr=sr, mono=True)

    frames_per_sec = sr // 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    n_seconds = len(rms) // frames_per_sec
    rms_per_sec = np.array([
        np.mean(rms[i * frames_per_sec:(i + 1) * frames_per_sec])
        for i in range(n_seconds - 2)
    ])

    # Dynamic weak supervision cuts per VOD profile
    pos_threshold = np.percentile(rms_per_sec, 85)
    neg_threshold = np.percentile(rms_per_sec, 40)

    os.makedirs(f"{output_dir}/positive", exist_ok=True)
    os.makedirs(f"{output_dir}/negative", exist_ok=True)

    pos_count = neg_count = hard_neg_count = 0
    total_duration_seconds = len(rms_per_sec)
    cutoff_second = total_duration_seconds - 90

    for i, score in enumerate(rms_per_sec[:-2]):
        filename = f"{os.path.basename(wav_path).replace('.wav', '')}_{i}.wav"

        # --- Hard Negative Isolation Layer ---
        # The final 90 seconds are almost always post-match cards, progression screens,
        # or lobby queues. Isolating these provides excellent negative mining material.
        if i >= cutoff_second:
            # Downsample post-game windows to avoid drowning the dataset in redundant silence
            if (i - cutoff_second) % 3 != 0:
                continue
            chunk = y[i * sr:(i + 2) * sr]
            if len(chunk) >= 2 * sr:
                sf.write(f"{output_dir}/negative/hard_neg_{filename}", chunk, sr)
                hard_neg_count += 1
            continue

        # --- Standard Mid-Match Slicing ---
        chunk = y[i * sr:(i + 2) * sr]
        if len(chunk) < 2 * sr:
            continue
            
        if score >= pos_threshold:
            sf.write(f"{output_dir}/positive/{filename}", chunk, sr)
            pos_count += 1
        elif score <= neg_threshold:
            sf.write(f"{output_dir}/negative/{filename}", chunk, sr)
            neg_count += 1

    print(f"  Positive: {pos_count} | Negative: {neg_count} | Hard Negative: {hard_neg_count}")
    return pos_count, neg_count + hard_neg_count

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python label.py <raw_dir> <output_dir>")
        sys.exit(1)
        
    raw_dir, output_dir = sys.argv[1], sys.argv[2]
    total_pos = total_neg = 0
    
    for fname in os.listdir(raw_dir):
        if fname.endswith(".wav"):
            p, n = label_recording(os.path.join(raw_dir, fname), output_dir)
            total_pos += p
            total_neg += n
            
    print(f"\n==================================================")
    print(f"Total Combined Output Summary:")
    print(f"  Positive Samples: {total_pos}")
    print(f"  Negative Samples: {total_neg}")
    print(f"==================================================")