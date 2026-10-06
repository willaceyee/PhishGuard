from flask import Flask
from flask_cors import CORS
from sqlalchemy import inspect, text

from app.extensions import db, jwt


def create_app(config_object="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_object)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    db.init_app(app)
    jwt.init_app(app)

    from app.auth import auth
    from app.routes import main, api
    from app.simulation import simulation
    from app.training import training
    from app.detection import detection
    from app.analytics import analytics
    from app.sending_profiles import sending_profiles

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(api)
    app.register_blueprint(simulation)
    app.register_blueprint(training)
    app.register_blueprint(detection)
    app.register_blueprint(analytics)
    app.register_blueprint(sending_profiles)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        return response

    @app.cli.command("init-db")
    def init_db_command():
        """Create database tables for the configured database."""
        db.create_all()
        print("Database tables created.")

    @app.cli.command("upgrade-db")
    def upgrade_db_command():
        """Apply the small built-in schema upgrades used by this project."""
        from app.models import SendingProfile

        upgraded = False
        columns = {column["name"] for column in inspect(db.engine).get_columns("users")}
        if "simulation_email_approved" not in columns:
            db.session.execute(
                text(
                    "ALTER TABLE users ADD COLUMN "
                    "simulation_email_approved BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            db.session.commit()
            print("Added users.simulation_email_approved.")
            upgraded = True

        profile_table_exists = inspect(db.engine).has_table("sending_profiles")
        SendingProfile.__table__.create(bind=db.engine, checkfirst=True)
        if not profile_table_exists:
            print("Created sending_profiles.")
            upgraded = True

        for table, column, definition in (
            ("campaigns", "sending_profile_id", "INTEGER"),
            ("tracking_events", "delivery_channel", "VARCHAR(40)"),
        ):
            columns = {
                item["name"] for item in inspect(db.engine).get_columns(table)
            }
            if column not in columns:
                db.session.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                )
                db.session.commit()
                print(f"Added {table}.{column}.")
                upgraded = True

        if not upgraded:
            print("Database is already up to date.")

    return app
