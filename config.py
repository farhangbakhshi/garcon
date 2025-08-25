import os

class BaseConfig:
    SERVICE_HOST = os.environ.get('HOST')
    SERVICE_PORT = os.environ.get('PORT')

class ProductionConfig(BaseConfig):
    DEBUG = False

class DevelopmentConfig(BaseConfig):
    DEBUG = True