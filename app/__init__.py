from flask import Flask, jsonify
from flask_cors import CORS
from app.core.config import Config
from app.core.database import create_indexes

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    CORS(app, resources={
        r"/*": {
            "origins": "*",
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
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(analyzer_bp)
    app.register_blueprint(drive_bp)
    
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
