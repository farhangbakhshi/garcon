from flask import Blueprint, request, jsonify

bp = Blueprint('main', __name__)

@bp.route("/webhook", methods=["POST"])
def webhook():
    if request.is_json:
        payload = request.get_json()

        print("✅ Webhook Received!")
        repo_name = payload.get('repository', {}).get('full_name', 'N/A')
        print(f"Repository: {repo_name}")

        return jsonify(message="Webhook received successfully"), 200
    else:
        return jsonify(error="Request was not JSON"), 400

@bp.route("/")
def index():
    return "<h1>Garcon is running!</h1>"