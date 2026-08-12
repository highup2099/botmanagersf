"""
Secure Token Storage - Encrypted storage for OAuth tokens.

Uses cryptography library to encrypt tokens before storing in database.
Supports both in-memory (MVP) and database-backed (production) storage.
"""

import os
import json
import base64
from typing import Optional, Dict
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.logging_module.app_logger import get_logger
from src.config.settings import settings


logger = get_logger()


class TokenStorageError(Exception):
    """Exception raised for token storage errors."""
    pass


class EncryptedTokenStorage:
    """
    Secure token storage with encryption.
    
    Uses Fernet symmetric encryption to protect OAuth tokens.
    Encryption key is derived from a master password or generated randomly.
    """
    
    def __init__(self, master_password: Optional[str] = None, use_database: bool = False):
        """
        Initialize encrypted token storage.
        
        Args:
            master_password: Optional master password for key derivation.
                            If not provided, uses environment variable or generates random key.
            use_database: If True, store encrypted tokens in database (production).
                         If False, use in-memory storage (MVP).
        """
        self.use_database = use_database
        self._tokens: Dict[int, Dict] = {}  # In-memory storage fallback
        
        # Derive or load encryption key
        self._cipher = self._initialize_cipher(master_password)
        
        if self.use_database:
            logger.info("Using database-backed encrypted token storage", "TOKEN_STORAGE_INIT")
        else:
            logger.info("Using in-memory encrypted token storage (MVP)", "TOKEN_STORAGE_INIT")
    
    def _initialize_cipher(self, master_password: Optional[str]) -> Fernet:
        """
        Initialize Fernet cipher for encryption/decryption.
        
        Args:
            master_password: Optional master password
            
        Returns:
            Fernet cipher instance
        """
        # Try to get key from environment
        key_b64 = os.environ.get('SPOTIFY_TOKEN_KEY')
        
        if key_b64:
            try:
                key = base64.urlsafe_b64decode(key_b64)
                logger.info("Loaded encryption key from environment", "TOKEN_KEY_LOADED")
                return Fernet(key)
            except Exception as e:
                logger.error(f"Failed to load key from environment: {e}", "TOKEN_KEY_ERROR")
        
        # Derive key from master password if provided
        if master_password:
            key = self._derive_key(master_password)
            return Fernet(base64.urlsafe_b64encode(key))
        
        # Generate random key (not persisted - tokens lost on restart)
        logger.warning("No encryption key configured - using random key (not persisted)", "TOKEN_KEY_RANDOM")
        key = Fernet.generate_key()
        return Fernet(key)
    
    def _derive_key(self, password: str, salt: Optional[bytes] = None) -> bytes:
        """
        Derive encryption key from password using PBKDF2.
        
        Args:
            password: Master password
            salt: Optional salt (generated if not provided)
            
        Returns:
            32-byte key
        """
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = kdf.derive(password.encode())
        return key
    
    def _encrypt(self, data: Dict) -> str:
        """
        Encrypt data dictionary.
        
        Args:
            data: Dictionary to encrypt
            
        Returns:
            Base64-encoded encrypted string
        """
        try:
            json_data = json.dumps(data).encode()
            encrypted = self._cipher.encrypt(json_data)
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            raise TokenStorageError(f"Failed to encrypt token data: {e}")
    
    def _decrypt(self, encrypted_data: str) -> Dict:
        """
        Decrypt data string.
        
        Args:
            encrypted_data: Base64-encoded encrypted string
            
        Returns:
            Decrypted dictionary
        """
        try:
            decoded = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self._cipher.decrypt(decoded)
            return json.loads(decrypted.decode())
        except Exception as e:
            raise TokenStorageError(f"Failed to decrypt token data: {e}")
    
    def store(self, profile_id: int, token_data: Dict) -> None:
        """
        Store encrypted tokens for a profile.
        
        Args:
            profile_id: Profile ID
            token_data: Token dictionary with access_token, refresh_token, etc.
        """
        # Add metadata
        token_data['stored_at'] = datetime.utcnow().isoformat()
        
        # Calculate absolute expiry time
        if 'expires_in' in token_data:
            from datetime import timedelta
            expires_in = token_data.get('expires_in', 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            token_data['expires_at'] = expires_at.isoformat()
        
        # Encrypt sensitive fields
        sensitive_fields = ['access_token', 'refresh_token']
        encrypted_data = {}
        
        for field, value in token_data.items():
            if field in sensitive_fields and value:
                encrypted_data[field] = self._encrypt({'value': value})
            else:
                encrypted_data[field] = value
        
        if self.use_database:
            self._store_in_database(profile_id, encrypted_data)
        else:
            self._tokens[profile_id] = encrypted_data
        
        logger.info(f"Stored encrypted tokens for profile {profile_id}", "TOKEN_STORED", profile_id)
    
    def _store_in_database(self, profile_id: int, encrypted_data: Dict) -> None:
        """Store encrypted tokens in database."""
        from src.database.database import DatabaseManager
        from src.database.models import Profile
        
        try:
            with DatabaseManager() as session:
                profile = session.query(Profile).filter(Profile.id == profile_id).first()
                if profile:
                    # Store as JSON blob
                    profile.spotify_user_id = json.dumps(encrypted_data)
                    session.commit()
        except Exception as e:
            raise TokenStorageError(f"Database storage failed: {e}")
    
    def get(self, profile_id: int) -> Optional[Dict]:
        """
        Get and decrypt tokens for a profile.
        
        Args:
            profile_id: Profile ID
            
        Returns:
            Token dictionary or None if not found
        """
        if self.use_database:
            encrypted_data = self._load_from_database(profile_id)
        else:
            encrypted_data = self._tokens.get(profile_id)
        
        if not encrypted_data:
            return None
        
        # Decrypt sensitive fields
        token_data = {}
        sensitive_fields = ['access_token', 'refresh_token']
        
        for field, value in encrypted_data.items():
            if field in sensitive_fields and value:
                try:
                    decrypted = self._decrypt(value)
                    token_data[field] = decrypted.get('value')
                except TokenStorageError:
                    logger.warning(f"Failed to decrypt {field} for profile {profile_id}", "TOKEN_DECRYPT_ERROR", profile_id)
                    return None
            else:
                token_data[field] = value
        
        # Parse ISO format timestamps
        for field in ['stored_at', 'expires_at']:
            if field in token_data and isinstance(token_data[field], str):
                try:
                    token_data[field] = datetime.fromisoformat(token_data[field])
                except ValueError:
                    pass
        
        return token_data
    
    def _load_from_database(self, profile_id: int) -> Optional[Dict]:
        """Load encrypted tokens from database."""
        from src.database.database import DatabaseManager
        from src.database.models import Profile
        
        try:
            with DatabaseManager() as session:
                profile = session.query(Profile).filter(Profile.id == profile_id).first()
                if profile and profile.spotify_user_id:
                    return json.loads(profile.spotify_user_id)
        except Exception as e:
            logger.error(f"Database load failed: {e}", "TOKEN_LOAD_ERROR", profile_id)
        
        return None
    
    def delete(self, profile_id: int) -> None:
        """
        Delete tokens for a profile.
        
        Args:
            profile_id: Profile ID
        """
        if self.use_database:
            self._delete_from_database(profile_id)
        else:
            self._tokens.pop(profile_id, None)
        
        logger.info(f"Deleted tokens for profile {profile_id}", "TOKEN_DELETED", profile_id)
    
    def _delete_from_database(self, profile_id: int) -> None:
        """Delete tokens from database."""
        from src.database.database import DatabaseManager
        from src.database.models import Profile
        
        try:
            with DatabaseManager() as session:
                profile = session.query(Profile).filter(Profile.id == profile_id).first()
                if profile:
                    profile.spotify_user_id = None
                    session.commit()
        except Exception as e:
            logger.error(f"Database delete failed: {e}", "TOKEN_DELETE_ERROR", profile_id)
    
    def needs_refresh(self, profile_id: int) -> bool:
        """
        Check if token needs refresh (5 min buffer).
        
        Args:
            profile_id: Profile ID
            
        Returns:
            True if refresh needed
        """
        token_data = self.get(profile_id)
        if not token_data:
            return True
        
        expires_at = token_data.get('expires_at')
        if not expires_at:
            return True
        
        # Refresh 5 minutes before expiry
        from datetime import timedelta
        buffer = timedelta(minutes=5)
        
        if isinstance(expires_at, datetime):
            return datetime.utcnow() > (expires_at - buffer)
        
        return True
    
    def generate_key(self) -> str:
        """
        Generate a new encryption key.
        
        Returns:
            Base64-encoded key (store this securely!)
        """
        key = Fernet.generate_key()
        return base64.urlsafe_b64encode(key).decode()
    
    def save_key_to_file(self, key: str, path: Optional[str] = None) -> None:
        """
        Save encryption key to file.
        
        Args:
            key: Base64-encoded key
            path: File path (default: ~/.spotify_manager/token.key)
        """
        if path is None:
            home_dir = Path.home()
            config_dir = home_dir / '.spotify_manager'
            config_dir.mkdir(mode=0o700, exist_ok=True)
            path = str(config_dir / 'token.key')
        
        try:
            with open(path, 'w') as f:
                f.write(key)
            
            # Set restrictive permissions
            os.chmod(path, 0o600)
            
            logger.info(f"Saved encryption key to {path}", "TOKEN_KEY_SAVED")
        except Exception as e:
            logger.error(f"Failed to save key: {e}", "TOKEN_KEY_SAVE_ERROR")
    
    def load_key_from_file(self, path: Optional[str] = None) -> Optional[str]:
        """
        Load encryption key from file.
        
        Args:
            path: File path (default: ~/.spotify_manager/token.key)
            
        Returns:
            Key string or None
        """
        if path is None:
            home_dir = Path.home()
            path = str(home_dir / '.spotify_manager' / 'token.key')
        
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    key = f.read().strip()
                logger.info(f"Loaded encryption key from {path}", "TOKEN_KEY_LOADED")
                return key
        except Exception as e:
            logger.error(f"Failed to load key: {e}", "TOKEN_KEY_LOAD_ERROR")
        
        return None


# Global instance
_token_storage: Optional[EncryptedTokenStorage] = None


def get_token_storage(use_database: bool = False) -> EncryptedTokenStorage:
    """Get or create encrypted token storage instance."""
    global _token_storage
    if _token_storage is None:
        _token_storage = EncryptedTokenStorage(use_database=use_database)
    return _token_storage


def initialize_secure_storage(master_password: Optional[str] = None, use_database: bool = False) -> EncryptedTokenStorage:
    """
    Initialize secure token storage with custom configuration.
    
    Args:
        master_password: Optional master password
        use_database: Use database storage
        
    Returns:
        EncryptedTokenStorage instance
    """
    global _token_storage
    _token_storage = EncryptedTokenStorage(master_password=master_password, use_database=use_database)
    return _token_storage
