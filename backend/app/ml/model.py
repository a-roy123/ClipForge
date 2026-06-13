import torch
import torch.nn as nn

class HighlightCNN(nn.Module):
    """
    CNN that takes a mel-spectrogram image and predicts how likely
    the audio is to contain a highlight-worthy moment.

    Input:
        (1, 64, 44)

    Think of this as:
        64 frequency bands
        44 time slices

    The CNN's job is to learn audio patterns such as:
        - Team fights
        - Ultimate abilities
        - Explosions
        - Gunfire bursts
        - Exciting moments

    Output:
        Single probability between 0 and 1

        0.0 = very unlikely highlight
        1.0 = very likely highlight
    """

    def __init__(self):
        super().__init__()

        self.features = nn.Sequential(

            # LAYER 1
            #
            # Input:
            #     (1, 64, 44)
            #
            # Conv2d creates 16 learned pattern detectors.
            #
            # During training, the network may learn detectors for:
            #     - Explosions
            #     - Voice lines
            #     - Gunfire
            #     - Other audio textures
            #
            # ReLU removes negative activations.
            #
            # MaxPool shrinks the image by 2x.
            #
            # Output:
            #     (16, 32, 22)

            nn.Conv2d(1, 16, 3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(2),

            # LAYER 2
            #
            # Input:
            #     (16, 32, 22)
            #
            # The network now combines simpler patterns from Layer 1
            # into more meaningful patterns.
            #
            # Examples:
            #     Explosion + Voice Line
            #     = Ultimate Ability
            #
            #     Gunfire + Multiple Frequencies
            #     = Team Fight
            #
            # Output:
            #     (32, 16, 11)

            nn.Conv2d(16, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),

            # LAYER 3
            #
            # Input:
            #     (32, 16, 11)
            #
            # The network now looks for larger and more abstract
            # highlight-related audio patterns.
            #
            # Examples:
            #     - Ultimate sequence
            #     - Team fight sequence
            #     - High-intensity combat
            #
            # Output:
            #     (64, 8, 5)

            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )

        self.classifier = nn.Sequential(

            # FLATTEN
            #
            # Converts:
            #
            #     (64, 8, 5)
            #
            # into:
            #
            #     2560 numbers
            #
            # These numbers represent everything the CNN learned
            # about the audio clip.

            nn.Flatten(),

            # FULLY CONNECTED LAYER
            #
            # Compresses 2560 learned features down to 128
            # important highlight-related features.
            #
            # Think:
            #
            #     Explosion detector
            #     Team fight detector
            #     Voice line detector
            #
            # get combined into a smaller summary representation.

            nn.Linear(64 * 8 * 5, 128),

            nn.ReLU(),

            # DROPOUT
            #
            # Randomly disables 30% of neurons during training.
            #
            # Prevents the model from memorizing training data.
            #
            # Forces the network to learn more general patterns.

            nn.Dropout(0.3),

            # FINAL DECISION LAYER
            #
            # Converts the 128 learned features into
            # a single score.

            nn.Linear(128, 1),

            # SIGMOID
            #
            # Converts any number into a value between 0 and 1.
            #
            # Examples:
            #
            #     0.05 -> probably not a highlight
            #     0.50 -> uncertain
            #     0.95 -> very likely a highlight

            nn.Sigmoid()
        )

    def forward(self, x):
        """
        Forward pass.

        Flow:

            Mel Spectrogram
                    ↓
              Feature Layers
                    ↓
            Learned Audio Features
                    ↓
              Classifier
                    ↓
            Highlight Probability

        Example:

            Input:
                (1, 64, 44)

            Output:
                0.87

            Meaning:
                87% confidence this audio resembles
                a highlight moment.
        """
        return self.classifier(self.features(x))