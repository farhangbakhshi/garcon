from app import create_app

app = create_app()

if __name__ == "__main__":
    host = app.config.get("SERVICE_HOST", "127.0.0.1")
    port = app.config.get("SERVICE_PORT", 5000)
    app.run(host=host, port=port)