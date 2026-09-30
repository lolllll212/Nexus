"""Unit test for the Multimodal Perception Bridge skill."""

import pytest
from nexus.application.tools.multimodal_perception import MultimodalPerceptionBridge
from nexus.infrastructure.adapters.execution.extended_tools import _process_multimodal_media


def test_image_decomposition_basic():
    # Synthetic small 1x1 GIF or PNG
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    result = MultimodalPerceptionBridge.analyze_image_bytes(png_bytes, filename="test_diagram.png")
    assert result["media_type"] == "image"
    assert "dimensions" in result
    assert "color_palette" in result
    assert "spatial_grid" in result
    assert "top_left" in result["spatial_grid"]
    assert "center" in result["spatial_grid"]
    assert "prompt_injection_block" in result
    assert "<<< MULTIMODAL PERCEPTION BRIDGE" in result["prompt_injection_block"]


def test_video_decomposition_basic():
    video_bytes = b"fake_mp4_header_and_sample_frame_buffer_bytes"
    result = MultimodalPerceptionBridge.analyze_video_bytes(video_bytes, filename="demo_sequence.mp4")
    assert result["media_type"] == "video"
    assert "keyframes" in result
    assert len(result["keyframes"]) >= 3
    assert "audio_transcript" in result
    assert "prompt_injection_block" in result
    assert "<<< MULTIMODAL PERCEPTION BRIDGE: HIGH-DENSITY VIDEO REPRESENTATION >>>" in result["prompt_injection_block"]


@pytest.mark.asyncio
async def test_tool_handler_execution():
    res = await _process_multimodal_media({
        "source": "mock_dashboard.png",
        "media_type": "image",
        "question": "What is in the center of the screen?",
    })
    assert res["status"] == "success"
    assert res["media_type"] == "image"
    assert "prompt_injection_block" in res
    assert "answer" in res
    assert len(res["answer"]) > 20
