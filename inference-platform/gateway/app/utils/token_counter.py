"""Token counting utilities for quota management."""
from typing import List, Dict, Any, Optional
import tiktoken


class TokenCounter:
    """Counts tokens for various models."""
    
    # Model to encoding mapping
    MODEL_ENCODINGS = {
        "qwen": "cl100k_base",  # Use GPT-4 encoding as approximation
        "text2sql": "cl100k_base",
        "default": "cl100k_base"
    }
    
    def __init__(self):
        """Initialize token counter with cached encodings."""
        self._encodings = {}
    
    def _get_encoding(self, model: str) -> tiktoken.Encoding:
        """Get or create encoding for a model."""
        encoding_name = self.MODEL_ENCODINGS.get(model, self.MODEL_ENCODINGS["default"])
        
        if encoding_name not in self._encodings:
            self._encodings[encoding_name] = tiktoken.get_encoding(encoding_name)
        
        return self._encodings[encoding_name]
    
    def count_tokens(self, text: str, model: str = "default") -> int:
        """
        Count tokens in a text string.
        
        Args:
            text: The text to count tokens for
            model: The model name (for model-specific encoding)
            
        Returns:
            Number of tokens
        """
        if not text:
            return 0
        
        encoding = self._get_encoding(model)
        return len(encoding.encode(text))
    
    def count_messages_tokens(self, messages: List[Dict[str, Any]], model: str = "default") -> int:
        """
        Count tokens in a list of chat messages.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: The model name
            
        Returns:
            Total number of tokens including message formatting overhead
        """
        encoding = self._get_encoding(model)
        
        # Tokens for message formatting (approximate)
        # Each message has: <|im_start|>role\ncontent<|im_end|>
        tokens_per_message = 4
        tokens_per_name = 1
        
        num_tokens = 0
        for message in messages:
            num_tokens += tokens_per_message
            
            for key, value in message.items():
                if isinstance(value, str):
                    num_tokens += len(encoding.encode(value))
                    if key == "name":
                        num_tokens += tokens_per_name
        
        # Add tokens for assistant reply priming
        num_tokens += 3
        
        return num_tokens
    
    def estimate_completion_tokens(self, max_tokens: Optional[int], default: int = 512) -> int:
        """
        Estimate completion tokens.
        
        Args:
            max_tokens: Maximum tokens requested
            default: Default estimate if max_tokens not specified
            
        Returns:
            Estimated completion tokens
        """
        if max_tokens:
            return min(max_tokens, 4096)  # Cap at reasonable limit
        return default


# Global token counter instance
token_counter = TokenCounter()


def count_tokens(text: str, model: str = "default") -> int:
    """Convenience function to count tokens."""
    return token_counter.count_tokens(text, model)


def count_chat_tokens(messages: List[Dict[str, Any]], model: str = "default") -> int:
    """Convenience function to count chat message tokens."""
    return token_counter.count_messages_tokens(messages, model)
