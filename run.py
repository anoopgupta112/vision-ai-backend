#!/usr/bin/env python3
"""
Flask application runner for local development.
Run this file directly to start the Flask development server.

Usage:
    python run.py
"""
import os
from app import create_app

if __name__ == '__main__':
    app = create_app()
    
    # Get port from environment or default to 8000
    port = int(os.environ.get('PORT', 8000))
    
    # Get debug mode from environment or default to True for local dev
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ('true', '1', 't')
    
    print(f"Starting Flask server on http://localhost:{port}")
    print(f"Debug mode: {debug}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
