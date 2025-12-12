import pytest
from unittest.mock import MagicMock, patch
from video_processor import VideoProcessor
from config.settings import settings

class TestVideoProcessor:
    @pytest.fixture
    def processor(self):
        with patch('video_processor.AIClient') as mock_ai, \
             patch('video_processor.VideoUtils') as mock_utils:
            return VideoProcessor()

    def test_calculate_text_position(self, processor):
        # Test bottom (default)
        assert processor._calculate_text_position("bottom") == "x=w*0.075:y=h*0.8-text_h/2"
        # Test top
        assert processor._calculate_text_position("top") == "x=w*0.075:y=50"
        # Test center
        assert processor._calculate_text_position("center") == "x=w*0.075:y=(h-text_h)/2"

    def test_wrap_text_youtube(self, processor):
        text = "This is a very long text that should be wrapped accordingly"
        # Youtube format (wide) - should allow more chars
        wrapped = processor._wrap_text(text, 36, "youtube")
        assert len(wrapped.split('\n')) <= 3
        
    def test_wrap_text_shorts(self, processor):
        text = "This is a very long text that should be wrapped accordingly"
        # Shorts format (narrow) - should break more often
        wrapped = processor._wrap_text(text, 36, "shorts")
        assert len(wrapped.split('\n')) >= 3

    def test_generate_summary_fallback(self, processor):
        # Mock class provided in fixture
        processor.ai_client.generate_summary.side_effect = Exception("AI Error")
        
        clip_req = MagicMock()
        clip_req.custom_text = None
        clip_req.keywords = "keyword " * 20 # Long keywords
        
        summary = processor._generate_summary(clip_req)
        assert "..." in summary
        assert len(summary) <= 53 # 50 chars + ...

    @pytest.mark.skip(reason="Partial mocking of os/shutil is flaky in test environment")
    def test_cleanup_logic(self, processor):
        import os
        # Use platform specific path
        test_path = os.path.join("videos", "temp", "clip_0", "final.mp4")
        
        with patch('os.path.exists') as mock_exists, \
             patch('shutil.rmtree') as mock_rmtree, \
             patch('os.listdir') as mock_listdir:
            
            mock_exists.return_value = True
            mock_listdir.return_value = [] 
            
            processor._cleanup_temp_files([test_path])
            
            # verify rmtree was called
            assert mock_rmtree.called
