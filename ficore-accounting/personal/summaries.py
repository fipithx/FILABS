from flask import Blueprint, jsonify, current_app, session, request
from flask_login import current_user, login_required
from datetime import datetime
from models.global import get_budgets, get_bills, get_net_worth, get_financial_health, get_emergency_funds
from utils import get_mongo_db, trans, requires_role
from bson import ObjectId
import logging

summaries_bp = Blueprint('summaries', __name__, url_prefix='/summaries')

# Configure logging
logger = logging.getLogger('ficore_app')
logger.setLevel(logging.INFO)

# --- HELPER FUNCTION ---
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
            'icon': 'bi-cash-coin'
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
            'icon': 'bi-graph-up'
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
            'icon': 'bi-heart-pulse'
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
            'icon': 'bi-piggy-bank'
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
            'icon': 'bi-question-circle'
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
                'icon': 'bi-book'
            })

    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return activities[:10]

# --- HELPER FUNCTION ---
def _get_recent_activities_data(user_id=None, is_admin_user=False, db=None):
    """
    Fetch recent activities across all personal finance tools for a user.

    Args:
        user_id: ID of the user (optional for admin)
        is_admin_user: Whether the user is an admin (default: False)
        db: MongoDB database instance (optional)

    Returns:
        list: List of recent activity records
    """
    if db is None:
        db = get_mongo_db()
    return get_recent_activities(user_id, is_admin_user, db)

@summaries_bp.route('/budget/summary')
@login_required
@requires_role(['personal', 'admin'])
def budget_summary():
    """Fetch the latest budget summary for the authenticated user."""
    try:
        db = get_mongo_db()
        budgets = get_budgets(db, {'user_id': current_user.id})
        total_budget = 0
        if budgets:
            latest_budget = budgets[0]
            total_budget = (latest_budget.get('income', 0) - 
                           (latest_budget.get('fixed_expenses', 0) + 
                            latest_budget.get('variable_expenses', 0)))
        logger.info(f"Fetched budget summary for user {current_user.id}: {total_budget}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'totalBudget': total_budget}), 200
    except Exception as e:
        logger.error(f"Error fetching budget summary for user {current_user.id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('budget_summary_error', default='Error fetching budget summary')}), 500

@summaries_bp.route('/bill/summary')
@login_required
@requires_role(['personal', 'admin'])
def bill_summary():
    """Fetch the total of upcoming bills for the authenticated user."""
    try:
        db = get_mongo_db()
        today = datetime.utcnow()
        bills = get_bills(db, {
            'user_id': current_user.id,
            'due_date': {'$gte': today},
            'status': 'pending'
        })
        total_upcoming_bills = sum(bill.get('amount', 0) for bill in bills)
        logger.info(f"Fetched bill summary for user {current_user.id}: {total_upcoming_bills}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'totalUpcomingBills': total_upcoming_bills}), 200
    except Exception as e:
        logger.error(f"Error fetching bill summary for user {current_user.id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('bill_summary_error', default='Error fetching bill summary')}), 500

@summaries_bp.route('/net_worth/summary')
@login_required
@requires_role(['personal', 'admin'])
def net_worth_summary():
    """Fetch the latest net worth for the authenticated user."""
    try:
        db = get_mongo_db()
        net_worth_records = get_net_worth(db, {'user_id': current_user.id})
        net_worth = net_worth_records[0].get('net_worth', 0) if net_worth_records else 0
        logger.info(f"Fetched net worth summary for user {current_user.id}: {net_worth}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'netWorth': net_worth}), 200
    except Exception as e:
        logger.error(f"Error fetching net worth summary for user {current_user.id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('net_worth_summary_error', default='Error fetching net worth summary')}), 500

@summaries_bp.route('/financial_health/summary')
@login_required
@requires_role(['personal', 'admin'])
def financial_health_summary():
    """Fetch the latest financial health score for the authenticated user."""
    try:
        db = get_mongo_db()
        health_records = get_financial_health(db, {'user_id': current_user.id})
        score = health_records[0].get('score', 0) if health_records else 0
        logger.info(f"Fetched financial health summary for user {current_user.id}: {score}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'score': score}), 200
    except Exception as e:
        logger.error(f"Error fetching financial health summary for user {current_user.id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('financial_health_summary_error', default='Error fetching financial health summary')}), 500

@summaries_bp.route('/emergency_fund/summary')
@login_required
@requires_role(['personal', 'admin'])
def emergency_fund_summary():
    """Fetch the latest emergency fund savings for the authenticated user."""
    try:
        db = get_mongo_db()
        funds = get_emergency_funds(db, {'user_id': current_user.id})
        total_savings = funds[0].get('current_savings', 0) if funds else 0
        logger.info(f"Fetched emergency fund summary for user {current_user.id}: {total_savings}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'totalSavings': total_savings}), 200
    except Exception as e:
        logger.error(f"Error fetching emergency fund summary for user {current_user.id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('emergency_fund_summary_error', default='Error fetching emergency fund summary')}), 500

@summaries_bp.route('/recent_activity')
@login_required
@requires_role(['personal', 'admin'])
def recent_activity():
    """Return recent activity across all personal finance tools for the current user."""
    try:
        activities = _get_recent_activities_data(user_id=current_user.id, is_admin_user=requires_role(['admin']))
        logger.debug(f"Fetched {len(activities)} recent activities for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify(activities), 200
    except Exception as e:
        logger.error(f"Error in summaries.recent_activity: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'error': trans('general_something_went_wrong', default='Failed to fetch recent activity')}), 500