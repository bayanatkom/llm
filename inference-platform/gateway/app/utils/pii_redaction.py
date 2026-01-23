"""PII redaction utilities for log sanitization."""
import re
from typing import Any, Dict


class PIIRedactor:
    """Redacts personally identifiable information from text."""
    
    # Regex patterns for common PII
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    PHONE_PATTERN = re.compile(r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b')
    SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
    CREDIT_CARD_PATTERN = re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b')
    IP_ADDRESS_PATTERN = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
    
    # Replacement tokens
    EMAIL_REPLACEMENT = '[EMAIL]'
    PHONE_REPLACEMENT = '[PHONE]'
    SSN_REPLACEMENT = '[SSN]'
    CC_REPLACEMENT = '[CC]'
    IP_REPLACEMENT = '[IP]'
    
    @classmethod
    def redact_text(cls, text: str) -> str:
        """
        Redact PII from a text string.
        
        Args:
            text: The text to redact
            
        Returns:
            Text with PII replaced by tokens
        """
        if not text:
            return text
        
        # Redact in order of specificity
        text = cls.EMAIL_PATTERN.sub(cls.EMAIL_REPLACEMENT, text)
        text = cls.SSN_PATTERN.sub(cls.SSN_REPLACEMENT, text)
        text = cls.CREDIT_CARD_PATTERN.sub(cls.CC_REPLACEMENT, text)
        text = cls.PHONE_PATTERN.sub(cls.PHONE_REPLACEMENT, text)
        # Note: IP addresses might be needed for debugging, so optional
        # text = cls.IP_ADDRESS_PATTERN.sub(cls.IP_REPLACEMENT, text)
        
        return text
    
    @classmethod
    def redact_dict(cls, data: Dict[str, Any], keys_to_redact: set = None) -> Dict[str, Any]:
        """
        Redact PII from dictionary values.
        
        Args:
            data: Dictionary to redact
            keys_to_redact: Specific keys to always redact (e.g., 'password', 'api_key')
            
        Returns:
            Dictionary with PII redacted
        """
        if keys_to_redact is None:
            keys_to_redact = {'password', 'api_key', 'token', 'secret', 'authorization'}
        
        redacted = {}
        for key, value in data.items():
            # Always redact sensitive keys
            if key.lower() in keys_to_redact:
                redacted[key] = '[REDACTED]'
            elif isinstance(value, str):
                redacted[key] = cls.redact_text(value)
            elif isinstance(value, dict):
                redacted[key] = cls.redact_dict(value, keys_to_redact)
            elif isinstance(value, list):
                redacted[key] = [
                    cls.redact_text(item) if isinstance(item, str)
                    else cls.redact_dict(item, keys_to_redact) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                redacted[key] = value
        
        return redacted


# Convenience function
def redact_pii(text: str) -> str:
    """Redact PII from text."""
    return PIIRedactor.redact_text(text)
