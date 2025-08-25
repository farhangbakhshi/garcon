import os
import dotenv

dotenv.load_dotenv()

class BaseConfig:
    SERVICE_HOST = os.environ.get('HOST')
    SERVICE_PORT = os.environ.get('PORT')
    GITHUB_WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET')

class ProductionConfig(BaseConfig):
    DEBUG = False

class DevelopmentConfig(BaseConfig):
    DEBUG = True