import os
from dotenv import load_dotenv

load_dotenv()

class BaseConfig:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DASHBOARD_URL = os.getenv('DASHBOARD_URL', 'http://localhost:5000')

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    ENV = 'development'

class ProductionConfig(BaseConfig):
    DEBUG = False
    ENV = 'production'

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    env = os.getenv('FLASK_ENV', 'development')
    return config_by_name.get(env, config_by_name['default'])
