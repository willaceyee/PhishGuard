from flask import Flask
from flask_cors import CORS

from app.extensions import db, jwt


def create_app(config_object="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_object)
    CORS(app)
    db.init_app(app)
    jwt.init_app(app)

    from app.auth import auth
    from app.routes import main, api
    from app.simulation import simulation
    from app.training import training
    from app.detection import detection

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(api)
    app.register_blueprint(simulation)
    app.register_blueprint(training)
    app.register_blueprint(detection)

    @app.cli.command("init-db")
    def init_db_command():
        """Create database tables for the configured database."""
        db.create_all()
        print("Database tables created.")

    return app
