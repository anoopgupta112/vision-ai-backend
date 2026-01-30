from flask import Flask, render_template, jsonify
from config import get_config

def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config())
    
    register_routes(app)
    register_error_handlers(app)
    
    return app

def register_routes(app):
    @app.route('/')
    def home():
        dashboard_url = app.config['DASHBOARD_URL']
        return render_template('index.html', dashboard_url=dashboard_url)
    
    @app.route('/health')
    def health_check():
        return jsonify({
            'status': 'healthy',
            'service': 'lead_extractor_landing'
        }), 200

def register_error_handlers(app):
    @app.errorhandler(404)
    def handle_not_found(error):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        return render_template('500.html'), 500
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.error(f'Unexpected error: {str(error)}')
        return render_template('500.html'), 500

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8000)
