import hashlib
import hmac
import logging
import os


def verify_github_webhook(payload_body, signature_header, secret):
    """
    Verify that the payload was sent from GitHub by validating SHA256.
    
    Args:
        payload_body (bytes): The raw payload body from the webhook
        signature_header (str): The X-Hub-Signature-256 header from GitHub
        secret (str): The secret configured in GitHub webhook settings
    
    Returns:
        bool: True if the signature is valid, False otherwise
    """
    if not signature_header:
        logging.warning("No signature header found in webhook request")
        return False
    
    if not secret:
        logging.error("No webhook secret configured")
        return False
    
    # GitHub sends the signature as 'sha256=<hash>'
    if not signature_header.startswith('sha256='):
        logging.warning("Invalid signature header format")
        return False
    
    # Extract the hash part
    github_signature = signature_header[7:]
    
    # Create our own signature
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(github_signature, expected_signature)
    
    if not is_valid:
        logging.warning("Invalid webhook signature")
    
    return is_valid