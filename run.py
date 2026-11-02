#!/usr/bin/env python3
"""
Flask application runner for local development.
Run this file directly to start the Flask development server.

Usage:
    python run.py
"""
import os
from dotenv import load_dotenv
from app import create_app

load_dotenv()

if __name__ == '__main__':
    app = create_app()
    
    # Get port from environment or default to 8000
    port = int(os.environ.get('PORT', 8000))
    
    # Get debug mode from environment or default to True for local dev
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ('true', '1', 't')
    
    # Bind to localhost (127.0.0.1) by default for local development security.
    # Prevents exposing the interactive Werkzeug debugger on public or LAN Wi-Fi interfaces.
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    if debug and host == '0.0.0.0' and os.environ.get('ALLOW_PUBLIC_DEBUG', '').lower() not in ('true', '1'):
        print("🔒 Security Notice: Flask debug mode on 0.0.0.0 is restricted. Binding to 127.0.0.1.")
        host = '127.0.0.1'

    base_url = f"http://{host}:{port}"
    
    print(f"Starting Flask server on {base_url}")
    print(f"Debug mode: {debug}")
    
    app.run(
        host=host,
        port=port,
        debug=debug
    )
