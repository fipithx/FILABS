from flask import Blueprint, jsonify, current_app, redirect, url_for, flash, render_template, request, session, make_response
from flask_login import current_user, login_required
from utils import requires_role, is_admin, get_mongo_db, limiter
import utils
from translations import trans
from datetime import datetime
from bson import ObjectId
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

personal_bp = Blueprint('personal', __name__, url_prefix='/personal', template_folder='templates/personal')

# Register all personal finance sub-blueprints
from personal.bill import bill_bp
from personal.budget import budget_bp
from personal.emergency_fund import emergency_fund_bp
from personal.financial_health import financial_health_bp
from personal.learning_hub import learning_hub_bp
from personal.net_worth import net_worth_bp
from personal.quiz import quiz_bp

personal_bp.register_blueprint(bill_bp)
personal_bp.register_blueprint(budget_bp)
personal_bp.register_blueprint(emergency_fund_bp)
personal_bp.register_blueprint(financial_health_bp)
personal_bp.register_blueprint(learning_hub_bp)
personal_bp.register_blueprint(net_worth_bp)
personal_bp.register_blueprint(quiz_bp)

def init_app(app):
    """Initialize all personal finance sub-blueprints."""
    try:
        for blueprint in [bill_bp, budget_bp, emergency_fund_bp, financial_health_bp, learning_hub_bp, net_worth_bp, quiz_bp]:
            if hasattr(blueprint, 'init_app'):
                blueprint.init_app(app)
                current_app.logger.info(f"Initialized {blueprint.name} blueprint", extra={'session_id': 'no-request-context'})
        current_app.logger.info("Personal finance blueprints initialized successfully", extra={'session_id': 'no-request-context'})
    except Exception as e:
        current_app.logger.error(f"Error initializing personal finance blueprints: {str(e)}", extra={'session_id': 'no-request-context'})
        raise

# --- NEW HELPER FUNCTION ---
def get_recent_activities(user_id=None, is_admin_user=False, db=None):
    if db is None:
        db = get_mongo_db()
    query = {} if is_admin_user else {'user_id': str(user_id)}
    activities = []

    # Fetch recent bills
    bills = db.bills.find(query).sort('created_at', -1).limit(5)
    for bill in bills:
        if not bill.get('created_at') or not bill.get('bill_name'):
            logger.warning(f"Skipping invalid bill record: {bill.get('_id')}")
            continue
        activities.append({
            'type': 'bill',
            'description': trans('recent_activity_bill_added', default='Added bill: {name}', name=bill.get('bill_name', 'Unknown')),
            'timestamp': bill.get('created_at', datetime.utcnow()).isoformat(),
            'details': {
                'amount': bill.get('amount', 0),
                'due_date': bill.get('due_date', 'N/A'),
                'status': bill.get('status', 'Unknown')
            },
            'icon': 'bi-receipt'
        })

    def _get_recent_activities_data(user_id=None, is_admin_user=False, db=None):
    if db is None:
        db = get_mongo_db()
    query = {} if is_admin_user else {'user_id': str(user_id)}
    activities = []

    # Fetch recent bills
    bills = db.bills.find(query).sort('created_at', -1).limit(5)
    for bill in bills:
        if not bill.get('created_at') or not bill.get('bill_name'):
            logger.warning(f"Skipping invalid bill record: {bill.get('_id')}")
            continue
        activities.append({
            'type': 'bill',
            'description': trans('recent_activity_bill_added', default='Added bill: {name}', name=bill.get('bill_name', 'Unknown')),
            'timestamp': bill.get('created_at', datetime.utcnow()).isoformat(),
            'details': {
                'amount': bill.get('amount', 0),
                'due_date': bill.get('due_date', 'N/A'),
                'status': bill.get('status', 'Unknown')
            },
            'icon': 'bi-receipt'
        })

    # Fetch recent budgets
    budgets = db.budgets.find(query).sort('created_at', -1).limit(5)
    for budget in budgets:
        activities.append({
            'type': 'budget',
            'description': trans('recent_activity_budget_created', default='Created budget with income: {amount}', amount=budget.get('income', 0)),
            'timestamp': budget.get('created_at', datetime.utcnow()).isoformat(),
            'details': {
                'income': budget.get('income', 0),
                'surplus_deficit': budget.get('surplus_deficit', 0)
            },
            'icon': 'bi-cash-coin'  # Add an icon for the template
        })

    # Fetch recent net worth records
    net_worths = db.net_worth_data.find(query).sort('created_at', -1).limit(5)
    for nw in net_worths:
        activities.append({
            'type': 'net_worth',
            'description': trans('recent_activity_net_worth_calculated', default='Calculated net worth: {amount}', amount=nw.get('net_worth', 0)),
            'timestamp': nw.get('created_at', datetime.utcnow()).isoformat(),
            'details': {
                'net_worth': nw.get('net_worth', 0),
                'total_assets': nw.get('total_assets', 0),
                'total_liabilities': nw.get('total_liabilities', 0)
            },
            'icon': 'bi-graph-up'  # Add an icon for the template
        })

    # Fetch recent financial health scores
    health_scores = db.financial_health_scores.find(query).sort('created_at', -1).limit(5)
    for hs in health_scores:
        activities.append({
            'type': 'financial_health',
            'description': trans('recent_activity_health_score', default='Calculated financial health score: {score}', score=hs.get('score', 0)),
            'timestamp': hs.get('created_at', datetime.utcnow()).isoformat(),
            'details': {
                'score': hs.get('score', 0),
                'status': hs.get('status', 'Unknown')
            },
            'icon': 'bi-heart-pulse'  # Add an icon for the template
        })

    # Fetch recent emergency fund plans
    emergency_funds = db.emergency_funds.find(query).sort('created_at', -1).limit(5)
    for ef in emergency_funds:
        activities.append({
            'type': 'emergency_fund',
            'description': trans('recent_activity_emergency_fund_created', default='Created emergency fund plan with target: {amount}', amount=ef.get('target_amount', 0)),
            'timestamp': ef.get('created_at', datetime.utcnow()).isoformat(),
            'details': {
                'target_amount': ef.get('target_amount', 0),
                'savings_gap': ef.get('savings_gap', 0),
                'monthly_savings': ef.get('monthly_savings', 0)
            },
            'icon': 'bi-piggy-bank'  # Add an icon for the template
        })

    # Fetch recent quiz results
    quizzes = db.quiz_responses.find(query).sort('created_at', -1).limit(5)
    for quiz in quizzes:
        activities.append({
            'type': 'quiz',
            'description': trans('recent_activity_quiz_completed', default='Completed financial quiz with score: {score}', score=quiz.get('score', 0)),
            'timestamp': quiz.get('created_at', datetime.utcnow()).isoformat(),
            'details': {
                'score': quiz.get('score', 0),
                'personality': quiz.get('personality', 'N/A')
            },
            'icon': 'bi-question-circle'  # Add an icon for the template
        })

    # Fetch recent learning hub progress
    learning_hub_progress = db.learning_materials.find(query).sort('updated_at', -1).limit(5)
    for progress in learning_hub_progress:
        if progress.get('course_id'):
            activities.append({
                'type': 'learning_hub',
                'description': trans('recent_activity_learning_hub_progress', default='Progress in course: {course_id}', course_id=progress.get('course_id', 'N/A')),
                'timestamp': progress.get('updated_at', datetime.utcnow()).isoformat(),
                'details': {
                    'course_id': progress.get('course_id', 'N/A'),
                    'lessons_completed': len(progress.get('lessons_completed', [])),
                    'current_lesson': progress.get('current_lesson', 'N/A')
                },
                'icon': 'bi-book'  # Add an icon for the template
            })

    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return activities[:10]

# --- NEW HELPER FUNCTION FOR NOTIFICATIONS ---
def _get_notifications_data(user_id, is_admin_user, db):
    """
    Helper function to fetch recent notifications for a user.
    """
    query = {} if is_admin_user else {'user_id': str(user_id)}
    notifications = db.reminder_logs.find(query).sort('sent_at', -1).limit(10)
    return [{
        'id': str(n.get('notification_id', ObjectId())),
        'message': n.get('message', 'No message'),
        'type': n.get('type', 'info'),
        'timestamp': n.get('sent_at', datetime.utcnow()).isoformat(),
        'read': n.get('read_status', False),
        'icon': get_notification_icon(n.get('type', 'info'))
    } for n in notifications]

# --- NEW HELPER FUNCTION FOR NOTIFICATION ICONS ---
def get_notification_icon(notification_type):
    """
    Map notification types to Bootstrap Icons.
    """
    icons = {
        'info': 'bi-info-circle',
        'warning': 'bi-exclamation-triangle',
        'error': 'bi-x-circle',
        'success': 'bi-check-circle'
    }
    return icons.get(notification_type, 'bi-info-circle')

@personal_bp.route('/')
@login_required
@requires_role(['personal', 'admin'])
def index():
    """Render the personal finance dashboard."""
    try:
        current_app.logger.info(f"Accessing personal.index - User: {current_user.id}, Authenticated: {current_user.is_authenticated}, Session: {dict(session)}")
        db = get_mongo_db()
        notifications = _get_notifications_data(current_user.id, is_admin(), db)
        activities = _get_recent_activities_data(user_id=current_user.id, is_admin_user=is_admin(), db=db)
        notification = notifications[0] if notifications else None
        activity = activities[0] if activities else None
        response = make_response(render_template(
            'personal/GENERAL/index.html',
            title=trans('general_welcome', lang=session.get('lang', 'en'), default='Welcome'),
            notifications=notifications,
            notification=notification,
            activities=activities,
            activity=activity,
            tools_for_template=utils.PERSONAL_TOOLS,  # Explicitly pass
            explore_features_for_template=utils.PERSONAL_EXPLORE_FEATURES,  # Explicitly pass
            is_admin=is_admin(),
            is_anonymous=False,
            is_public=False
        ))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        current_app.logger.error(f"Error rendering personal index: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('general_error', default='An error occurred'), 'danger')
        response = make_response(render_template(
            'personal/GENERAL/error.html',
            error_message="Unable to load the personal finance dashboard due to an internal error.",
            title=trans('general_welcome', lang=session.get('lang', 'en'), default='Welcome'),
            is_admin=is_admin()
        ), 500)
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response
        
@personal_bp.route('/notification_count')
@login_required
@requires_role(['personal', 'admin'])
def notification_count():
    """Return the count of unread notifications for the current user."""
    try:
        db = get_mongo_db()
        query = {'read_status': False} if is_admin() else {'user_id': str(current_user.id), 'read_status': False}
        count = db.reminder_logs.count_documents(query)
        current_app.logger.debug(f"Fetched notification count {count} for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'count': count}), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching notification count: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('general_something_went_wrong', default='Failed to fetch notification count'), 'warning')
        return jsonify({'error': trans('general_something_went_wrong', default='Failed to fetch notification count')}), 500

@personal_bp.route('/notifications')
@login_required
@requires_role(['personal', 'admin'])
def notifications():
    """Return the list of recent notifications for the current user."""
    try:
        db = get_mongo_db()
        query = {} if is_admin() else {'user_id': str(current_user.id)}
        notifications = list(db.reminder_logs.find(query).sort('sent_at', -1).limit(10))

        # Handle cases where notification_id or sent_at might be missing
        notification_ids = []
        for n in notifications:
            if 'notification_id' in n and not n.get('read_status', False):
                notification_ids.append(n['notification_id'])

        if notification_ids:
            db.reminder_logs.update_many(
                {'notification_id': {'$in': notification_ids}},
                {'$set': {'read_status': True}}
            )

        result = []
        for n in notifications:
            try:
                result.append({
                    'id': str(n.get('notification_id', ObjectId())),
                    'message': n.get('message', 'No message'),
                    'type': n.get('type', 'info'),
                    'timestamp': n.get('sent_at', datetime.utcnow()).isoformat(),
                    'read': n.get('read_status', False),
                    'icon': get_notification_icon(n.get('type', 'info'))
                })
            except Exception as e:
                current_app.logger.warning(f"Skipping invalid notification: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                continue

        current_app.logger.debug(f"Fetched {len(result)} notifications for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching notifications: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('general_something_went_wrong', default='Failed to fetch notifications'), 'warning')
        return jsonify({'error': trans('general_something_went_wrong', default='Failed to fetch notifications')}), 500

@personal_bp.route('/recent_activity')
@login_required
@requires_role(['personal', 'admin'])
def recent_activity():
    """Return recent activity across all personal finance tools for the current user."""
    try:
        activities = _get_recent_activities_data(user_id=current_user.id, is_admin_user=is_admin())
        current_app.logger.debug(f"Fetched {len(activities)} recent activities for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify(activities), 200
    except Exception as e:
        current_app.logger.error(f"Error in personal.recent_activity: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('general_something_went_wrong', default='Failed to fetch recent activity'), 'warning')
        return jsonify({'error': trans('general_something_went_wrong', default='Failed to fetch recent activity')}), 500
