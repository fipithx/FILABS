from flask import Blueprint

learning_hub_bp = Blueprint('learning_hub', __name__, url_prefix='/learning_hub', template_folder='templates/learning_hub', static_folder='static')

# Import routes to register them with the blueprint
from . import routes

def init_learning_materials(app):
    """
    Initialize storage for the Learning Hub (e.g., MongoDB collections).
    Called by the main app during initialization.
    """
    from .models import init_learning_materials  # Correct: init_learning_materials is defined in models.py
    try:
        with app.app_context():
            init_learning_materials(app)  # Fixed: Changed setup_storage to init_learning_materials
    except Exception as e:
        app.logger.error(f"Error initializing Learning Hub storage: {str(e)}")
        raise
