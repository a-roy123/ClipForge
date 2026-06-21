import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, random_split
import librosa
import numpy as np
import os
from app.ml.model import HighlightCNN
from app.ml.features import extract_mel_chunk

# Anchor all paths to this script's own location on disk, not the current
# working directory. This makes the script work identically whether you run
# it as `python app/ml/train.py` from backend/, `python train.py` from
# app/ml/, or any other invocation style.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))        # .../backend/app/ml/
BACKEND_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))     # .../backend/
DATA_DIR = os.path.normpath(os.path.join(BACKEND_DIR, "..", "data", "labeled"))  # .../ClipForge/data/labeled
MODELS_DIR = os.path.join(SCRIPT_DIR, "models")                 # .../backend/app/ml/models


class AudioDataset(Dataset):
    def __init__(self, data_dir: str, sr: int = 22050):
        self.samples = []
        self.sr = sr

        # Crawl weakly supervised directory trees
        for label, folder in [(1, "positive"), (0, "negative")]:
            folder_path = os.path.join(data_dir, folder)
            if not os.path.exists(folder_path):
                continue
            for fname in os.listdir(folder_path):
                if fname.endswith(".wav"):
                    self.samples.append((os.path.join(folder_path, fname), label))

        print(f"Dataset: {len(self.samples)} total samples loaded.")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]

        # Load raw 2-second audio frame slice
        y, _ = librosa.load(path, sr=self.sr, mono=True)

        # --- Online Augmentation: Dynamic Gain Scaling ---
        gain = np.random.uniform(0.7, 1.3)
        y = y * gain

        # --- Online Augmentation: Gaussian Noise Injection ---
        noise = np.random.randn(len(y)) * 0.005
        y = y + noise

        # Transform augmented waveform into normalized Mel-spectrogram
        mel = extract_mel_chunk(y, self.sr)

        # Reshape to channel-first tensor format -> (1, 64, 44)
        tensor = torch.FloatTensor(mel).unsqueeze(0)
        return tensor, torch.FloatTensor([label])


def train():
    print(f"Loading training data from: {DATA_DIR}")
    dataset = AudioDataset(DATA_DIR)

    n_total = len(dataset)
    if n_total == 0:
        print(f"Error: No training samples found at {DATA_DIR}. Run the labeling script first.")
        return

    # Strictly partition dataset into 80% Train / 10% Val / 10% Test blocks
    n_train = int(0.8 * n_total)
    n_val = int(0.1 * n_total)
    n_test = n_total - n_train - n_val
    train_ds, val_ds, test_ds = random_split(dataset, [n_train, n_val, n_test])

    print(f"Split: {n_train} train / {n_val} val / {n_test} test")

    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=32)

    model = HighlightCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.BCELoss()

    best_val_acc = 0.0
    print("\nCommencing CNN optimization loop across 20 epochs...")

    for epoch in range(20):
        model.train()
        for x, y in train_loader:
            optimizer.zero_grad()
            pred = model(x)
            loss = criterion(pred, y)
            loss.backward()
            optimizer.step()

        # Validation evaluation phase
        model.eval()
        correct = total = 0
        with torch.no_grad():
            for x, y in val_loader:
                pred = model(x)
                predicted = (pred > 0.5).float()
                correct += (predicted == y).sum().item()
                total += y.size(0)

        val_acc = correct / total if total > 0 else 0.0
        print(f"Epoch {epoch+1}/20 — Val Accuracy: {val_acc:.3f}")

        # Dynamic checkpointing: only save weights when validation accuracy improves
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            os.makedirs(MODELS_DIR, exist_ok=True)
            artifact_path = os.path.join(MODELS_DIR, "highlight_cnn.pt")

            torch.save(model.state_dict(), artifact_path)
            print(f"  Saved new best model checkpoint ({val_acc:.3f}) -> {artifact_path}")

    print(f"\nTraining complete. Peak Validation Accuracy: {best_val_acc:.3f}")
    if best_val_acc < 0.65:
        print("WARNING: Val accuracy below 65%. Consider setting CNN_WEIGHT=0.1 in your .env configuration.")


if __name__ == "__main__":
    train()