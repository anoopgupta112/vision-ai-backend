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
    coding_dashboard_key = os.environ.get('CODING_DASHBOARD', '').strip()
    base_url = f"http://localhost:{port}"
    
    print(f"Starting Flask server on {base_url}")
    print(f"Debug mode: {debug}")
    if coding_dashboard_key:
        print(f"Coding dashboard: {base_url}/api/admin/automation/dashboard?key={coding_dashboard_key}")
    else:
        print("Coding dashboard: disabled (set CODING_DASHBOARD to enable)")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
