import subprocess
from flask import Blueprint, request, jsonify
from . import services
import logging
import os
from pathlib import Path

bp = Blueprint("main", __name__)


@bp.route("/webhook", methods=["POST"])
def webhook():
    if request.is_json:
        payload = request.get_json()

        service = services.Services()
        processed_data = service.process_webhook(payload)
        
        # Get the parent directory of the current file
        current_dir = Path(__file__).parent
        deploy_script = current_dir / "deploy.sh"

        subprocess.run([str(deploy_script), processed_data["repo_url"]], check=True)

        # Configure logging to write to ../logs/app.log
        logging.basicConfig(
            filename="../logs/app.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        logging.info(f"Webhook Received! Repository: {processed_data['repo_name']}")

        return jsonify(message="Webhook received successfully"), 200
    else:
        return jsonify(error="Request was not JSON"), 400


@bp.route("/")
def index():
    return "<h1>Garcon is running!</h1>"
