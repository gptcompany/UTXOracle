"""
Test suite for JWT authentication.
Task T017: Write pytest tests for JWT lifecycle.
"""

import pytest
import time
from api.whale_auth import JWTAuthManager, auth_manager
from fastapi import HTTPException


class TestJWTAuthManager:
    """Test JWT authentication manager functionality."""

    def test_generate_token(self):
        """Test JWT token generation."""
        user_id = "test_user"
        result = auth_manager.generate_token(user_id)

        assert "token" in result
        assert result["token_type"] == "Bearer"
        assert result["expires_in"] == 3600  # 1 hour
        assert "expires_at" in result

    def test_validate_token(self):
        """Test token validation with valid token."""
        user_id = "test_user"
        permissions = ["whale_view", "whale_admin"]

        # Generate token
        result = auth_manager.generate_token(user_id, permissions)
        token = result["token"]

        # Validate token
        payload = auth_manager.validate_token(token)

        assert payload["user_id"] == user_id
        assert payload["permissions"] == permissions
        assert "exp" in payload
        assert "iat" in payload

    def test_validate_expired_token(self):
        """Test validation of expired token."""
        # Create a custom auth manager with very short expiry
        test_auth = JWTAuthManager()
        test_auth.expiry_hours = -1  # Already expired

        user_id = "test_user"
        result = test_auth.generate_token(user_id)
        token = result["token"]

        # Should raise HTTPException for expired token
        with pytest.raises(HTTPException) as exc_info:
            auth_manager.validate_token(token)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_validate_invalid_token(self):
        """Test validation of invalid token."""
        invalid_token = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            auth_manager.validate_token(invalid_token)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    def test_should_refresh(self):
        """Test token refresh check."""
        # Generate token
        user_id = "test_user"
        result = auth_manager.generate_token(user_id)
        token = result["token"]

        # Fresh token should not need refresh
        assert not auth_manager.should_refresh(token)

        # Create token that's about to expire
        test_auth = JWTAuthManager()
        test_auth.expiry_hours = 0.1  # 6 minutes
        test_auth.refresh_minutes = 5  # Refresh in last 5 minutes

        result = test_auth.generate_token(user_id)
        token = result["token"]

        # Wait a bit to get into refresh window
        time.sleep(1.5)  # 1.5 seconds should put us in refresh window

        # Should now need refresh
        assert test_auth.should_refresh(token)

    def test_refresh_token_success(self):
        """Test successful token refresh."""
        # Create token near expiry
        test_auth = JWTAuthManager()
        test_auth.expiry_hours = 0.1  # 6 minutes
        test_auth.refresh_minutes = 5  # Refresh in last 5 minutes

        user_id = "test_user"
        permissions = ["whale_view"]

        result = test_auth.generate_token(user_id, permissions)
        old_token = result["token"]

        # Wait to get into refresh window
        time.sleep(1.5)

        # Refresh token
        new_result = test_auth.refresh_token(old_token)

        assert new_result is not None
        assert "token" in new_result
        assert new_result["token"] != old_token  # New token generated

        # Validate new token
        payload = auth_manager.validate_token(new_result["token"])
        assert payload["user_id"] == user_id
        assert payload["permissions"] == permissions

    def test_refresh_token_too_early(self):
        """Test token refresh when not in refresh window."""
        user_id = "test_user"
        result = auth_manager.generate_token(user_id)
        token = result["token"]

        # Try to refresh immediately (not in window)
        new_result = auth_manager.refresh_token(token)

        assert new_result is None  # Should not refresh

    def test_refresh_expired_token(self):
        """Test that completely expired tokens cannot be refreshed."""
        # Create expired token
        test_auth = JWTAuthManager()
        test_auth.expiry_hours = -1  # Already expired

        user_id = "test_user"
        result = test_auth.generate_token(user_id)
        expired_token = result["token"]

        # Try to refresh expired token
        new_result = test_auth.refresh_token(expired_token)

        assert new_result is None  # Should not refresh expired token

    def test_token_permissions(self):
        """Test token with different permission levels."""
        user_id = "admin_user"
        admin_permissions = ["whale_view", "whale_admin", "whale_delete"]

        result = auth_manager.generate_token(user_id, admin_permissions)
        token = result["token"]

        payload = auth_manager.validate_token(token)
        assert payload["permissions"] == admin_permissions

    def test_token_jti_uniqueness(self):
        """Test that JWT ID (jti) is unique for each token."""
        user_id = "test_user"

        # Generate two tokens
        result1 = auth_manager.generate_token(user_id)
        time.sleep(0.1)  # Small delay to ensure different timestamp
        result2 = auth_manager.generate_token(user_id)

        # Decode tokens to check jti
        payload1 = auth_manager.validate_token(result1["token"])
        payload2 = auth_manager.validate_token(result2["token"])

        # JTI should be different
        assert payload1["jti"] != payload2["jti"]


@pytest.fixture
def clean_auth_manager():
    """Fixture to provide a clean auth manager instance."""
    return JWTAuthManager()


def test_auth_manager_initialization(clean_auth_manager):
    """Test auth manager initializes correctly."""
    assert clean_auth_manager.secret == auth_manager.secret
    assert clean_auth_manager.algorithm == "HS256"
    assert clean_auth_manager.expiry_hours == 1
    assert clean_auth_manager.refresh_minutes == 55
