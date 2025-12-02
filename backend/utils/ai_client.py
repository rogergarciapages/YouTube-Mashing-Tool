import os
import logging
import google.generativeai as genai
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)

class AIClient:
    def __init__(self):
        self.api_key = settings.GOOGLE_AI_API_KEY
        if not self.api_key:
            logger.warning("Google AI API key not found. AI summaries will not work.")
            self.available = False
        else:
            genai.configure(api_key=self.api_key)
            self.available = True
            try:
                # Test the API connection with gemini-pro (more widely available)
                model = genai.GenerativeModel("gemini-pro")
                logger.info("Google AI Studio connection established")
            except Exception as e:
                logger.error(f"Failed to connect to Google AI Studio: {e}")
                self.available = False
    
    def generate_summary(self, keywords: str) -> str:
        """
        Generate a short, engaging summary from keywords using Google AI Studio
        """
        if not self.available:
            return self._fallback_summary(keywords)
        
        try:
            # Create a prompt for generating engaging summaries
            prompt = f"""
            Create a very short, engaging 1-sentence description (max 60 characters) 
            for a video clip based on these keywords: {keywords}
            
            The description should be:
            - Engaging and attention-grabbing
            - Under 60 characters
            - Relevant to the keywords
            - Suitable for video subtitles
            
            Return only the description, nothing else.
            """
            
            model = genai.GenerativeModel("gemini-pro")
            response = model.generate_content(prompt)
            
            summary = response.text.strip()
            
            # Ensure the summary is within character limit
            if len(summary) > 60:
                summary = summary[:57] + "..."
            
            logger.debug(f"Generated AI summary: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"AI summary generation failed: {e}")
            return self._fallback_summary(keywords)
    
    def _fallback_summary(self, keywords: str) -> str:
        """
        Fallback summary when AI is not available
        """
        if not keywords:
            return "Video clip"
        
        # Simple keyword-based summary
        words = keywords.split()[:3]  # Take first 3 words
        summary = " ".join(words)
        
        # Ensure it's within character limit
        if len(summary) > 60:
            summary = summary[:57] + "..."
        
        return summary
    
    def is_available(self) -> bool:
        """
        Check if AI service is available
        """
        return self.available
