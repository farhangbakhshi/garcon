import os
import dotenv
import secrets

dotenv.load_dotenv()


class BaseConfig:
    SERVICE_HOST = os.environ.get("HOST")
    SERVICE_PORT = os.environ.get("PORT")
    GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
    # Generate a secure secret key if not provided in environment
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))


class ProductionConfig(BaseConfig):
    DEBUG = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True
