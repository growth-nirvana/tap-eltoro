"""ElToro Authentication."""

from __future__ import annotations

import sys

from singer_sdk.authenticators import OAuthAuthenticator, SingletonMeta

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


# The SingletonMeta metaclass makes your streams reuse the same authenticator instance.
# If this behaviour interferes with your use-case, you can remove the metaclass.
class ElToroAuthenticator(OAuthAuthenticator, metaclass=SingletonMeta):
    """Authenticator class for ElToro."""

    @override
    @property
    def oauth_request_body(self) -> dict:
        """Define the OAuth request body for the ElToro API.

        Returns:
            A dict with the request body
        """
        body = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        
        # Add scope if provided
        if self.oauth_scopes:
            body["scope"] = self.oauth_scopes
            
        return body

    @override
    def is_token_valid(self) -> bool:
        """Check if the current token is valid with clock skew consideration.
        
        Returns:
            True if token is valid and not expiring within 60 seconds
        """
        if not self.access_token:
            return False
            
        if not hasattr(self, '_expires_at') or self._expires_at is None:
            return True  # No expiration info, assume valid
            
        # Refresh proactively if less than 60 seconds remaining
        current_time = time.time()
        return (self._expires_at - current_time) > 60

    @override  
    def update_access_token(self) -> None:
        """Update the access token and track expiration time."""
        super().update_access_token()
        
        # Track token expiration time for proactive refresh
        if hasattr(self, '_token_result') and self._token_result:
            expires_in = self._token_result.get('expires_in')
            if expires_in:
                self._expires_at = time.time() + int(expires_in)
            else:
                # Default to 5 minutes if no expires_in provided
                self._expires_at = time.time() + 300
