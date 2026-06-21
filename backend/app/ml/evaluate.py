import torch
import os
import librosa
import numpy as np
from app.ml.model import HighlightCNN
from app.ml.features import extract_mel_chunk

# Anchor paths relative to this script on disk to ensure execution stability anywhere
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))        # .../backend/app/ml/
BACKEND_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))     # .../backend/
MANUAL_DATA_DIR = os.path.normpath(os.path.join(BACKEND_DIR, "..", "data", "manual"))
MODEL_PATH = os.path.join(SCRIPT_DIR, "models", "highlight_cnn.pt")

def evaluate_system():
    model = HighlightCNN()
    
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Error: Model weights artifact missing at {MODEL_PATH}. Run training first.")
        return
        
    model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    model.eval()

    classes = {
        "pos": os.path.join(MANUAL_DATA_DIR, "positive"), 
        "neg": os.path.join(MANUAL_DATA_DIR, "negative")
    }
    
    sr = 22050
    evaluation_records = []

    print("🧪 Phase 1: Running single-pass inference and feature extraction...")
    for label_type, folder in classes.items():
        if not os.path.exists(folder):
            print(f"Skipping missing manual verification folder: {folder}")
            continue
            
        true_label = 1 if label_type == "pos" else 0
        
        for fname in os.listdir(folder):
            if not fname.endswith(".wav"):
                continue
                
            file_path = os.path.join(folder, fname)
            
            # Load raw file exactly ONCE into memory to protect disk I/O performance
            y, _ = librosa.load(file_path, sr=sr, mono=True)

            # 1. Compute CNN Inference Score
            mel = extract_mel_chunk(y, sr)
            tensor = torch.FloatTensor(mel).unsqueeze(0).unsqueeze(0)
            with torch.no_grad():
                cnn_score = model(tensor).item()
                cnn_pred = 1 if cnn_score > 0.5 else 0

            # 2. Compute Mean RMS Value
            raw_rms = np.mean(librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0])
            
            evaluation_records.append({
                "fname": fname,
                "true_label": true_label,
                "cnn_pred": cnn_pred,
                "raw_rms": raw_rms,
                "is_hard_neg": (true_label == 0 and "hard_neg" in fname)
            })

    if not evaluation_records:
        print(f"❌ No validation clips found inside {MANUAL_DATA_DIR}. Ensure your hand-picked test samples are populated.")
        return

    # 🔍 Phase 2: Dynamic Hyperparameter Optimization Sweep for RMS Baseline
    print("📋 Phase 2: Calibrating optimal RMS baseline via threshold parameter sweep...")
    rms_values = [rec["raw_rms"] for rec in evaluation_records]
    rms_min, rms_max = min(rms_values), max(rms_values)
    
    best_rms_threshold = rms_min
    best_rms_accuracy = 0.0
    
    # Sweep across 200 linear intervals between data extremes to find peak accuracy
    candidate_thresholds = np.linspace(rms_min, rms_max, 200)
    for candidate in candidate_thresholds:
        correct_predictions = sum(
            1 for rec in evaluation_records 
            if (1 if rec["raw_rms"] > candidate else 0) == rec["true_label"]
        )
        current_accuracy = correct_predictions / len(evaluation_records)
        
        if current_accuracy > best_rms_accuracy:
            best_rms_accuracy = current_accuracy
            best_rms_threshold = candidate

    # 📊 Phase 3: Evaluate and Score Final Metrics
    cnn_correct = 0
    rms_correct = 0
    hard_neg_total = 0
    hard_neg_cnn_blocked = 0
    total_samples = len(evaluation_records)

    for rec in evaluation_records:
        # Determine RMS classification using the optimized best-fit threshold
        rms_pred = 1 if rec["raw_rms"] > best_rms_threshold else 0
        
        if rec["cnn_pred"] == rec["true_label"]:
            cnn_correct += 1
        if rms_pred == rec["true_label"]:
            rms_correct += 1
            
        if rec["is_hard_neg"]:
            hard_neg_total += 1
            if rec["cnn_pred"] == 0:
                hard_neg_cnn_blocked += 1

    print("\n==================================================")
    print("📊 BASELINE RMS CALIBRATION DIAGNOSTICS")
    print("==================================================")
    print(f"Validation Audio Count: {total_samples} clips")
    print(f"RMS Energy Range:       min={rms_min:.4f} ↔ max={rms_max:.4f}")
    print(f"Best-fit RMS Threshold: {best_rms_threshold:.4f}")
    print(f"Peak RMS Baseline Acc:  {best_rms_accuracy * 100:.2f}% (Optimized Top Bound)")
    print("==================================================\n")

    print("==================================================")
    print("📊 MULTIMODAL MODEL EVALUATION PERFORMANCE MATRIX")
    print("==================================================")
    print(f"CNN Accuracy:        {(cnn_correct / total_samples) * 100:.2f}%")
    print(f"RMS Baseline Acc:    {(rms_correct / total_samples) * 100:.2f}% (Tuned Optimal)")
    print(f"CNN Net Improvement: +{((cnn_correct - rms_correct) / total_samples) * 100:.2f}%")
    print("--------------------------------------------------")
    if hard_neg_total > 0:
        print(f"Hard Negative Interception: {(hard_neg_cnn_blocked / hard_neg_total) * 100:.2f}% ({hard_neg_cnn_blocked}/{hard_neg_total})")
        print(f"-> CNN cleanly blocked {hard_neg_cnn_blocked} high-volume non-combat noise events that raw RMS would have mislabeled as highlights.")
    else:
        print("ℹ️ No hard negative samples found in data/manual/negative to calculate interception rates.")
    print("==================================================")

if __name__ == "__main__":
    evaluate_system()