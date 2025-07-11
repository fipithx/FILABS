from flask import Blueprint
import os
from .models import init_storage

learning_hub_bp = Blueprint(
    'learning_hub',
    __name__,
    template_folder='templates/learning_hub',
    static_folder='static',
    url_prefix='/learning_hub'
)

# Import routes after blueprint definition to avoid circular imports
from .routes import *
