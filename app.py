import os
from flask import Flask, send_from_directory
from flask_login import LoginManager
from config import Config
from models import Admin, db
from routes import bp as api_bp

login_manager = LoginManager()
login_manager.login_view = 'api.login'


def create_app():
    app = Flask(__name__, static_folder='sky', static_url_path='')
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return Admin.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    app.register_blueprint(api_bp)

    @app.route('/')
    def index():
        return send_from_directory(app.static_folder, 'admin.html')

    return app


if __name__ == '__main__':
    application = create_app()
    debug_mode = os.environ.get('FLASK_DEBUG', '1') == '1'
    application.run(host='0.0.0.0', port=5000, debug=debug_mode)
