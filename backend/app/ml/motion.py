import cv2
import numpy as np


def compute_motion_and_mask(video_path: str) -> tuple:
    """
    Extract two gameplay signals from a video:

    1. motion_delta
       Measures unusual visual activity (motion spikes).
       High values often correspond to:
           - Team fights
           - Explosions
           - Fast camera turns
           - Ultimates

    2. death_mask
       Indicates whether the player is alive.

           1.0 = alive
           0.0 = dead / killcam / post-match scoreboard

    These signals will later be combined with audio features to help
    identify highlight-worthy moments.

    IMPORTANT:
    prev_gray is updated on EVERY frame.

    Optical flow works best when comparing adjacent frames.
    If we only updated once per second, motion vectors would become
    extremely noisy because objects may have moved too far between frames.
    """

    # Open video file for frame-by-frame reading.
    cap = cv2.VideoCapture(video_path)

    # Determine video frame rate.
    # Example:
    #     60 FPS = 60 frames per second.
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Sample approximately once per second.
    #
    # Example:
    #     FPS = 60
    #     frame_interval = 60
    #
    # Every 60th frame will contribute one motion/death score.
    frame_interval = max(1, int(fps))

    # Stores raw optical flow magnitude values.
    raw_motion = []

    # Stores alive/dead state per sampled second.
    death_mask = []

    # Previous grayscale frame used by optical flow.
    prev_gray = None

    frame_idx = 0

    while True:
        # Read next frame from video.
        ret, frame = cap.read()

        # End of video.
        if not ret:
            break

        # ---------------------------------------------------------
        # MOTION PREPROCESSING
        # ---------------------------------------------------------

        # Downscale frame to reduce computation.
        #
        # Motion detection does not require full 1080p resolution.
        # Smaller images = significantly faster optical flow.
        frame_small = cv2.resize(frame, (320, 180))

        # Convert to grayscale.
        #
        # Optical flow only needs brightness information.
        # Color information adds cost without helping motion detection.
        gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)

        # Process approximately once per second.
        if frame_idx % frame_interval == 0:

            # -----------------------------------------------------
            # DEATH MASK DETECTION
            # -----------------------------------------------------

            # Normalize every frame to 1920x1080.
            #
            # Different recordings may have:
            #     720p
            #     1080p
            #     letterboxing
            #
            # Resizing ensures HUD elements always appear in the
            # same relative location.
            frame_norm = cv2.resize(frame, (1920, 1080))

            # Overwatch death screen places a dark translucent
            # "RESPAWN IN X" overlay in the upper-right corner.
            #
            # We crop that region and measure brightness.
            #
            # If the region becomes very dark:
            #     likely dead / killcam / scoreboard
            #
            # If the region remains bright:
            #     likely alive
            ymin, ymax = int(1080 * 0.00), int(1080 * 0.12)
            xmin, xmax = int(1920 * 0.85), int(1920 * 1.00)

            respawn_region = frame_norm[ymin:ymax, xmin:xmax]

            # Average brightness of the region.
            brightness = np.mean(respawn_region)

            # Threshold chosen experimentally.
            #
            # Dark region -> dead
            # Bright region -> alive
            death_mask.append(
                0.0 if brightness < 40 else 1.0
            )

            # -----------------------------------------------------
            # MOTION DETECTION
            # -----------------------------------------------------

            if prev_gray is not None:

                # Optical Flow:
                #
                # Estimates how far every pixel moved between
                # consecutive frames.
                #
                # Examples:
                #     Standing still        -> small motion
                #     Team fight           -> large motion
                #     Fast camera flick    -> large motion
                #     Explosion            -> large motion
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray,
                    gray,
                    None,
                    0.5,
                    3,
                    15,
                    3,
                    5,
                    1.2,
                    0
                )

                # Convert x/y motion vectors into a magnitude.
                #
                # Think:
                #     "How much movement happened?"
                mag, _ = cv2.cartToPolar(
                    flow[..., 0],
                    flow[..., 1]
                )

                # Average motion strength across the entire frame.
                raw_motion.append(
                    float(np.mean(mag))
                )

            else:
                # First frame has no previous frame to compare against.
                raw_motion.append(0.0)

        # IMPORTANT:
        #
        # Always update previous frame.
        #
        # Optical flow should compare adjacent frames,
        # not frames separated by an entire second.
        prev_gray = gray

        frame_idx += 1

    cap.release()

    # Guard against broken or empty videos.
    if len(raw_motion) == 0:
        return (
            np.array([], dtype=np.float32),
            np.array([], dtype=np.float32)
        )

    # -------------------------------------------------------------
    # MOTION SPIKE DETECTION
    # -------------------------------------------------------------

    raw = np.array(raw_motion, dtype=np.float32)

    # Build a 5-second rolling average.
    #
    # This represents the "normal" motion level
    # surrounding each moment.
    pad_width = 2

    raw_padded = np.pad(
        raw,
        pad_width,
        mode="edge"
    )

    kernel = np.ones(5) / 5

    rolling_mean = np.convolve(
        raw_padded,
        kernel,
        mode="valid"
    )

    # Compute deviation from local baseline.
    #
    # Large value:
    #     unusual motion spike
    #
    # Small value:
    #     normal gameplay movement
    delta = np.abs(raw - rolling_mean)

    # Normalize to [0,1].
    #
    # Makes it easier to combine with:
    #     RMS audio scores
    #     CNN scores
    #     future highlight signals
    max_val = delta.max()

    if max_val > 0:
        delta = delta / max_val

    return (
        delta,
        np.array(death_mask, dtype=np.float32)
    )