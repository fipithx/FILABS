from flask import Blueprint, current_app
from flask_wtf.csrf import CSRFProtect
import os
import logging
from .models import init_storage

learning_hub_bp = Blueprint(
    'learning_hub',
    __name__,
    template_folder='templates/learning_hub',
    static_folder='static',
    url_prefix='/learning_hub'
)

# Initialize CSRF protection
csrf = CSRFProtect()

def init_app(app):
    """Initialize the Learning Hub with app context."""
    # Ensure upload folder exists
    upload_folder = app.config.get('UPLOAD_FOLDER', 'learning_hub/static/uploads')
    os.makedirs(upload_folder, exist_ok=True)
    
    # Configure logging
    app.logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    app.logger.addHandler(handler)
    
    # Initialize storage
    init_storage(app)
    
    # Register context processor for courses
    @app.context_processor
    def inject_courses():
        from .models import get_courses_by_role
        role_filter = session.get('role_filter', 'all')
        courses = get_courses_by_role(role_filter)
        return {'courses': courses}
    
    # Ensure MongoDB connections are closed on teardown
    @app.teardown_appcontext
    def close_db(error):
        from flask import g
        if hasattr(g, 'db'):
            g.db.client.close()
            current_app.logger.info("MongoDB connection closed", extra={'session_id': session.get('sid', 'no-session-id')})