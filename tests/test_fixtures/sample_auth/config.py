"""
Application configuration.
"""

# Database
DB_PATH = "app.db"
DB_POOL_SIZE = 5

# Authentication
JWT_SECRET = "change-me-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
MAX_LOGIN_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 300  # seconds
ACCOUNT_LOCK_THRESHOLD = 3

# Server
HOST = "0.0.0.0"
PORT = 8000
WORKERS = 4
REQUEST_TIMEOUT_SECONDS = 30
MAX_REQUEST_SIZE_KB = 100

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "json"
AUDIT_LOG_ENABLED = True
