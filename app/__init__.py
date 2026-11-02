import os
from flask import Flask, jsonify
from flask_cors import CORS
from app.core.config import Config
from app.core.database import create_indexes

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:5173')
    production_domain = os.environ.get('PRODUCTION_DOMAIN', '')
    custom_cors_env = os.environ.get('CORS_ALLOWED_ORIGINS', '')
    extra_origins = [o.strip() for o in custom_cors_env.split(',') if o.strip()]

    allowed_origins = [
        frontend_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    if production_domain:
        allowed_origins.append(production_domain)
    allowed_origins.extend(extra_origins)
    allowed_origins = list(dict.fromkeys(filter(None, allowed_origins)))

    CORS(app, resources={
        r"/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"]
        }
    })
    
    from app.auth import bp as auth_bp
    from app.admin import bp as admin_bp
    from app.payments import bp as payments_bp
    from app.projects.analyzer import bp as analyzer_bp
    from app.projects.analyzer.api.drive_routes import bp as drive_bp
    from app.projects.lead_gen import blueprints as lead_gen_blueprints
    from app.projects.reddit_leads import bp as reddit_leads_bp
    from app.projects.vip_concierge import bp as vip_concierge_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(analyzer_bp)
    app.register_blueprint(drive_bp)
    app.register_blueprint(reddit_leads_bp)
    app.register_blueprint(vip_concierge_bp)
    
    for bp in lead_gen_blueprints:
        app.register_blueprint(bp)
    
    with app.app_context():
        try:
            create_indexes()
        except ConnectionError:
            app.logger.warning('Failed to create indexes')
    
    @app.route('/')
    def root():
        return jsonify({
            'service': 'Platform API',
            'version': '1.0',
            'modules': {
                'auth': '/api/auth',
                'lead_gen': '/api/lead_gen',
                'analyzer': '/api/analyzer',
                'reddit_leads': '/api/reddit-leads',
                'vip_concierge': '/api/vip-concierge',
                'admin': '/api/admin',
                'payments': '/api/payments'
            }
        }), 200
    
    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy'}), 200
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8000, debug=True)
