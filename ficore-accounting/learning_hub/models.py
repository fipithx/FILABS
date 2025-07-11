from flask import current_app, session
from datetime import datetime
from bson import ObjectId
from .utils import get_mongo_db, format_currency, clean_currency

# Courses data with thematic organization
courses_data = {
    "personal_finance": {
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
            "theme": "personal_finance",
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
                            "content_en": "Understanding different sources of income is crucial for effective budgeting.",
                            "quiz_id": "quiz-1-1"
                        },
                        {
                            "id": "budgeting_101-module-1-lesson-2",
                            "title_key": "learning_hub_lesson_net_income_title",
                            "title_en": "Calculating Net Income",
                            "content_type": "text",
                            "content_en": "Learn how to calculate your net income after taxes and deductions.",
                            "quiz_id": None
                        }
                    ]
                }
            ]
        },
        "savings_basics": {
            "id": "savings_basics",
            "title_en": "Savings Fundamentals",
            "title_ha": "Asalin Tattara Kudi",
            "description_en": "Master the fundamentals of saving money effectively.",
            "description_ha": "Koyon asalin tattara kudi yadda ya kamata.",
            "title_key": "learning_hub_course_savings_basics_title",
            "desc_key": "learning_hub_course_savings_basics_desc",
            "is_premium": False,
            "roles": ["civil_servant", "nysc", "agent"],
            "theme": "personal_finance",
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
                            "content_en": "Learn proven strategies for building your savings effectively.",
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
            "description_en": "Test your financial knowledge with our comprehensive quiz.",
            "description_ha": "Gwada ilimin ku na kudi da jarabawa mai cikakke.",
            "title_key": "learning_hub_course_financial_quiz_title",
            "desc_key": "learning_hub_course_financial_quiz_desc",
            "is_premium": False,
            "roles": ["civil_servant", "nysc", "agent"],
            "theme": "personal_finance",
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
                            "content_en": "This comprehensive quiz will help assess your financial knowledge.",
                            "quiz_id": "quiz-financial-1"
                        }
                    ]
                }
            ]
        }
    },
    "compliance": {
        "tax_reforms_2025": {
            "id": "tax_reforms_2025",
            "title_en": "2025 Tax Reforms – What You Need to Know",
            "title_ha": "Gyaran Haraji na 2025 – Abin da Yakamata Ku Sani",
            "description_en": "Understand the key changes in Nigeria's 2025 tax reforms.",
            "description_ha": "Fahimci mahimman canje-canje a cikin gyaran haraji na Najeriya na 2025.",
            "title_key": "learning_hub_course_tax_reforms_2025_title",
            "desc_key": "learning_hub_course_tax_reforms_2025_desc",
            "is_premium": False,
            "roles": ["civil_servant", "agent"],
            "theme": "compliance",
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
                            "content_en": """
### Personal Income Tax (PIT) Changes
- Individuals earning 1000000 or less annually now enjoy 200000 rent relief.
- Result: No PIT for most low-income earners.

### Value Added Tax (VAT) Relief
- No VAT on essential goods/services: food, education, rent, healthcare.

### Corporate Income Tax (CIT) Reforms
- Small businesses (≤50000000 turnover): 0% CIT.
- Large companies: CIT reduced from 30% to 27.5% (2025).
                            """,
                            "quiz_id": "quiz-tax-reforms-2025"
                        }
                    ]
                }
            ]
        }
    },
    "tool_tutorials": {
        "digital_foundations": {
            "id": "digital_foundations",
            "title_en": "Digital Foundations",
            "title_ha": "Tushen Dijital",
            "description_en": "Learn the basics of computers, internet tools, and AI tools like ChatGPT.",
            "description_ha": "Koyon asalin kwamfutoci, kayan aikin intanet, da kayan aikin AI kamar ChatGPT.",
            "title_key": "learning_hub_digital_foundations_title",
            "desc_key": "learning_hub_digital_foundations_desc",
            "is_premium": False,
            "roles": ["civil_servant", "nysc", "agent"],
            "theme": "tool_tutorials",
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
                            "content_en": "Understand the basic components of a computer.",
                            "quiz_id": None
                        }
                    ]
                }
            ]
        }
    }
}

quizzes_data = {
    "quiz-1-1": {
        "id": "quiz-1-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_income_q1",
                "question_en": "What is the most common source of income for most people?",
                "options_en": ["Salary/Wages", "Business Income", "Investment Returns", "Other Sources"],
                "answer_en": "Salary/Wages"
            }
        ]
    },
    "quiz-financial-1": {
        "id": "quiz-financial-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_financial_q1",
                "question_en": "What percentage of income should you ideally save?",
                "options_en": ["20%", "10%", "5%", "30%"],
                "answer_en": "20%"
            }
        ]
    },
    "quiz-tax-reforms-2025": {
        "id": "quiz-tax-reforms-2025",
        "questions": [
            {
                "question_key": "learning_hub_quiz_tax_reforms_q1",
                "question_en": "What is the new rent relief threshold for PIT?",
                "options_en": ["100000", "200000", "500000", "None"],
                "answer_en": "200000"
            }
        ]
    }
}

def init_storage(app):
    """Initialize storage with app context and logger."""
    with app.app_context():
        current_app.logger.info("Initializing courses storage.", extra={'session_id': 'no-request-context'})
        try:
            db = get_mongo_db()
            existing_courses = list(db.learning_materials.find({'type': 'course'}))
            existing_course_ids = {course['id'] for course in existing_courses}
            current_app.logger.info(f"Found {len(existing_courses)} existing courses: {existing_course_ids}", extra={'session_id': 'no-request-context'})
            
            default_courses = []
            for theme, courses in courses_data.items():
                for course_id, course in courses.items():
                    if course_id not in existing_course_ids:
                        default_courses.append({
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
                            'theme': course.get('theme', theme),
                            'modules': course.get('modules', []),
                            'created_at': datetime.utcnow()
                        })
            
            if default_courses:
                db.learning_materials.insert_many(default_courses)
                current_app.logger.info(f"Initialized courses collection with {len(default_courses)} default courses", extra={'session_id': 'no-request-context'})
            else:
                current_app.logger.info("No new courses to initialize", extra={'session_id': 'no-request-context'})
        except Exception as e:
            current_app.logger.error(f"Error initializing courses: {str(e)}", exc_info=True, extra={'session_id': 'no-request-context'})
            raise

def course_lookup(course_id):
    """Retrieve course by ID with validation and fallback."""
    try:
        course = get_mongo_db().learning_materials.find_one({'type': 'course', 'id': course_id})
        if course and isinstance(course, dict) and 'modules' in course and isinstance(course['modules'], list):
            return course
        current_app.logger.warning(f"Course {course_id} not found in MongoDB or invalid, falling back to in-memory data", extra={'session_id': session.get('sid', 'no-session-id')})
        for theme, courses in courses_data.items():
            if course_id in courses:
                course = courses[course_id]
                if isinstance(course, dict) and 'modules' in course and isinstance(course['modules'], list):
                    return course
        current_app.logger.error(f"Invalid course data for course_id {course_id}", extra={'session_id': session.get('sid', 'no-session-id')})
        return None
    except Exception as e:
        current_app.logger.error(f"Error retrieving course {course_id}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return None

def get_courses_by_role(role_filter):
    """Retrieve courses filtered by user role."""
    try:
        filtered_courses = {}
        for theme, courses in courses_data.items():
            filtered_courses[theme] = {
                k: v for k, v in courses.items()
                if role_filter == 'all' or role_filter in v.get('roles', [])
            }
        return filtered_courses
    except Exception as e:
        current_app.logger.error(f"Error retrieving courses by role {role_filter}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return {}

def get_progress():
    """Retrieve learning progress from MongoDB."""
    from flask_login import current_user
    try:
        filter_kwargs = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session.get('sid')}
        progress_records = get_mongo_db().learning_materials.find(filter_kwargs)
        progress = {}
        for record in progress_records:
            course_id = record.get('course_id')
            if not course_id:
                current_app.logger.warning(f"Invalid progress record: {record}", extra={'session_id': session.get('sid', 'no-session-id')})
                continue
            progress[course_id] = {
                'lessons_completed': record.get('lessons_completed', []),
                'quiz_scores': record.get('quiz_scores', {}),
                'current_lesson': record.get('current_lesson'),
                'coins_earned': record.get('coins_earned', 0),
                'badges_earned': record.get('badges_earned', [])
            }
        return progress
    except Exception as e:
        current_app.logger.error(f"Error retrieving progress: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return {}

def save_course_progress(course_id, course_progress):
    """Save course progress to MongoDB."""
    from flask_login import current_user
    try:
        if not isinstance(course_id, str) or not isinstance(course_progress, dict):
            current_app.logger.error(f"Invalid course_id or course_progress: {course_id}, {course_progress}", extra={'session_id': session.get('sid', 'no-session-id')})
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
        current_app.logger.error(f"Error saving progress for course {course_id}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})

def lesson_lookup(course, lesson_id):
    """Retrieve lesson and its module by lesson ID."""
    if not course or not isinstance(course, dict) or 'modules' not in course:
        current_app.logger.error(f"Invalid course data: {course}", extra={'session_id': session.get('sid', 'no-session-id')})
        return None, None
    for module in course['modules']:
        for lesson in module.get('lessons', []):
            if lesson.get('id') == lesson_id:
                return lesson, module
    current_app.logger.warning(f"Lesson {lesson_id} not found in course", extra={'session_id': session.get('sid', 'no-session-id')})
    return None, None

def calculate_progress_summary():
    """Calculate progress summary for dashboard."""
    progress = get_progress()
    progress_summary = []
    total_completed = 0
    total_quiz_scores = 0
    total_coins_earned = 0
    certificates_earned = 0
    badges_earned = []
    
    for theme, courses in courses_data.items():
        for course_id, course in courses.items():
            db_course = course_lookup(course_id)
            if not db_course:
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
                'coins_earned': format_currency(cp.get('coins_earned', 0), currency='NGN')
            })
            
            total_completed += completed
            total_quiz_scores += sum(clean_currency(score) for score in cp.get('quiz_scores', {}).values())
            total_coins_earned += clean_currency(cp.get('coins_earned', 0))
            badges_earned.extend(cp.get('badges_earned', []))
            if completed == lessons_total and lessons_total > 0:
                certificates_earned += 1
    
    return progress_summary, total_completed, total_quiz_scores, certificates_earned, format_currency(total_coins_earned, currency='NGN'), badges_earned