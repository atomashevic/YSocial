"""
Image annotation using multimodal LLMs.

Provides the Annotator class for generating textual descriptions of images
using vision-capable Large Language Models through the Autogen framework.
"""

import os
import tempfile
from io import BytesIO

import autogen
import requests
from autogen.agentchat.contrib.multimodal_conversable_agent import (
    MultimodalConversableAgent,
)
from PIL import Image


class Annotator(object):
    """
    Multimodal LLM-based image annotator.

    Uses vision-capable LLMs to generate natural language descriptions
    of images for accessibility and content understanding.
    """

    def __init__(self, llmv, llm_url=None):
        """
        Initialize the image annotator with a vision LLM.

        Args:
            llmv: Vision-capable LLM model name/identifier
            llm_url: Optional custom LLM server URL. If None, uses
                     environment variable or defaults based on backend.
        """

        self.config_list = None
        self.image_agent = None
        self.user_proxy = None

        if llm_url is not None:
            base_url = llm_url
        else:
            # Get base URL from environment variable (set by y_social.py)
            base_url = os.getenv("LLM_URL")
            if not base_url:
                # Fallback to determining URL based on LLM backend for backward compatibility
                llm_backend = os.getenv("LLM_BACKEND")
                if llm_backend == "vllm":
                    base_url = "http://127.0.0.1:8000/v1"
                elif llm_backend == "ollama":
                    base_url = "http://127.0.0.1:11434/v1"
                else:
                    return

        self.config_list = [
            {
                "model": llmv,
                "base_url": base_url,
                "timeout": 10000,
                "api_type": "open_ai",
                "api_key": "NULL",
                "price": [0, 0],
            }
        ]

        self.image_agent = MultimodalConversableAgent(
            name="image-explainer",
            max_consecutive_auto_reply=1,
            llm_config={
                "cache_seed": None,
                "config_list": self.config_list,
                "temperature": 0.5,
                "max_tokens": 300,
            },
            human_input_mode="NEVER",
        )

        self.user_proxy = autogen.AssistantAgent(
            name="User_proxy",
            max_consecutive_auto_reply=0,
        )

    def annotate(self, image):
        """
        Generate a natural language description of an image.

        Args:
            image: Image path or URL to describe

        Returns:
            String description of the image content, or None if description
            generation fails (e.g., model refuses, error occurs)
        """
        if self.image_agent is None or self.user_proxy is None:
            return None

        img_path = self._maybe_materialize_motion_preview(image)
        try:
            self.user_proxy.initiate_chat(
                self.image_agent,
                silent=True,
                message=(
                    "Describe the following image.\n"
                    "If the image looks like multiple frames from an animation, describe what changes across frames.\n"
                    "Write in english. "
                    f"<img {img_path}>"
                ),
            )
        finally:
            if img_path != image and os.path.exists(img_path):
                try:
                    os.unlink(img_path)
                except Exception:
                    pass

        try:
            res = self.image_agent.chat_messages[self.user_proxy][-1]["content"][-1][
                "text"
            ]
        except Exception:
            return None

        if "I'm sorry" in res:
            res = None
        return res

    def _sample_indices(self, total_count: int, max_samples: int = 4) -> list[int]:
        if total_count <= 1:
            return [0]
        sample_count = min(max_samples, total_count)
        if sample_count <= 1:
            return [0]
        indices = []
        for i in range(sample_count):
            idx = int(round((i * (total_count - 1)) / float(sample_count - 1)))
            indices.append(max(0, min(total_count - 1, idx)))
        return sorted(set(indices))

    def _build_frame_grid(self, frames: list[Image.Image]) -> str | None:
        if len(frames) <= 1:
            return None

        target_w = 384
        resized = []
        for frame in frames:
            w, h = frame.size
            if w <= 0 or h <= 0:
                continue
            scale = target_w / float(w)
            new_size = (target_w, max(1, int(h * scale)))
            resized.append(frame.resize(new_size))

        if len(resized) <= 1:
            return None

        cols = 2
        rows = (len(resized) + cols - 1) // cols
        pad = 6
        cell_w = max(frame.size[0] for frame in resized)
        cell_h = max(frame.size[1] for frame in resized)
        grid_w = cols * cell_w + (cols + 1) * pad
        grid_h = rows * cell_h + (rows + 1) * pad

        canvas = Image.new("RGB", (grid_w, grid_h), (245, 246, 248))
        for i, frame in enumerate(resized):
            row = i // cols
            col = i % cols
            x = pad + col * (cell_w + pad) + (cell_w - frame.size[0]) // 2
            y = pad + row * (cell_h + pad) + (cell_h - frame.size[1]) // 2
            canvas.paste(frame, (x, y))

        tmp = tempfile.NamedTemporaryFile(
            prefix="ysocial_anim_", suffix=".png", delete=False
        )
        tmp.close()
        canvas.save(tmp.name, format="PNG")
        return tmp.name

    def _maybe_materialize_motion_preview(self, image: str) -> str:
        preview = self._maybe_materialize_animation_preview(image)
        if preview != image:
            return preview
        return self._maybe_materialize_video_preview(image)

    def _maybe_materialize_animation_preview(self, image: str) -> str:
        if not isinstance(image, str) or not image:
            return image

        try:
            if image.startswith("http://") or image.startswith("https://"):
                resp = requests.get(image, timeout=10)
                resp.raise_for_status()
                content = BytesIO(resp.content)
                im = Image.open(content)
            elif os.path.exists(image):
                im = Image.open(image)
            else:
                return image

            n_frames = getattr(im, "n_frames", 1) or 1
            is_animated = bool(getattr(im, "is_animated", False)) or n_frames > 1
            if not is_animated or n_frames <= 1:
                return image

            indices = self._sample_indices(n_frames)
            frames = []
            for idx in indices:
                try:
                    im.seek(idx)
                except Exception:
                    continue
                frames.append(im.convert("RGB").copy())

            if len(frames) <= 1:
                return image

            grid = self._build_frame_grid(frames)
            return grid or image
        except Exception:
            return image

    def _looks_like_video_ref(self, ref: str) -> bool:
        lowered = (ref or "").split("?", 1)[0].split("#", 1)[0].lower()
        return lowered.endswith(".mp4")

    def _maybe_materialize_video_preview(self, image: str) -> str:
        if not isinstance(image, str) or not image:
            return image
        if not self._looks_like_video_ref(image):
            return image

        tmp_video_path = None
        try:
            video_ref = image
            if image.startswith("http://") or image.startswith("https://"):
                resp = requests.get(image, timeout=10, stream=True)
                resp.raise_for_status()
                tmp_video = tempfile.NamedTemporaryFile(
                    prefix="ysocial_video_", suffix=".mp4", delete=False
                )
                with tmp_video as out_file:
                    total = 0
                    for chunk in resp.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > 30 * 1024 * 1024:
                            return image
                        out_file.write(chunk)
                tmp_video_path = tmp_video.name
                video_ref = tmp_video_path
            elif not os.path.exists(image):
                return image

            try:
                import imageio.v3 as iio
            except Exception:
                return image

            try:
                iterator = iio.imiter(video_ref, plugin="ffmpeg")
            except Exception:
                try:
                    iterator = iio.imiter(video_ref)
                except Exception:
                    return image

            raw_frames = []
            for idx, frame in enumerate(iterator):
                if idx % 12 == 0:
                    raw_frames.append(frame)
                if idx >= 360 or len(raw_frames) >= 24:
                    break

            if len(raw_frames) <= 1:
                return image

            indices = self._sample_indices(len(raw_frames))
            frames = []
            for idx in indices:
                arr = raw_frames[idx]
                if getattr(arr, "ndim", 0) == 2:
                    arr = arr[..., None]
                if getattr(arr, "ndim", 0) != 3:
                    continue
                try:
                    frames.append(Image.fromarray(arr[:, :, :3]).convert("RGB"))
                except Exception:
                    continue

            if len(frames) <= 1:
                return image

            grid = self._build_frame_grid(frames)
            return grid or image
        except Exception:
            return image
        finally:
            if tmp_video_path and os.path.exists(tmp_video_path):
                try:
                    os.unlink(tmp_video_path)
                except Exception:
                    pass
