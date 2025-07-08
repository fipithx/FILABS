from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, session
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SelectField, validators, SubmitField
from datetime import datetime
from translations import trans
import utils
from models import get_budgets, get_bills, get_emergency_funds, get_net_worth, get_quiz_results, get_learning_progress
from bson import ObjectId
import logging
import re

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, template_folder='templates/admin')

# Initialize limiter
AGENT_ID_REGEX = re.compile(r'^[A-Z0-9]{8}$')  # Agent ID: 8 alphanumeric characters

class CreditForm(FlaskForm):
    user_id = StringField(trans('admin_user_id', default='User ID'), [
        validators.DataRequired(message=trans('admin_user_id_required', default='User ID is required')),
        validators.Length(min=3, max=50, message=trans('admin_user_id_length', default='User ID must be between 3 and 50 characters'))
    ], render_kw={'class': 'form-control'})
    amount = FloatField(trans('admin_coin_amount', default='Coin Amount'), [
        validators.DataRequired(message=trans('admin_coin_amount_required', default='Coin amount is required')),
        validators.NumberRange(min=1, message=trans('admin_coin_amount_min', default='Coin amount must be at least 1'))
    ], render_kw={'class': 'form-control'})
    submit = SubmitField(trans('admin_credit_coins', default='Credit Coins'), render_kw={'class': 'btn btn-primary w-100'})

class AgentManagementForm(FlaskForm):
    agent_id = StringField(trans('agents_agent_id', default='Agent ID'), [
        validators.DataRequired(message=trans('agents_agent_id_required', default='Agent ID is required')),
        validators.Regexp(AGENT_ID_REGEX, message=trans('agents_agent_id_format', default='Agent ID must be 8 alphanumeric characters'))
    ], render_kw={'class': 'form-control'})
    status = SelectField(trans('agents_status', default='Status'), choices=[
        ('active', trans('agents_active', default='Active')),
        ('inactive', trans('agents_inactive', default='Inactive'))
    ], validators=[validators.DataRequired(message=trans('agents_status_required', default='Status is required'))], render_kw={'class': 'form-select'})
    submit = SubmitField(trans('agents_manage_submit', default='Add/Update Agent'), render_kw={'class': 'btn btn-primary w-100'})

def log_audit_action(action, details=None):
    """Log an admin action to audit_logs collection."""
    try:
        db = utils.get_mongo_db()
        db.audit_logs.insert_one({
            'admin_id': str(current_user.id),
            'action': action,
            'details': details or {},
            'timestamp': datetime.utcnow()
        })
    except Exception as e:
        logger.error(f"Error logging audit action: {str(e)}")

@admin_bp.route('/dashboard', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("100 per hour")
def dashboard():
    """Admin dashboard with system stats."""
    try:
        db = utils.get_mongo_db()
        user_count = db.users.count_documents({'role': {'$ne': 'admin'}} if not utils.is_admin() else {})
        records_count = db.records.count_documents({})
        cashflows_count = db.cashflows.count_documents({})
        inventory_count = db.inventory.count_documents({})
        coin_tx_count = db.coin_transactions.count_documents({})
        audit_log_count = db.audit_logs.count_documents({})
        budgets_count = db.budgets.count_documents({})
        bills_count = db.bills.count_documents({})
        emergency_funds_count = db.emergency_funds.count_documents({})
        net_worth_count = db.net_worth_data.count_documents({})
        quiz_results_count = db.quiz_responses.count_documents({})
        learning_progress_count = db.learning_materials.count_documents({})
        recent_users = list(db.users.find({} if utils.is_admin() else {'role': {'$ne': 'admin'}}).sort('created_at', -1).limit(10))
        for user in recent_users:
            user['_id'] = str(user['_id'])
        return render_template(
            'admin/dashboard.html',
            stats={
                'users': user_count,
                'records': records_count,
                'cashflows': cashflows_count,
                'inventory': inventory_count,
                'coin_transactions': coin_tx_count,
                'audit_logs': audit_log_count,
                'budgets': budgets_count,
                'bills': bills_count,
                'emergency_funds': emergency_funds_count,
                'net_worth': net_worth_count,
                'quiz_results': quiz_results_count,
                'learning_progress': learning_progress_count
            },
            recent_users=recent_users
        )
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('500.html', error=str(e)), 500

@admin_bp.route('/users', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_users():
    """View and manage users."""
    try:
        db = utils.get_mongo_db()
        users = list(db.users.find({} if utils.is_admin() else {'role': {'$ne': 'admin'}}).sort('created_at', -1))
        for user in users:
            user['_id'] = str(user['_id'])
        return render_template('admin/users.html', users=users)
    except Exception as e:
        logger.error(f"Error fetching users for admin: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/users.html', users=[]), 500

@admin_bp.route('/users/suspend/<user_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def suspend_user(user_id):
    """Suspend a user account."""
    try:
        db = utils.get_mongo_db()
        user_query = utils.get_user_query(user_id)
        user = db.users.find_one(user_query)
        if not user:
            flash(trans('admin_user_not_found', default='User not found'), 'danger')
            return redirect(url_for('admin.manage_users'))
        result = db.users.update_one(
            user_query,
            {'$set': {'suspended': True, 'updated_at': datetime.utcnow()}}
        )
        if result.modified_count == 0:
            flash(trans('admin_user_not_updated', default='User could not be suspended'), 'danger')
        else:
            flash(trans('admin_user_suspended', default='User suspended successfully'), 'success')
            logger.info(f"Admin {current_user.id} suspended user {user_id}")
            log_audit_action('suspend_user', {'user_id': user_id})
        return redirect(url_for('admin.manage_users'))
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/delete/<user_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("5 per hour")
def delete_user(user_id):
    """Delete a user and their data."""
    try:
        db = utils.get_mongo_db()
        user_query = utils.get_user_query(user_id)
        user = db.users.find_one(user_query)
        if not user:
            flash(trans('admin_user_not_found', default='User not found'), 'danger')
            return redirect(url_for('admin.manage_users'))
        db.records.delete_many({'user_id': user_id})
        db.cashflows.delete_many({'user_id': user_id})
        db.inventory.delete_many({'user_id': user_id})
        db.coin_transactions.delete_many({'user_id': user_id})
        db.audit_logs.delete_many({'details.user_id': user_id})
        db.budgets.delete_many({'user_id': user_id})
        db.bills.delete_many({'user_id': user_id})
        db.emergency_funds.delete_many({'user_id': user_id})
        db.net_worth_data.delete_many({'user_id': user_id})
        db.quiz_responses.delete_many({'user_id': user_id})
        db.learning_materials.delete_many({'user_id': user_id})
        result = db.users.delete_one(user_query)
        if result.deleted_count == 0:
            flash(trans('admin_user_not_deleted', default='User could not be deleted'), 'danger')
        else:
            flash(trans('admin_user_deleted', default='User deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted user {user_id}")
            log_audit_action('delete_user', {'user_id': user_id})
        return redirect(url_for('admin.manage_users'))
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.manage_users'))

@admin_bp.route('/data/delete/<collection>/<item_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def delete_item(collection, item_id):
    """Delete an item from a collection."""
    valid_collections = ['records', 'cashflows', 'inventory', 'budgets', 'bills', 'emergency_funds', 'net_worth_data', 'quiz_responses', 'learning_materials']
    if collection not in valid_collections:
        flash(trans('admin_invalid_collection', default='Invalid collection selected'), 'danger')
        return redirect(url_for('admin.dashboard'))
    try:
        db = utils.get_mongo_db()
        result = db[collection].delete_one({'_id': ObjectId(item_id)})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Item not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Item deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted {collection} item {item_id}")
            log_audit_action(f'delete_{collection}_item', {'item_id': item_id, 'collection': collection})
        return redirect(url_for(f'admin.admin_{collection}'))
    except Exception as e:
        logger.error(f"Error deleting {collection} item {item_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/coins/credit', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def credit_coins():
    """Manually credit coins to a user."""
    form = CreditForm()
    if form.validate_on_submit():
        try:
            db = utils.get_mongo_db()
            user_id = form.user_id.data.strip().lower()
            user_query = utils.get_user_query(user_id)
            user = db.users.find_one(user_query)
            if not user:
                flash(trans('admin_user_not_found', default='User not found'), 'danger')
                return render_template('admin/reset.html', form=form)
            amount = int(form.amount.data)
            db.users.update_one(
                user_query,
                {'$inc': {'coin_balance': amount}}
            )
            ref = f"ADMIN_CREDIT_{datetime.utcnow().isoformat()}"
            db.coin_transactions.insert_one({
                'user_id': user_id,
                'amount': amount,
                'type': 'admin_credit',
                'ref': ref,
                'date': datetime.utcnow()
            })
            flash(trans('admin_credit_success', default='Coins credited successfully'), 'success')
            logger.info(f"Admin {current_user.id} credited {amount} coins to user {user_id}")
            log_audit_action('credit_coins', {'user_id': user_id, 'amount': amount, 'ref': ref})
            return redirect(url_for('admin.dashboard'))
        except Exception as e:
            logger.error(f"Error crediting coins by admin {current_user.id}: {str(e)}")
            flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
            return render_template('admin/reset.html', form=form)
    return render_template('admin/reset.html', form=form)

@admin_bp.route('/audit', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def audit():
    """View audit logs of admin actions."""
    try:
        db = utils.get_mongo_db()
        logs = list(db.audit_logs.find().sort('timestamp', -1).limit(100))
        for log in logs:
            log['_id'] = str(log['_id'])
        return render_template('admin/audit.html', logs=logs)
    except Exception as e:
        logger.error(f"Error fetching audit logs for admin {current_user.id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/audit.html', logs=[])

@admin_bp.route('/manage_agents', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_agents():
    """Manage agent IDs (add or update status)."""
    form = AgentManagementForm()
    try:
        db = utils.get_mongo_db()
        agents = list(db.agents.find().sort('created_at', -1))
        for agent in agents:
            agent['_id'] = str(agent['_id'])
        
        if form.validate_on_submit():
            agent_id = form.agent_id.data.strip().upper()
            status = form.status.data
            
            existing_agent = db.agents.find_one({'_id': agent_id})
            if existing_agent:
                result = db.agents.update_one(
                    {'_id': agent_id},
                    {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
                )
                if result.modified_count == 0:
                    flash(trans('agents_not_updated', default='Agent status could not be updated'), 'danger')
                else:
                    flash(trans('agents_status_updated', default='Agent status updated successfully'), 'success')
                    logger.info(f"Admin {current_user.id} updated agent {agent_id} to status {status}")
                    log_audit_action('update_agent_status', {'agent_id': agent_id, 'status': status})
            else:
                db.agents.insert_one({
                    '_id': agent_id,
                    'status': status,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                })
                flash(trans('agents_added', default='Agent ID added successfully'), 'success')
                logger.info(f"Admin {current_user.id} added agent {agent_id} with status {status}")
                log_audit_action('add_agent', {'agent_id': agent_id, 'status': status})
            
            return redirect(url_for('admin.manage_agents'))
        
        return render_template('admin/manage_agents.html', form=form, agents=agents)
    
    except Exception as e:
        logger.error(f"Error managing agents for admin {current_user.id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/manage_agents.html', form=form, agents=[])

@admin_bp.route('/budgets', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def admin_budgets():
    """View all user budgets."""
    try:
        db = utils.get_mongo_db()
        budgets = list(get_budgets(db, {}))
        for budget in budgets:
            budget['_id'] = str(budget['_id'])
        return render_template('admin/budgets.html', budgets=budgets)
    except Exception as e:
        logger.error(f"Error fetching budgets for admin: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/budgets.html', budgets=[]), 500

@admin_bp.route('/budgets/delete/<budget_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def admin_delete_budget(budget_id):
    """Delete a budget."""
    try:
        db = utils.get_mongo_db()
        result = db.budgets.delete_one({'_id': ObjectId(budget_id)})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Budget not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Budget deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted budget {budget_id}")
            log_audit_action('delete_budget', {'budget_id': budget_id})
        return redirect(url_for('admin.admin_budgets'))
    except Exception as e:
        logger.error(f"Error deleting budget {budget_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.admin_budgets'))

@admin_bp.route('/bills', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def admin_bills():
    """View all user bills."""
    try:
        db = utils.get_mongo_db()
        bills = list(get_bills(db, {}))
        for bill in bills:
            bill['_id'] = str(bill['_id'])
        return render_template('admin/bills.html', bills=bills)
    except Exception as e:
        logger.error(f"Error fetching bills for admin: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/bills.html', bills=[]), 500

@admin_bp.route('/bills/delete/<bill_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def admin_delete_bill(bill_id):
    """Delete a bill."""
    try:
        db = utils.get_mongo_db()
        result = db.bills.delete_one({'_id': ObjectId(bill_id)})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Bill not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Bill deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted bill {bill_id}")
            log_audit_action('delete_bill', {'bill_id': bill_id})
        return redirect(url_for('admin.admin_bills'))
    except Exception as e:
        logger.error(f"Error deleting bill {bill_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.admin_bills'))

@admin_bp.route('/bills/mark_paid/<bill_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def admin_mark_bill_paid(bill_id):
    """Mark a bill as paid."""
    try:
        db = utils.get_mongo_db()
        result = db.bills.update_one(
            {'_id': ObjectId(bill_id)},
            {'$set': {'status': 'paid', 'updated_at': datetime.utcnow()}}
        )
        if result.modified_count == 0:
            flash(trans('admin_item_not_updated', default='Bill could not be updated'), 'danger')
        else:
            flash(trans('admin_bill_marked_paid', default='Bill marked as paid'), 'success')
            logger.info(f"Admin {current_user.id} marked bill {bill_id} as paid")
            log_audit_action('mark_bill_paid', {'bill_id': bill_id})
        return redirect(url_for('admin.admin_bills'))
    except Exception as e:
        logger.error(f"Error marking bill {bill_id} as paid: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.admin_bills'))

@admin_bp.route('/emergency_funds', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def admin_emergency_funds():
    """View all user emergency funds."""
    try:
        db = utils.get_mongo_db()
        funds = list(get_emergency_funds(db, {}))
        for fund in funds:
            fund['_id'] = str(fund['_id'])
        return render_template('admin/emergency_funds.html', funds=funds)
    except Exception as e:
        logger.error(f"Error fetching emergency funds for admin: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/emergency_funds.html', funds=[]), 500

@admin_bp.route('/emergency_funds/delete/<fund_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def admin_delete_emergency_fund(fund_id):
    """Delete an emergency fund."""
    try:
        db = utils.get_mongo_db()
        result = db.emergency_funds.delete_one({'_id': ObjectId(fund_id)})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Emergency fund not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Emergency fund deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted emergency fund {fund_id}")
            log_audit_action('delete_emergency_fund', {'fund_id': fund_id})
        return redirect(url_for('admin.admin_emergency_funds'))
    except Exception as e:
        logger.error(f"Error deleting emergency fund {fund_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.admin_emergency_funds'))

@admin_bp.route('/net_worth', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def admin_net_worth():
    """View all user net worth records."""
    try:
        db = utils.get_mongo_db()
        net_worths = list(get_net_worth(db, {}))
        for nw in net_worths:
            nw['_id'] = str(nw['_id'])
        return render_template('admin/net_worth.html', net_worths=net_worths)
    except Exception as e:
        logger.error(f"Error fetching net worth for admin: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/net_worth.html', net_worths=[]), 500

@admin_bp.route('/net_worth/delete/<nw_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def admin_delete_net_worth(nw_id):
    """Delete a net worth record."""
    try:
        db = utils.get_mongo_db()
        result = db.net_worth_data.delete_one({'_id': ObjectId(nw_id)})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Net worth record not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Net worth record deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted net worth record {nw_id}")
            log_audit_action('delete_net_worth', {'nw_id': nw_id})
        return redirect(url_for('admin.admin_net_worth'))
    except Exception as e:
        logger.error(f"Error deleting net worth record {nw_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.admin_net_worth'))

@admin_bp.route('/quiz_results', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def admin_quiz_results():
    """View all user quiz results."""
    try:
        db = utils.get_mongo_db()
        quiz_results = list(get_quiz_results(db, {}))
        for result in quiz_results:
            result['_id'] = str(result['_id'])
        return render_template('admin/quiz_results.html', quiz_results=quiz_results)
    except Exception as e:
        logger.error(f"Error fetching quiz results for admin: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/quiz_results.html', quiz_results=[]), 500

@admin_bp.route('/quiz_results/delete/<result_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def admin_delete_quiz_result(result_id):
    """Delete a quiz result."""
    try:
        db = utils.get_mongo_db()
        result = db.quiz_responses.delete_one({'_id': ObjectId(result_id)})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Quiz result not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Quiz result deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted quiz result {result_id}")
            log_audit_action('delete_quiz_result', {'result_id': result_id})
        return redirect(url_for('admin.admin_quiz_results'))
    except Exception as e:
        logger.error(f"Error deleting quiz result {result_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.admin_quiz_results'))

@admin_bp.route('/learning_hub', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def admin_learning_hub():
    """View all user learning hub progress."""
    try:
        db = utils.get_mongo_db()
        progress = list(get_learning_progress(db, {}))
        for p in progress:
            p['_id'] = str(p['_id'])
        return render_template('admin/learning_hub.html', progress=progress)
    except Exception as e:
        logger.error(f"Error fetching learning progress for admin: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/learning_hub.html', progress=[]), 500

@admin_bp.route('/learning_hub/delete/<progress_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def admin_delete_learning_progress(progress_id):
    """Delete a learning progress record."""
    try:
        db = utils.get_mongo_db()
        result = db.learning_materials.delete_one({'_id': ObjectId(progress_id)})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Learning progress not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Learning progress deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted learning progress {progress_id}")
            log_audit_action('delete_learning_progress', {'progress_id': progress_id})
        return redirect(url_for('admin.admin_learning_hub'))
    except Exception as e:
        logger.error(f"Error deleting learning progress {progress_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.admin_learning_hub'))
