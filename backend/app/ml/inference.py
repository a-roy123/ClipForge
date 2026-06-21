import torch
import os
import numpy as np
from app.ml.model import HighlightCNN
from app.ml.features import extract_mel_chunk
import librosa

_model = None

def get_model() -> HighlightCNN:
    """
    Singleton provider pattern for the HighlightCNN. Loads weights lazily
    on first invocation to minimize worker memory footprints during startup.
    """
    global _model
    if _model is None:
        model = HighlightCNN()
        artifact_path = os.path.join(os.path.dirname(__file__), "models", "highlight_cnn.pt")
        
        if not os.path.exists(artifact_path):
            raise FileNotFoundError(
                f"❌ Model weights artifact missing at {artifact_path}. "
                "Ensure training completed successfully before invoking inference."
            )
            
        model.load_state_dict(torch.load(artifact_path, map_location="cpu"))
        model.eval()
        _model = model
    return _model

def compute_cnn_scores(audio_path: str, sr: int = 22050) -> np.ndarray:
    """
    Chunks an incoming audio track into 2-second windows with a 1-second hop frame interval.
    Executes a forward pass through the CNN for each window to return an array of sequential
    per-second highlight probability scores.
    """
    model = get_model()
    y, _ = librosa.load(audio_path, sr=sr, mono=True)
    scores = []
    
    # Calculate the number of 1-second step iterations possible across the signal duration
    for i in range(len(y) // sr - 1):
        chunk = y[i * sr : (i + 2) * sr]
        if len(chunk) < 2 * sr:
            scores.append(0.0)
            continue
            
        # Extract features and scale into standardized (64, 44) mel frequency shape
        mel = extract_mel_chunk(chunk, sr)
        
        # Shape tensor format: add explicit Batch and Channel dimensions -> (1, 1, 64, 44)
        tensor = torch.FloatTensor(mel).unsqueeze(0).unsqueeze(0)
        
        with torch.no_grad():
            prob = model(tensor).item()
        scores.append(prob)
        
    return np.array(scores, dtype=np.float32)