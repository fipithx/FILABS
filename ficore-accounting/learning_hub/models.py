from datetime import datetime
from bson import ObjectId
from utils import get_mongo_db, trans, format_currency, clean_currency
from flask import current_app, session
from flask_login import current_user
import logging

logger = logging.getLogger('ficore_app.learning_hub')
logger.setLevel(logging.INFO)

# Course and quiz data
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
- Individuals earning 1000000 or less annually now enjoy 200000 rent relief, reducing their taxable income to 800000.
- Result: No PIT for most low-income earners.

### Value Added Tax (VAT) Relief
- No VAT on essential goods/services: food, education, rent, healthcare, baby products, electricity.
- Helps families reduce cost of living.

### Corporate Income Tax (CIT) Reforms
- **Small businesses (≤50000000 turnover):**
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
                "options_en": ["100000", "200000", "500000", "None"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt1_b",
                "answer_en": "200000"
            },
            {
                "question_key": "learning_hub_quiz_tax_reforms_q2",
                "question_en": "A business earning 30000000 yearly will pay what CIT rate?",
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

def init_storage(app):
    """Initialize storage with app context and logger."""
    with app.app_context():
        logger.info("Initializing courses storage.", extra={'session_id': 'no-request-context'})
        try:
            db = get_mongo_db()
            existing_courses = list(db.learning_materials.find({'type': 'course'}))
            existing_course_ids = {course['id'] for course in existing_courses}
            logger.info(f"Found {len(existing_courses)} existing courses: {existing_course_ids}", extra={'session_id': 'no-request-context'})
            
            # Prepare default courses, skipping duplicates
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
                } for course in courses_data.values() if course['id'] not in existing_course_ids
            ]
            
            # Initialize quizzes
            existing_quizzes = list(db.learning_materials.find({'type': 'quiz'}))
            existing_quiz_ids = {quiz['id'] for quiz in existing_quizzes}
            default_quizzes = [
                {
                    'type': 'quiz',
                    'id': quiz['id'],
                    '_id': ObjectId(),
                    'questions': quiz['questions'],
                    'created_at': datetime.utcnow()
                } for quiz in quizzes_data.values() if quiz['id'] not in existing_quiz_ids
            ]
            
            if default_courses:
                db.learning_materials.insert_many(default_courses)
                logger.info(f"Initialized courses collection with {len(default_courses)} default courses", extra={'session_id': 'no-request-context'})
            else:
                logger.info("No new courses to initialize; all default courses already exist", extra={'session_id': 'no-request-context'})
                
            if default_quizzes:
                db.learning_materials.insert_many(default_quizzes)
                logger.info(f"Initialized quizzes collection with {len(default_quizzes)} default quizzes", extra={'session_id': 'no-request-context'})
            else:
                logger.info("No new quizzes to initialize; all default quizzes already exist", extra={'session_id': 'no-request-context'})
        except Exception as e:
            logger.error(f"Error initializing courses: {str(e)}", exc_info=True, extra={'session_id': 'no-request-context'})
            raise

def get_progress():
    """Retrieve learning progress from MongoDB with caching."""
    try:
        filter_kwargs = {} if current_user.is_authenticated and hasattr(current_user, 'is_admin') and current_user.is_admin else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session.get('sid')}
        progress_records = get_mongo_db().learning_materials.find(filter_kwargs)
        progress = {}
        for record in progress_records:
            try:
                course_id = record.get('course_id')
                if not course_id:
                    logger.warning(f"Invalid progress record, missing course_id: {record}", extra={'session_id': session.get('sid', 'no-session-id')})
                    continue
                progress[course_id] = {
                    'lessons_completed': record.get('lessons_completed', []),
                    'quiz_scores': record.get('quiz_scores', {}),
                    'current_lesson': record.get('current_lesson'),
                    'coins_earned': record.get('coins_earned', 0),
                    'badges_earned': record.get('badges_earned', [])
                }
            except Exception as e:
                logger.error(f"Error parsing progress record for course {record.get('course_id', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return progress
    except Exception as e:
        logger.error(f"Error retrieving progress from MongoDB: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return {}

def save_course_progress(course_id, course_progress):
    """Save course progress to MongoDB with validation."""
    try:
        if 'sid' not in session:
            from session_utils import create_anonymous_session
            create_anonymous_session()
            session.permanent = True
            session.modified = True
        if not isinstance(course_id, str) or not isinstance(course_progress, dict):
            logger.error(f"Invalid course_id or course_progress: course_id={course_id}, course_progress={course_progress}", extra={'session_id': session.get('sid', 'no-session-id')})
            return
        filter_kwargs = {'course_id': course_id} if current_user.is_authenticated and hasattr(current_user, 'is_admin') and current_user.is_admin else {'user_id': current_user.id, 'course_id': course_id} if current_user.is_authenticated else {'session_id': session['sid'], 'course_id': course_id}
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
        logger.info(f"Saved progress for course {course_id}", extra={'session_id': session['sid']})
    except Exception as e:
        logger.error(f"Error saving progress to MongoDB for course {course_id}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})

def course_lookup(course_id):
    """Retrieve course by ID with validation and fallback to in-memory data."""
    try:
        if course_id == 'all':
            return courses_data
        course = get_mongo_db().learning_materials.find_one({'type': 'course', 'id': course_id})
        if course and isinstance(course, dict) and 'modules' in course and isinstance(course['modules'], list):
            return course
        logger.warning(f"Course {course_id} not found in MongoDB or invalid, falling back to in-memory data", extra={'session_id': session.get('sid', 'no-session-id')})
        course = courses_data.get(course_id)
        if not course or not isinstance(course, dict) or 'modules' not in course or not isinstance(course['modules'], list):
            logger.error(f"Invalid course data for {course_id} in in-memory data", extra={'session_id': session.get('sid', 'no-session-id')})
            return None
        return course
    except Exception as e:
        logger.error(f"Error retrieving course {course_id}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return None

def lesson_lookup(course, lesson_id):
    """Retrieve lesson and its module from a course."""
    try:
        if not course or not isinstance(course, dict) or 'modules' not in course:
            logger.error(f"Invalid course data for lesson lookup: {course}", extra={'session_id': session.get('sid', 'no-session-id')})
            return None, None
        for module in course['modules']:
            for lesson in module.get('lessons', []):
                if lesson.get('id') == lesson_id:
                    return lesson, module
        logger.warning(f"Lesson {lesson_id} not found in course", extra={'session_id': session.get('sid', 'no-session-id')})
        return None, None
    except Exception as e:
        logger.error(f"Error looking up lesson {lesson_id}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return None, None

def calculate_progress_summary():
    """Calculate progress summary for display."""
    try:
        progress = get_progress()
        total_completed = 0
        total_quiz_scores = 0
        total_coins_earned = 0
        certificates_earned = 0
        badges_earned = []
        progress_summary = []

        for course_id, course_progress in progress.items():
            course = course_lookup(course_id)
            if not course:
                continue
            lessons_completed = course_progress.get('lessons_completed', [])
            quiz_scores = course_progress.get('quiz_scores', {})
            total_coins_earned += clean_currency(course_progress.get('coins_earned', 0))
            badges_earned.extend(course_progress.get('badges_earned', []))

            total_completed += len(lessons_completed)
            total_quiz_scores += len(quiz_scores)

            # Count certificates (e.g., if all lessons in a course are completed)
            total_lessons = sum(len(module.get('lessons', [])) for module in course.get('modules', []))
            if len(lessons_completed) == total_lessons:
                certificates_earned += 1

            progress_summary.append({
                'course_id': course_id,
                'course_title': course.get('title_en', 'Unknown'),
                'lessons_completed': len(lessons_completed),
                'total_lessons': total_lessons,
                'quiz_scores': quiz_scores,
                'coins_earned': format_currency(course_progress.get('coins_earned', 0), currency='NGN')
            })

        return (
            progress_summary,
            total_completed,
            total_quiz_scores,
            certificates_earned,
            format_currency(total_coins_earned, currency='NGN'),
            badges_earned
        )
    except Exception as e:
        logger.error(f"Error calculating progress summary: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return [], 0, 0, 0, format_currency(0, currency='NGN'), []
