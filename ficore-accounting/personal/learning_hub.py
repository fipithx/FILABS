from flask import Blueprint, render_template, session, request, redirect, url_for, flash, current_app, send_from_directory, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, FileField, SelectField
from wtforms.validators import DataRequired, Email, Optional
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_login import current_user
from datetime import datetime
import logging
import os
from werkzeug.utils import secure_filename
from mailersend_email import send_email, EMAIL_CONFIG
from translations import trans
from models import log_tool_usage
from session_utils import create_anonymous_session
from utils import requires_role, is_admin, get_mongo_db
from bson import ObjectId
from werkzeug import Response
import utils

learning_hub_bp = Blueprint(
    'learning_hub',
    __name__,
    template_folder='templates/personal/LEARNINGHUB',
    url_prefix='/learning_hub'
)

# Initialize CSRF protection
csrf = CSRFProtect()

# Define allowed file extensions and upload folder
ALLOWED_EXTENSIONS = {'mp4', 'pdf', 'txt', 'md'}
UPLOAD_FOLDER = 'static/uploads'

# Ensure upload folder exists
def init_app(app):
    os.makedirs(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), exist_ok=True)
    init_storage(app)
    # Configure logging
    app.logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    app.logger.addHandler(handler)
    # Ensure MongoDB connections are closed on teardown
    @app.teardown_appcontext
    def close_db(error):
        if hasattr(g, 'db'):
            g.db.client.close()
            current_app.logger.info("MongoDB connection closed", extra={'session_id': session.get('sid', 'no-session-id')})

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Courses data with multimedia support and role tags
courses_data = {
    "budgeting_101": {
        "id": "budgeting_101",
        "title_en": "Budgeting 101",
        "title_ha": "Tsarin Kudi 101",
        "description_en": "Learn the basics of budgeting and financial planning to take control of your finances.",
        "description_ha": "Koyon asalin tsarin kudi da shirye-shiryen kudi don sarrafa kudin ku.",
        "title_key": "learning_hub_course_budgeting101_title",
        "desc_key": "learning_hub_course_budgeting101_desc",
        "is_premium": False,
        "roles": ["civil_servant", "nysc", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_income_title",
                "title_en": "Understanding Income",
                "lessons": [
                    {
                        "id": "budgeting_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_income_sources_title",
                        "title_en": "Income Sources",
                        "content_type": "video",
                        "content_path": "uploads/budgeting_101_lesson1.mp4",
                        "content_en": "Understanding different sources of income is crucial for effective budgeting. Learn about salary, business income, investments, and passive income streams.",
                        "quiz_id": "quiz-1-1"
                    },
                    {
                        "id": "budgeting_101-module-1-lesson-2",
                        "title_key": "learning_hub_lesson_net_income_title",
                        "title_en": "Calculating Net Income",
                        "content_type": "text",
                        "content_key": "learning_hub_lesson_net_income_content",
                        "content_en": "Learn how to calculate your net income after taxes and deductions. This is the foundation of any successful budget.",
                        "quiz_id": None
                    }
                ]
            },
            {
                "id": "module-2",
                "title_key": "learning_hub_module_expenses_title",
                "title_en": "Managing Expenses",
                "lessons": [
                    {
                        "id": "budgeting_101-module-2-lesson-1",
                        "title_key": "learning_hub_lesson_expense_categories_title",
                        "title_en": "Expense Categories",
                        "content_type": "text",
                        "content_en": "Learn to categorize your expenses into fixed, variable, and discretionary spending to better manage your budget.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "financial_quiz": {
        "id": "financial_quiz",
        "title_en": "Financial Knowledge Quiz",
        "title_ha": "Jarabawar Ilimin Kudi",
        "description_en": "Test your financial knowledge with our comprehensive quiz and discover areas for improvement.",
        "description_ha": "Gwada ilimin ku na kudi da jarabawa mai cikakke kuma gano wuraren da za ku inganta.",
        "title_key": "learning_hub_course_financial_quiz_title",
        "desc_key": "learning_hub_course_financial_quiz_desc",
        "is_premium": False,
        "roles": ["civil_servant", "nysc", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_quiz_title",
                "title_en": "Financial Assessment",
                "lessons": [
                    {
                        "id": "financial_quiz-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_quiz_intro_title",
                        "title_en": "Quiz Introduction",
                        "content_type": "text",
                        "content_key": "learning_hub_lesson_quiz_intro_content",
                        "content_en": "This comprehensive quiz will help assess your current financial knowledge and identify areas where you can improve your financial literacy.",
                        "quiz_id": "quiz-financial-1"
                    }
                ]
            }
        ]
    },
    "savings_basics": {
        "id": "savings_basics",
        "title_en": "Savings Fundamentals",
        "title_ha": "Asalin Tattara Kudi",
        "description_en": "Master the fundamentals of saving money effectively and build a secure financial future.",
        "description_ha": "Koyon asalin tattara kudi yadda ya kamata kuma gina makomar kudi mai tsaro.",
        "title_key": "learning_hub_course_savings_basics_title",
        "desc_key": "learning_hub_course_savings_basics_desc",
        "is_premium": False,
        "roles": ["civil_servant", "nysc", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_savings_title",
                "title_en": "Savings Strategies",
                "lessons": [
                    {
                        "id": "savings_basics-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_savings_strategies_title",
                        "title_en": "Effective Savings Strategies",
                        "content_type": "text",
                        "content_key": "learning_hub_lesson_savings_strategies_content",
                        "content_en": "Learn proven strategies for building your savings effectively, including the 50/30/20 rule, automatic savings, and emergency fund planning.",
                        "quiz_id": None
                    },
                    {
                        "id": "savings_basics-module-1-lesson-2",
                        "title_key": "learning_hub_lesson_savings_goals_title",
                        "title_en": "Setting Savings Goals",
                        "content_type": "text",
                        "content_en": "Discover how to set realistic and achievable savings goals that will motivate you to save consistently.",
                        "quiz_id": "quiz-savings-1"
                    }
                ]
            }
        ]
    },
    "tax_reforms_2025": {
        "id": "tax_reforms_2025",
        "title_en": "2025 Tax Reforms – What You Need to Know",
        "title_ha": "Gyaran Haraji na 2025 – Abin da Yakamata Ku Sani",
        "description_en": "Understand the key changes in Nigeria's 2025 tax reforms, including updates to PIT, CIT, and VAT.",
        "description_ha": "Fahimci mahimman canje-canje a cikin gyaran haraji na Najeriya na 2025, ciki har da sabuntawa ga PIT, CIT, da VAT.",
        "title_key": "learning_hub_course_tax_reforms_2025_title",
        "desc_key": "learning_hub_course_tax_reforms_2025_desc",
        "is_premium": False,
        "roles": ["civil_servant", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_tax_reforms_title",
                "title_en": "Understanding Nigeria's 2025 Tax Reforms",
                "lessons": [
                    {
                        "id": "tax_reforms_2025-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_tax_reforms_title",
                        "title_en": "Key Tax Reform Changes",
                        "content_type": "text",
                        "content_key": "learning_hub_lesson_tax_reforms_content",
                        "content_en": """
### Personal Income Tax (PIT) Changes
- Individuals earning ₦1 million or less annually now enjoy ₦200,000 rent relief, reducing their taxable income to ₦800,000.
- Result: No PIT for most low-income earners.

### Value Added Tax (VAT) Relief
- No VAT on essential goods/services: food, education, rent, healthcare, baby products, electricity.
- Helps families reduce cost of living.

### Corporate Income Tax (CIT) Reforms
- **Small businesses (≤₦50M turnover):**
  - Now pay 0% CIT.
  - Can file simpler tax returns, no audited accounts required.
- **Large companies:**
  - CIT reduced from 30% to 27.5% (2025).
  - Further reduction to 25% in later years.
  - Can now claim VAT credits on eligible expenses.
                        """,
                        "quiz_id": "quiz-tax-reforms-2025"
                    }
                ]
            }
        ]
    },
    "digital_foundations": {
        "id": "digital_foundations",
        "title_en": "Digital Foundations",
        "title_ha": "Tushen Dijital",
        "description_en": "Learn the basics of computers, internet tools, and how to use AI tools like ChatGPT for everyday tasks. No prior knowledge needed!",
        "description_ha": "Koyon asalin kwamfutoci, kayan aikin intanet, da yadda ake amfani da kayan aikin AI kamar ChatGPT don ayyukan yau da kullum. Ba a buƙatar ilimi na farko!",
        "title_key": "learning_hub_digital_foundations_title",
        "desc_key": "learning_hub_digital_foundations_desc",
        "is_premium": False,
        "roles": ["civil_servant", "nysc", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_computer_basics_title",
                "title_en": "Computer Basics",
                "lessons": [
                    {
                        "id": "digital_foundations-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_computer_basics_title",
                        "title_en": "What is a Computer?",
                        "content_type": "text",
                        "content_en": "Understand the basic components of a computer and how to use it for everyday tasks.",
                        "quiz_id": None
                    },
                    {
                        "id": "digital_foundations-module-1-lesson-2",
                        "title_key": "learning_hub_lesson_files_title",
                        "title_en": "Saving vs. Uploading Files",
                        "content_type": "text",
                        "content_en": "Learn the difference between saving a file locally and uploading it to the cloud or a website.",
                        "quiz_id": None
                    }
                ]
            },
            {
                "id": "module-2",
                "title_key": "learning_hub_module_internet_tools_title",
                "title_en": "Internet Tools",
                "lessons": [
                    {
                        "id": "digital_foundations-module-2-lesson-1",
                        "title_key": "learning_hub_lesson_browser_title",
                        "title_en": "What is a Browser?",
                        "content_type": "video",
                        "content_path": "uploads/browser_intro.mp4",
                        "content_en": "Explore how to use web browsers to access the internet effectively.",
                        "quiz_id": None
                    }
                ]
            },
            {
                "id": "module-3",
                "title_key": "learning_hub_module_ai_basics_title",
                "title_en": "AI for Beginners",
                "lessons": [
                    {
                        "id": "digital_foundations-module-3-lesson-1",
                        "title_key": "learning_hub_lesson_ai_budgeting_title",
                        "title_en": "Using ChatGPT for Budgeting",
                        "content_type": "text",
                        "content_en": "Learn how to use AI tools like ChatGPT to assist with budgeting and financial planning.",
                        "quiz_id": "quiz-digital-foundations-3-1"
                    }
                ]
            }
        ]
    }
}

quizzes_data = {
    "quiz-1-1": {
        "id": "quiz-1-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_income_q1",
                "question_en": "What is the most common source of income for most people?",
                "options_keys": [
                    "learning_hub_quiz_income_opt_salary",
                    "learning_hub_quiz_income_opt_business",
                    "learning_hub_quiz_income_opt_investment",
                    "learning_hub_quiz_income_opt_other"
                ],
                "options_en": ["Salary/Wages", "Business Income", "Investment Returns", "Other Sources"],
                "answer_key": "learning_hub_quiz_income_opt_salary",
                "answer_en": "Salary/Wages"
            },
            {
                "question_key": "learning_hub_quiz_income_q2",
                "question_en": "What should you do with your income first?",
                "options_keys": [
                    "learning_hub_quiz_income_opt2_spend",
                    "learning_hub_quiz_income_opt2_save",
                    "learning_hub_quiz_income_opt2_invest",
                    "learning_hub_quiz_income_opt2_budget"
                ],
                "options_en": ["Spend on necessities", "Save everything", "Invest immediately", "Create a budget plan"],
                "answer_key": "learning_hub_quiz_income_opt2_budget",
                "answer_en": "Create a budget plan"
            }
        ]
    },
    "quiz-financial-1": {
        "id": "quiz-financial-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_financial_q1",
                "question_en": "What percentage of income should you ideally save?",
                "options_keys": [
                    "learning_hub_quiz_financial_opt_a",
                    "learning_hub_quiz_financial_opt_b",
                    "learning_hub_quiz_financial_opt_c",
                    "learning_hub_quiz_financial_opt_d"
                ],
                "options_en": ["20%", "10%", "5%", "30%"],
                "answer_key": "learning_hub_quiz_financial_opt_a",
                "answer_en": "20%"
            },
            {
                "question_key": "learning_hub_quiz_financial_q2",
                "question_en": "What is an emergency fund?",
                "options_keys": [
                    "learning_hub_quiz_financial_opt2_a",
                    "learning_hub_quiz_financial_opt2_b",
                    "learning_hub_quiz_financial_opt2_c",
                    "learning_hub_quiz_financial_opt2_d"
                ],
                "options_en": ["Money for vacations", "Money for unexpected expenses", "Money for investments", "Money for shopping"],
                "answer_key": "learning_hub_quiz_financial_opt2_b",
                "answer_en": "Money for unexpected expenses"
            }
        ]
    },
    "quiz-savings-1": {
        "id": "quiz-savings-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_savings_q1",
                "question_en": "What is the 50/30/20 rule?",
                "options_keys": [
                    "learning_hub_quiz_savings_opt_a",
                    "learning_hub_quiz_savings_opt_b",
                    "learning_hub_quiz_savings_opt_c",
                    "learning_hub_quiz_savings_opt_d"
                ],
                "options_en": ["50% needs, 30% wants, 20% savings", "50% savings, 30% needs, 20% wants", "50% wants, 30% savings, 20% needs", "50% investments, 30% savings, 20% spending"],
                "answer_key": "learning_hub_quiz_savings_opt_a",
                "answer_en": "50% needs, 30% wants, 20% savings"
            }
        ]
    },
    "quiz-tax-reforms-2025": {
        "id": "quiz-tax-reforms-2025",
        "questions": [
            {
                "question_key": "learning_hub_quiz_tax_reforms_q1",
                "question_en": "What is the new rent relief threshold for PIT?",
                "options_keys": [
                    "learning_hub_quiz_tax_reforms_opt1_a",
                    "learning_hub_quiz_tax_reforms_opt1_b",
                    "learning_hub_quiz_tax_reforms_opt1_c",
                    "learning_hub_quiz_tax_reforms_opt1_d"
                ],
                "options_en": ["₦100k", "₦200k", "₦500k", "None"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt1_b",
                "answer_en": "₦200k"
            },
            {
                "question_key": "learning_hub_quiz_tax_reforms_q2",
                "question_en": "A business earning ₦30M yearly will pay what CIT rate?",
                "options_keys": [
                    "learning_hub_quiz_tax_reforms_opt2_a",
                    "learning_hub_quiz_tax_reforms_opt2_b",
                    "learning_hub_quiz_tax_reforms_opt2_c",
                    "learning_hub_quiz_tax_reforms_opt2_d"
                ],
                "options_en": ["0%", "20%", "25%", "30%"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt2_a",
                "answer_en": "0%"
            },
            {
                "question_key": "learning_hub_quiz_tax_reforms_q3",
                "question_en": "Which of these items is now VAT-exempt?",
                "options_keys": [
                    "learning_hub_quiz_tax_reforms_opt3_a",
                    "learning_hub_quiz_tax_reforms_opt3_b",
                    "learning_hub_quiz_tax_reforms_opt3_c",
                    "learning_hub_quiz_tax_reforms_opt3_d"
                ],
                "options_en": ["Soft drinks", "Healthcare", "Designer clothes", "Luxury cars"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt3_b",
                "answer_en": "Healthcare"
            },
            {
                "question_key": "learning_hub_quiz_tax_reforms_q4",
                "question_en": "What tax benefit do large companies now enjoy?",
                "options_keys": [
                    "learning_hub_quiz_tax_reforms_opt4_a",
                    "learning_hub_quiz_tax_reforms_opt4_b",
                    "learning_hub_quiz_tax_reforms_opt4_c",
                    "learning_hub_quiz_tax_reforms_opt4_d"
                ],
                "options_en": ["Flat rate of 35%", "Exemption from tax", "Reduced VAT", "Reduced CIT to 27.5%, later 25%"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt4_d",
                "answer_en": "Reduced CIT to 27.5%, later 25%"
            }
        ]
    },
    "quiz-digital-foundations-3-1": {
        "id": "quiz-digital-foundations-3-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_digital_q1",
                "question_en": "What can AI tools like ChatGPT help you with?",
                "options_keys": [
                    "learning_hub_quiz_digital_opt1_a",
                    "learning_hub_quiz_digital_opt1_b",
                    "learning_hub_quiz_digital_opt1_c",
                    "learning_hub_quiz_digital_opt1_d"
                ],
                "options_en": ["Budgeting", "Building a computer", "Driving a car", "Cooking meals"],
                "answer_key": "learning_hub_quiz_digital_opt1_a",
                "answer_en": "Budgeting"
            }
        ]
    },
    "reality_check_quiz": {
        "id": "reality_check_quiz",
        "questions": [
            {
                "question_key": "learning_hub_quiz_q1",
                "question_en": "What is a web browser?",
                "options_keys": [
                    "learning_hub_quiz_q1_a",
                    "learning_hub_quiz_q1_b"
                ],
                "options_en": ["A program to browse the internet", "A type of computer hardware"],
                "answer_key": "learning_hub_quiz_q1_a",
                "answer_en": "A program to browse the internet"
            },
            {
                "question_key": "learning_hub_quiz_q2",
                "question_en": "How do you save a file?",
                "options_keys": [
                    "learning_hub_quiz_q2_a",
                    "learning_hub_quiz_q2_b"
                ],
                "options_en": ["Click File > Save in an application", "Send it to an email"],
                "answer_key": "learning_hub_quiz_q2_a",
                "answer_en": "Click File > Save in an application"
            }
        ]
    }
}

class LearningHubProfileForm(FlaskForm):
    first_name = StringField(trans('general_first_name', default='First Name'), validators=[DataRequired()])
    email = StringField(trans('general_email', default='Email'), validators=[Optional(), Email()])
    send_email = BooleanField(trans('general_send_email', default='Send Email'), default=False)
    submit = SubmitField(trans('general_submit', default='Submit'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.first_name.validators[0].message = trans('general_first_name_required', default='First name is required', lang=lang)
        if self.email.validators:
            self.email.validators[1].message = trans('general_email_invalid', default='Please enter a valid email address', lang=lang)

class UploadForm(FlaskForm):
    title = StringField(trans('learning_hub_course_title', default='Course Title'), validators=[DataRequired()])
    course_id = StringField(trans('learning_hub_course_id', default='Course ID'), validators=[DataRequired()])
    description = StringField(trans('learning_hub_description', default='Description'), validators=[DataRequired()])
    content_type = SelectField(trans('learning_hub_content_type', default='Content Type'), choices=[
        ('video', 'Video'), ('text', 'Text'), ('pdf', 'PDF')
    ], validators=[DataRequired()])
    is_premium = BooleanField(trans('learning_hub_is_premium', default='Premium Content'), default=False)
    roles = SelectField(trans('learning_hub_roles', default='Roles'), choices=[
        ('all', 'All Roles'), ('civil_servant', 'Civil Servant'), ('nysc', 'NYSC Member'), ('agent', 'Agent')
    ], validators=[DataRequired()])
    file = FileField(trans('learning_hub_upload_file', default='Upload File'), validators=[DataRequired()])
    submit = SubmitField(trans('learning_hub_upload', default='Upload'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.title.validators[0].message = trans('learning_hub_course_title_required', default='Course title is required', lang=lang)
        self.course_id.validators[0].message = trans('learning_hub_course_id_required', default='Course ID is required', lang=lang)
        self.description.validators[0].message = trans('learning_hub_description_required', default='Description is required', lang=lang)
        self.content_type.validators[0].message = trans('learning_hub_content_type_required', default='Content type is required', lang=lang)
        self.file.validators[0].message = trans('learning_hub_file_required', default='File is required', lang=lang)
        self.roles.validators[0].message = trans('learning_hub_roles_required', default='Role is required', lang=lang)

def custom_login_required(f):
    """Custom login decorator that allows both authenticated users and anonymous sessions."""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated and not session.get('is_anonymous', False):
            create_anonymous_session()
        return f(*args, **kwargs)
    return decorated_function

def get_progress():
    """Retrieve learning progress from MongoDB with caching."""
    try:
        filter_kwargs = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session.get('sid')}
        progress_records = get_mongo_db().learning_materials.find(filter_kwargs)
        progress = {}
        for record in progress_records:
            try:
                course_id = record.get('course_id')
                if not course_id:
                    current_app.logger.warning(f"Invalid progress record, missing course_id: {record}", extra={'session_id': session.get('sid', 'no-session-id')})
                    continue
                progress[course_id] = {
                    'lessons_completed': record.get('lessons_completed', []),
                    'quiz_scores': record.get('quiz_scores', {}),
                    'current_lesson': record.get('current_lesson'),
                    'coins_earned': record.get('coins_earned', 0),
                    'badges_earned': record.get('badges_earned', [])
                }
            except Exception as e:
                current_app.logger.error(f"Error parsing progress record for course {record.get('course_id', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return progress
    except Exception as e:
        current_app.logger.error(f"Error retrieving progress from MongoDB: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return {}

def save_course_progress(course_id, course_progress):
    """Save course progress to MongoDB with validation."""
    try:
        if 'sid' not in session:
            create_anonymous_session()
            session.permanent = True
            session.modified = True
        if not isinstance(course_id, str) or not isinstance(course_progress, dict):
            current_app.logger.error(f"Invalid course_id or course_progress: course_id={course_id}, course_progress={course_progress}", extra={'session_id': session.get('sid', 'no-session-id')})
            return
        filter_kwargs = {'course_id': course_id} if is_admin() else {'user_id': current_user.id, 'course_id': course_id} if current_user.is_authenticated else {'session_id': session['sid'], 'course_id': course_id}
        update_data = {
            '$set': {
                'user_id': current_user.id if current_user.is_authenticated else None,
                'session_id': session['sid'],
                'course_id': course_id,
                'lessons_completed': course_progress.get('lessons_completed', []),
                'quiz_scores': course_progress.get('quiz_scores', {}),
                'current_lesson': course_progress.get('current_lesson'),
                'coins_earned': course_progress.get('coins_earned', 0),
                'badges_earned': course_progress.get('badges_earned', []),
                'updated_at': datetime.utcnow()
            }
        }
        get_mongo_db().learning_materials.update_one(filter_kwargs, update_data, upsert=True)
        current_app.logger.info(f"Saved progress for course {course_id}", extra={'session_id': session['sid']})
    except Exception as e:
        current_app.logger.error(f"Error saving progress to MongoDB for course {course_id}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})

def init_storage(app):
    """Initialize storage with app context and logger."""
    with app.app_context():
        current_app.logger.info("Initializing courses storage.", extra={'session_id': 'no-request-context'})
        try:
            existing_courses = get_mongo_db().learning_materials.find({'type': 'course'})
            if existing_courses.count() == 0:
                current_app.logger.info("Courses collection is empty. Initializing with default courses.", extra={'session_id': 'no-request-context'})
                default_courses = [
                    {
                        'type': 'course',
                        'id': course['id'],
                        '_id': ObjectId(),
                        'title_key': course['title_key'],
                        'title_en': course['title_en'],
                        'title_ha': course['title_ha'],
                        'description_en': course['description_en'],
                        'description_ha': course['description_ha'],
                        'is_premium': course.get('is_premium', False),
                        'roles': course.get('roles', []),
                        'modules': course.get('modules', []),
                        'created_at': datetime.utcnow()
                    } for course in courses_data.values()
                ]
                if default_courses:
                    get_mongo_db().learning_materials.insert_many(default_courses)
                    current_app.logger.info(f"Initialized courses collection with {len(default_courses)} default courses", extra={'session_id': 'no-request-context'})
        except Exception as e:
            current_app.logger.error(f"Error initializing courses: {str(e)}", extra={'session_id': 'no-request-context'})
            raise

def course_lookup(course_id):
    """Retrieve course by ID with validation."""
    course = get_mongo_db().learning_materials.find_one({'type': 'course', 'id': course_id})
    if not course or not isinstance(course, dict) or 'modules' not in course or not isinstance(course['modules'], list):
        current_app.logger.error(f"Invalid course data for course_id {course_id}: {course}", extra={'session_id': session.get('sid', 'no-session-id')})
        return None
    for module in course['modules']:
        if not isinstance(module, dict) or 'lessons' not in module or not isinstance(module['lessons'], list):
            current_app.logger.error(f"Invalid module data in course {course_id}: {module}", extra={'session_id': session.get('sid', 'no-session-id')})
            return None
    return course

def lesson_lookup(course, lesson_id):
    """Retrieve lesson and its module by lesson ID with validation."""
    if not course or not isinstance(course, dict) or 'modules' not in course:
        current_app.logger.error(f"Invalid course data for lesson lookup: {course}", extra={'session_id': session.get('sid', 'no-session-id')})
        return None, None
    for module in course['modules']:
        if not isinstance(module, dict) or 'lessons' not in module:
            current_app.logger.error(f"Invalid module data: {module}", extra={'session_id': session.get('sid', 'no-session-id')})
            continue
        for lesson in module['lessons']:
            if not isinstance(lesson, dict) or 'id' not in lesson:
                current_app.logger.error(f"Invalid lesson data: {lesson}", extra={'session_id': session.get('sid', 'no-session-id')})
                continue
            if lesson['id'] == lesson_id:
                return lesson, module
    current_app.logger.warning(f"Lesson {lesson_id} not found in course", extra={'session_id': session.get('sid', 'no-session-id')})
    return None, None

def calculate_progress_summary():
    """Calculate progress summary for dashboard, including badges."""
    progress = get_progress()
    progress_summary = []
    total_completed = 0
    total_quiz_scores = 0
    total_coins_earned = 0
    certificates_earned = 0
    badges_earned = []
    
    for course_id, course in courses_data.items():
        if not course_lookup(course_id):
            continue
        cp = progress.get(course_id, {'lessons_completed': [], 'current_lesson': None, 'quiz_scores': {}, 'coins_earned': 0, 'badges_earned': []})
        lessons_total = sum(len(m.get('lessons', [])) for m in course.get('modules', []))
        completed = len(cp.get('lessons_completed', []))
        percent = int((completed / lessons_total) * 100) if lessons_total > 0 else 0
        current_lesson_id = cp.get('current_lesson')
        if not current_lesson_id and lessons_total > 0:
            current_lesson_id = course['modules'][0]['lessons'][0]['id'] if course['modules'] and course['modules'][0]['lessons'] else None
        
        progress_summary.append({
            'course': course,
            'completed': completed,
            'total': lessons_total,
            'percent': percent,
            'current_lesson': current_lesson_id,
            'coins_earned': cp.get('coins_earned', 0)
        })
        
        total_completed += completed
        total_quiz_scores += sum(cp.get('quiz_scores', {}).values())
        total_coins_earned += cp.get('coins_earned', 0)
        badges_earned.extend(cp.get('badges_earned', []))
        if completed == lessons_total and lessons_total > 0:
            certificates_earned += 1
    
    return progress_summary, total_completed, total_quiz_scores, certificates_earned, total_coins_earned, badges_earned

@learning_hub_bp.route('/')
@learning_hub_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def main():
    """Main learning hub interface with all functionality."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    
    try:
        try:
            log_tool_usage(
                tool_name='learning_hub',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='main_view',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('learning_hub_log_error', default='Error logging learning hub activity. Please try again.'), 'warning')
        
        # Get courses filtered by role
        role_filter = session.get('role_filter', 'all')
        courses = {k: v for k, v in courses_data.items() if role_filter == 'all' or role_filter in v.get('roles', [])}
        
        # Get progress and calculate summary
        progress = get_progress()
        progress_summary, total_completed, total_quiz_scores, certificates_earned, total_coins_earned, badges_earned = calculate_progress_summary()
        
        # Get profile data
        profile_data = session.get('learning_hub_profile', {})
        if current_user.is_authenticated:
            profile_data['email'] = profile_data.get('email', current_user.email)
            profile_data['first_name'] = profile_data.get('first_name', current_user.username)
        
        # Create forms
        profile_form = LearningHubProfileForm(data=profile_data)
        upload_form = UploadForm()
        
        if request.method == 'POST' and request.form.get('action') == 'upload' and is_admin():
            if upload_form.validate_on_submit():
                if not allowed_file(upload_form.file.data.filename):
                    flash(trans('learning_hub_invalid_file_type', default='Invalid file type. Allowed: mp4, pdf, txt, md'), 'danger')
                else:
                    filename = secure_filename(upload_form.file.data.filename)
                    file_path = os.path.join(current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), filename)
                    upload_form.file.data.save(file_path)
                    
                    # Update MongoDB
                    course_id = upload_form.course_id.data
                    roles = [upload_form.roles.data] if upload_form.roles.data != 'all' else ['civil_servant', 'nysc', 'agent']
                    course_data = {
                        'type': 'course',
                        'id': course_id,
                        '_id': ObjectId(),
                        'title_key': f"learning_hub_course_{course_id}_title",
                        'title_en': upload_form.title.data,
                        'title_ha': upload_form.title.data,  # Placeholder; should support translation
                        'description_en': upload_form.description.data,
                        'description_ha': upload_form.description.data,  # Placeholder
                        'is_premium': upload_form.is_premium.data,
                        'roles': roles,
                        'modules': [{
                            'id': f"{course_id}-module-1",
                            'title_key': f"learning_hub_module_{course_id}_title",
                            'title_en': "Module 1",
                            'lessons': [{
                                'id': f"{course_id}-module-1-lesson-1",
                                'title_key': f"learning_hub_lesson_{course_id}_title",
                                'title_en': "Lesson 1",
                                'content_type': upload_form.content_type.data,
                                'content_path': f"uploads/{filename}",
                                'content_en': "Uploaded content",
                                'quiz_id': None
                            }]
                        }],
                        'created_at': datetime.utcnow()
                    }
                    
                    # Save to MongoDB
                    get_mongo_db().learning_materials.update_one(
                        {'type': 'course', 'id': course_id},
                        {'$set': course_data},
                        upsert=True
                    )
                    
                    flash(trans('learning_hub_upload_success', default='Content uploaded successfully'), 'success')
                    current_app.logger.info(f"Uploaded course {course_id}", extra={'session_id': session['sid']})
            else:
                flash(trans('learning_hub_upload_failed', default='Failed to upload content'), 'danger')
        
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        current_app.logger.info(f"Rendering main learning hub page", extra={'session_id': session.get('sid', 'no-session-id')})
        
        return render_template(
            'personal/LEARNINGHUB/learning_hub_main.html',
            courses=courses,
            progress=progress,
            progress_summary=progress_summary,
            total_completed=total_completed,
            total_courses=len(courses),
            quiz_scores_count=total_quiz_scores,
            certificates_earned=certificates_earned,
            total_coins_earned=total_coins_earned,
            badges_earned=badges_earned,
            profile_form=profile_form,
            upload_form=upload_form,
            profile_data=profile_data,
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang),
            tools=tools,
            bottom_nav_items=bottom_nav_items,
            role_filter=role_filter
        )
        
    except Exception as e:
        current_app.logger.error(f"Error rendering main learning hub page: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_error_loading", default="Error loading learning hub", lang=lang), "danger")
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        return render_template(
            'personal/LEARNINGHUB/learning_hub_main.html',
            courses={},
            progress={},
            progress_summary=[],
            total_completed=0,
            total_courses=0,
            quiz_scores_count=0,
            certificates_earned=0,
            total_coins_earned=0,
            badges_earned=[],
            profile_form=LearningHubProfileForm(),
            upload_form=UploadForm(),
            profile_data={},
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang),
            tools=tools,
            bottom_nav_items=bottom_nav_items,
            role_filter='all'
        ), 500

@learning_hub_bp.route('/api/course/<course_id>')
@custom_login_required
@requires_role(['personal', 'admin'])
def get_course_data(course_id):
    """API endpoint to get course data."""
    try:
        course = course_lookup(course_id)
        if not course:
            return jsonify({'success': False, 'message': trans('learning_hub_course_not_found', default='Course not found')}), 404
        
        progress = get_progress()
        course_progress = progress.get(course_id, {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []})
        
        return jsonify({
            'success': True,
            'course': course,
            'progress': course_progress
        })
    except Exception as e:
        current_app.logger.error(f"Error getting course data: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_course_load_error', default='Error loading course')}), 500

@learning_hub_bp.route('/api/lesson')
@custom_login_required
@requires_role(['personal', 'admin'])
def get_lesson_data():
    """API endpoint to get lesson data."""
    try:
        course_id = request.args.get('course_id')
        lesson_id = request.args.get('lesson_id')
        
        course = course_lookup(course_id)
        if not course:
            return jsonify({'success': False, 'message': trans('learning_hub_course_not_found', default='Course not found')}), 404
        
        lesson, module = lesson_lookup(course, lesson_id)
        if not lesson:
            return jsonify({'success': False, 'message': trans('learning_hub_lesson_not_found', default='Lesson not found')}), 404
        
        progress = get_progress()
        course_progress = progress.get(course_id, {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []})
        
        # Find next lesson
        next_lesson_id = None
        found = False
        for m in course['modules']:
            for l in m['lessons']:
                if found and l.get('id'):
                    next_lesson_id = l['id']
                    break
                if l['id'] == lesson_id:
                    found = True
            if next_lesson_id:
                break
        
        return jsonify({
            'success': True,
            'course': course,
            'lesson': lesson,
            'progress': course_progress,
            'next_lesson_id': next_lesson_id
        })
    except Exception as e:
        current_app.logger.error(f"Error getting lesson data: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_lesson_load_error', default='Error loading lesson')}), 500

@learning_hub_bp.route('/api/quiz')
@custom_login_required
@requires_role(['personal', 'admin'])
def get_quiz_data():
    """API endpoint to get quiz data."""
    try:
        course_id = request.args.get('course_id')
        quiz_id = request.args.get('quiz_id')
        
        course = course_lookup(course_id)
        if not course:
            return jsonify({'success': False, 'message': trans('learning_hub_course_not_found', default='Course not found')}), 404
        
        quiz = quizzes_data.get(quiz_id)
        if not quiz:
            return jsonify({'success': False, 'message': trans('learning_hub_quiz_not_found', default='Quiz not found')}), 404
        
        progress = get_progress()
        course_progress = progress.get(course_id, {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []})
        
        return jsonify({
            'success': True,
            'course': course,
            'quiz': quiz,
            'progress': course_progress
        })
    except Exception as e:
        current_app.logger.error(f"Error getting quiz data: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_quiz_load_error', default='Error loading quiz')}), 500

@learning_hub_bp.route('/api/lesson/action', methods=['POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def lesson_action():
    """Handle lesson actions like marking complete."""
    try:
        course_id = request.form.get('course_id')
        lesson_id = request.form.get('lesson_id')
        action = request.form.get('action')
        
        if action == 'mark_complete':
            progress = get_progress()
            if course_id not in progress:
                course_progress = {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': lesson_id, 'coins_earned': 0, 'badges_earned': []}
                progress[course_id] = course_progress
            else:
                course_progress = progress[course_id]
            
            if lesson_id not in course_progress['lessons_completed']:
                course_progress['lessons_completed'].append(lesson_id)
                course_progress['current_lesson'] = lesson_id
                # Award coins and badges
                coins_earned = 0
                badge_earned = None
                if course_id == 'tax_reforms_2025' and lesson_id == 'tax_reforms_2025-module-1-lesson-1':
                    coins_earned = 3
                elif course_id == 'digital_foundations' and lesson_id == 'digital_foundations-module-1-lesson-1':
                    coins_earned = 3
                    badge_earned = {'title_key': 'learning_hub_badge_digital_starter', 'title_en': 'Digital Starter'}
                course_progress['coins_earned'] = course_progress.get('coins_earned', 0) + coins_earned
                if badge_earned and badge_earned not in course_progress['badges_earned']:
                    course_progress['badges_earned'].append(badge_earned)
                save_course_progress(course_id, course_progress)
                
                # Send email if user has provided details and opted in
                profile = session.get('learning_hub_profile', {})
                if profile.get('send_email') and profile.get('email'):
                    try:
                        course = course_lookup(course_id)
                        lesson, _ = lesson_lookup(course, lesson_id)
                        
                        config = EMAIL_CONFIG.get("learning_hub_lesson_completed", {})
                        subject = trans(config.get("subject_key", "learning_hub_lesson_completed_subject"), default="Lesson Completed", lang=session.get('lang', 'en'))
                        template = config.get("template", "learning_hub_lesson_completed.html")
                        
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=profile['email'],
                            subject=subject,
                            template_name=template,
                            data={
                                "first_name": profile.get('first_name', ''),
                                "course_title": course.get('title_en', ''),
                                "lesson_title": lesson.get('title_en', ''),
                                "completed_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                                "cta_url": url_for('learning_hub.main', _external=True),
                                "unsubscribe_url": url_for('learning_hub.unsubscribe', email=profile['email'], _external=True),
                                "coins_earned": coins_earned,
                                "badge_earned": badge_earned.get('title_en') if badge_earned else None
                            },
                            lang=session.get('lang', 'en')
                        )
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email for lesson {lesson_id}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
                
                return jsonify({
                    'success': True,
                    'message': trans('learning_hub_lesson_completed', default='Lesson marked as complete'),
                    'coins_earned': coins_earned,
                    'badge_earned': badge_earned.get('title_en') if badge_earned else None
                })
            else:
                return jsonify({
                    'success': True,
                    'message': trans('learning_hub_lesson_already_completed', default='Lesson already completed'),
                    'coins_earned': 0,
                    'badge_earned': None
                })
        
        return jsonify({'success': False, 'message': trans('learning_hub_invalid_action', default='Invalid action')}), 400
    except Exception as e:
        current_app.logger.error(f"Error in lesson action: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_action_error', default='Error processing action')}), 500

@learning_hub_bp.route('/api/quiz/action', methods=['POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def quiz_action():
    """Handle quiz actions like submitting answers, including Reality Check Quiz."""
    try:
        course_id = request.form.get('course_id')
        quiz_id = request.form.get('quiz_id')
        action = request.form.get('action')
        
        if action == 'submit_quiz' or action == 'submit_reality_check':
            quiz = quizzes_data.get(quiz_id)
            if not quiz:
                return jsonify({'success': False, 'message': trans('learning_hub_quiz_not_found', default='Quiz not found')}), 404
            
            # Calculate score
            score = 0
            for i, question in enumerate(quiz['questions']):
                user_answer = request.form.get(f'q{i}')
                if user_answer and user_answer == question['answer_en']:
                    score += 1
            
            # Check if quiz score meets passmark (60% for most quizzes)
            passmark = 0.6 * len(quiz['questions']) if quiz_id != 'reality_check_quiz' else 0
            passed = score >= passmark
            
            # Save score and award coins/badges
            progress = get_progress()
            if course_id not in progress and quiz_id != 'reality_check_quiz':
                course_progress = {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []}
                progress[course_id] = course_progress
            else:
                course_progress = progress.get(course_id, {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []})
            
            coins_earned = 0
            badge_earned = None
            if quiz_id == 'quiz-tax-reforms-2025' and passed and quiz_id not in course_progress.get('quiz_scores', {}):
                coins_earned = 3
            elif quiz_id == 'reality_check_quiz' and quiz_id not in course_progress.get('quiz_scores', {}):
                coins_earned = 3
                badge_earned = {'title_key': 'learning_hub_badge_reality_check', 'title_en': 'Reality Check'}
            
            course_progress['quiz_scores'][quiz_id] = score
            course_progress['coins_earned'] = course_progress.get('coins_earned', 0) + coins_earned
            if badge_earned and badge_earned not in course_progress['badges_earned']:
                course_progress['badges_earned'].append(badge_earned)
            if quiz_id != 'reality_check_quiz':
                save_course_progress(course_id, course_progress)
            else:
                session['reality_check_score'] = score
                session.permanent = True
                session.modified = True
            
            # Send email notification for quiz completion
            profile = session.get('learning_hub_profile', {})
            if profile.get('send_email') and profile.get('email'):
                try:
                    course = course_lookup(course_id) if course_id else {'title_en': 'Reality Check Quiz'}
                    config = EMAIL_CONFIG.get("learning_hub_quiz_completed", {})
                    subject = trans(config.get("subject_key", "learning_hub_quiz_completed_subject"), default="Quiz Completed", lang=session.get('lang', 'en'))
                    template = config.get("template", "learning_hub_quiz_completed.html")
                    
                    send_email(
                        app=current_app,
                        logger=current_app.logger,
                        to_email=profile['email'],
                        subject=subject,
                        template_name=template,
                        data={
                            "first_name": profile.get('first_name', ''),
                            "course_title": course.get('title_en', ''),
                            "quiz_title": quiz.get('id', ''),
                            "score": score,
                            "total": len(quiz['questions']),
                            "passed": passed,
                            "coins_earned": coins_earned,
                            "badge_earned": badge_earned.get('title_en') if badge_earned else None,
                            "completed_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                            "cta_url": url_for('learning_hub.main', _external=True),
                            "unsubscribe_url": url_for('learning_hub.unsubscribe', email=profile['email'], _external=True)
                        },
                        lang=session.get('lang', 'en')
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to send email for quiz {quiz_id}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
            
            message = trans('learning_hub_quiz_submitted', default='Quiz submitted successfully')
            if quiz_id == 'reality_check_quiz':
                message = trans('learning_hub_quiz_submitted', default='Quiz submitted successfully') + '. '
                message += trans('learning_hub_quiz_recommendation', default='We recommend starting with the Digital Foundations course to build your ICT skills!') if score < 2 else trans('learning_hub_quiz_perfect', default='Great job! You have strong ICT basics!')
            
            return jsonify({
                'success': True,
                'message': message,
                'score': score,
                'total': len(quiz['questions']),
                'passed': passed,
                'coins_earned': coins_earned,
                'badge_earned': badge_earned.get('title_en') if badge_earned else None
            })
        
        return jsonify({'success': False, 'message': trans('learning_hub_invalid_action', default='Invalid action')}), 400
    except Exception as e:
        current_app.logger.error(f"Error in quiz action: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_quiz_error', default='Error processing quiz')}), 500

@learning_hub_bp.route('/api/set_role_filter', methods=['POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def set_role_filter():
    """Set role filter for course display."""
    try:
        role = request.form.get('role')
        if role not in ['all', 'civil_servant', 'nysc', 'agent']:
            return jsonify({'success': False, 'message': trans('learning_hub_invalid_role', default='Invalid role selected')}), 400
        session['role_filter'] = role
        session.permanent = True
        session.modified = True
        current_app.logger.info(f"Set role filter to {role}", extra={'session_id': session['sid']})
        return jsonify({'success': True, 'message': trans('learning_hub_role_updated', default='Role filter updated')})
    except Exception as e:
        current_app.logger.error(f"Error setting role filter: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_role_error', default='Error updating role filter')}), 500

@learning_hub_bp.route('/register_webinar', methods=['POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def register_webinar():
    """Handle webinar registration."""
    try:
        email = request.form.get('email')
        if not email:
            flash(trans('general_email_required', default='Email is required'), 'danger')
            return redirect(url_for('learning_hub.main'))
        
        # Save webinar registration to MongoDB
        get_mongo_db().webinar_registrations.insert_one({
            'email': email,
            'user_id': current_user.id if current_user.is_authenticated else None,
            'session_id': session['sid'],
            'registered_at': datetime.utcnow()
        })
        
        # Send confirmation email
        config = EMAIL_CONFIG.get("learning_hub_webinar_registration", {})
        subject = trans(config.get("subject_key", "learning_hub_webinar_registration_subject"), default="Webinar Registration Confirmed", lang=session.get('lang', 'en'))
        template = config.get("template", "learning_hub_webinar_registration.html")
        
        send_email(
            app=current_app,
            logger=current_app.logger,
            to_email=email,
            subject=subject,
            template_name=template,
            data={
                "first_name": session.get('learning_hub_profile', {}).get('first_name', ''),
                "webinar_date": "TBD",  # Placeholder; update with actual date
                "cta_url": url_for('learning_hub.main', _external=True),
                "unsubscribe_url": url_for('learning_hub.unsubscribe', email=email, _external=True)
            },
            lang=session.get('lang', 'en')
        )
        
        flash(trans('learning_hub_webinar_registered', default='Successfully registered for the webinar!'), 'success')
        current_app.logger.info(f"Registered email {email} for webinar", extra={'session_id': session['sid']})
        return redirect(url_for('learning_hub.main'))
    except Exception as e:
        current_app.logger.error(f"Error registering for webinar: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_webinar_error', default='Error registering for webinar'), 'danger')
        return redirect(url_for('learning_hub.main')), 500

@learning_hub_bp.route('/profile', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def profile():
    """Handle user profile form for first name and email."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    
    try:
        try:
            log_tool_usage(
                tool_name='learning_hub',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='profile_submit' if request.method == 'POST' else 'profile_view',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log profile action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('learning_hub_log_error', default='Error logging profile activity. Please try again.'), 'warning')
        
        profile_form = LearningHubProfileForm()
        if request.method == 'POST' and profile_form.validate_on_submit():
            session['learning_hub_profile'] = {
                'first_name': profile_form.first_name.data,
                'email': profile_form.email.data,
                'send_email': profile_form.send_email.data
            }
            session.permanent = True
            session.modified = True
            
            current_app.logger.info(f"Profile saved for user {current_user.id if current_user.is_authenticated else 'anonymous'}", extra={'session_id': session.get('sid', 'no-session-id')})
            flash(trans('learning_hub_profile_saved', default='Profile saved successfully', lang=lang), 'success')
            return redirect(url_for('personal.index'))
        
        elif request.method == 'POST':
            flash(trans('learning_hub_profile_failed', default='Failed to save profile', lang=lang), 'danger')
        
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        return render_template(
            'personal/learning_hub/learning_hub_profile.html',
            profile_form=profile_form,
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_profile_title', default='Learning Hub Profile', lang=lang),
            tools=tools,
            bottom_nav_items=bottom_nav_items
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in profile page: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_error_loading", default="Error loading profile", lang=lang), "danger")
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        return render_template(
            'personal/learning_hub/learning_hub_profile.html',
            profile_form=LearningHubProfileForm(),
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_profile_title', default='Learning Hub Profile', lang=lang),
            tools=tools,
            bottom_nav_items=bottom_nav_items
        ), 500

@learning_hub_bp.route('/unsubscribe/<email>')
@custom_login_required
@requires_role(['personal', 'admin'])
def unsubscribe(email):
    """Unsubscribe user from learning hub emails."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    try:
        try:
            log_tool_usage(
                tool_name='learning_hub',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='unsubscribe',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log unsubscribe action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('learning_hub_log_error', default='Error logging unsubscribe action. Continuing with unsubscription.'), 'warning')
        
        lang = session.get('lang', 'en')
        profile = session.get('learning_hub_profile', {})
        
        if is_admin() or (profile.get('email') == email and profile.get('send_email', False)):
            profile['send_email'] = False
            session['learning_hub_profile'] = profile
            session.permanent = True
            session.modified = True
            current_app.logger.info(f"Unsubscribed email {email}", extra={'session_id': session.get('sid', 'no-session-id')})
            flash(trans("learning_hub_unsubscribed_success", default="Successfully unsubscribed from emails", lang=lang), "success")
        else:
            current_app.logger.warning(f"Failed to unsubscribe email {email}: No matching profile or already unsubscribed", extra={'session_id': session.get('sid', 'no-session-id')})
            flash(trans("learning_hub_unsubscribe_failed", default="Failed to unsubscribe. Email not found or already unsubscribed.", lang=lang), "danger")
        
        return redirect(url_for('personal.index'))
        
    except Exception as e:
        current_app.logger.error(f"Error in unsubscribe: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_unsubscribe_error", default="Error processing unsubscribe request", lang=lang), "danger")
        return redirect(url_for('personal.index')), 500

@learning_hub_bp.route('/static/uploads/<path:filename>')
@custom_login_required
@requires_role(['personal', 'admin'])
def serve_uploaded_file(filename):
    """Serve uploaded files securely with caching."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    try:
        try:
            log_tool_usage(
                tool_name='learning_hub',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='serve_file',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log file serve action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('learning_hub_log_error', default='Error logging file access. Continuing with file serving.'), 'warning')
        
        response = send_from_directory(current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), filename)
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        current_app.logger.info(f"Served file: {filename}", extra={'session_id': session.get('sid', 'no-session-id')})
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error serving uploaded file {filename}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_file_not_found", default="File not found", lang=session.get('lang', 'en')), "danger")
        return redirect(url_for('personal.index')), 404

@learning_hub_bp.errorhandler(404)
def handle_not_found(e):
    """Handle 404 errors with user-friendly message."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
    bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
    current_app.logger.error(f"404 error on {request.path}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
    flash(trans("learning_hub_not_found", default="The requested page was not found. Please check the URL or return to the main page.", lang=lang), "danger")
    return render_template(
        'personal/LEARNINGHUB/learning_hub_main.html',
        courses={},
        progress={},
        progress_summary=[],
        total_completed=0,
        total_courses=0,
        quiz_scores_count=0,
        certificates_earned=0,
        total_coins_earned=0,
        badges_earned=[],
        profile_form=LearningHubProfileForm(),
        upload_form=UploadForm(),
        profile_data={},
        t=trans,
        lang=lang,
        tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang),
        tools=tools,
        bottom_nav_items=bottom_nav_items,
        role_filter='all'
    ), 404

@learning_hub_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
    bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'no-session-id')})
    flash(trans("learning_hub_csrf_error", default="Form submission failed due to a missing security token. Please refresh and try again.", lang=lang), "danger")
    return render_template(
        'personal/LEARNINGHUB/learning_hub_main.html',
        courses={},
        progress={},
        progress_summary=[],
        total_completed=0,
        total_courses=0,
        quiz_scores_count=0,
        certificates_earned=0,
        total_coins_earned=0,
        badges_earned=[],
        profile_form=LearningHubProfileForm(),
        upload_form=UploadForm(),
        profile_data={},
        t=trans,
        lang=lang,
        tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang),
        tools=tools,
        bottom_nav_items=bottom_nav_items,
        role_filter='all'
    ), 400

# Legacy route redirects for backward compatibility
@learning_hub_bp.route('/courses')
@custom_login_required
@requires_role(['personal', 'admin'])
def courses():
    """Redirect to main page with courses tab."""
    return redirect(url_for('learning_hub.main') + '#courses')

@learning_hub_bp.route('/courses/<course_id>')
@custom_login_required
@requires_role(['personal', 'admin'])
def course_overview(course_id):
    """Redirect to main page and load course overview."""
    return redirect(url_for('learning_hub.main') + f'#course-{course_id}')

@learning_hub_bp.route('/courses/<course_id>/lesson/<lesson_id>')
@custom_login_required
@requires_role(['personal', 'admin'])
def lesson(course_id, lesson_id):
    """Redirect to main page and load lesson."""
    return redirect(url_for('learning_hub.main') + f'#lesson-{course_id}-{lesson_id}')

@learning_hub_bp.route('/courses/<course_id>/quiz/<quiz_id>')
@custom_login_required
@requires_role(['personal', 'admin'])
def quiz(course_id, quiz_id):
    """Redirect to main page and load quiz."""
    return redirect(url_for('learning_hub.main') + f'#quiz-{course_id}-{quiz_id}')

@learning_hub_bp.route('/forum')
@custom_login_required
@requires_role(['personal', 'admin'])
def forum():
    """Placeholder for community forum."""
    lang = session.get('lang', 'en')
    flash(trans('learning_hub_forum_coming_soon', default='Community forum coming soon!'), 'info')
    return redirect(url_for('learning_hub.main'))
