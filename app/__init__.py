from flask import Flask
from config import DevelopmentConfig as Config
import logging
from pathlib import Path

def create_app(config_class=Config):
    app = Flask(__name__)

    app.config.from_object(config_class)

    # Configure logging
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "app.log"),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    with app.app_context():
        from . import routes
        app.register_blueprint(routes.bp)


    return app