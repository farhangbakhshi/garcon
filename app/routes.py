import subprocess
from flask import Blueprint, request, jsonify
from . import services
import logging

bp = Blueprint("main", __name__)


@bp.route("/webhook", methods=["POST"])
def webhook():
    if request.is_json:
        payload = request.get_json()

        service = services.Services()
        processed_data = service.process_webhook(payload)
        
        subprocess.run(
            ["/home/farhang/source_codes/garcon/deploy.sh", processed_data["repo_url"]],
            check=True,
        )

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
