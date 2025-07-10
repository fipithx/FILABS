import logging
from bson import ObjectId
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, Response
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SelectField, SubmitField, TextAreaField, DateField, validators, FileField
from wtforms.validators import DataRequired, NumberRange, ValidationError
from translations import trans
import utils
import bleach
import datetime
from babel.dates import format_date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO
import csv
import re
from models import get_budgets, get_bills, get_emergency_funds, get_net_worth, get_quiz_results, get_learning_progress
from personal.learning_hub import UploadForm  # Import UploadForm from learning_hub.py
from werkzeug.utils import secure_filename
import os

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, template_folder='templates/admin')

# Regular expression for agent ID validation
AGENT_ID_REGEX = re.compile(r'^[A-Z0-9]{8}$')  # Agent ID: 8 alphanumeric characters

# Define allowed file extensions and upload folder
ALLOWED_EXTENSIONS = {'mp4', 'pdf', 'txt', 'md'}
UPLOAD_FOLDER = 'static/uploads'

# Form Definitions
class CreditForm(FlaskForm):
    user_id = StringField(trans('admin_user_id', default='User ID'), [
        DataRequired(message=trans('admin_user_id_required', default='User ID is required')),
        validators.Length(min=3, max=50, message=trans('admin_user_id_length', default='User ID must be between 3 and 50 characters'))
    ], render_kw={'class': 'form-control'})
    amount = FloatField(trans('admin_coin_amount', default='Coin Amount'), [
        DataRequired(message=trans('admin_coin_amount_required', default='Coin amount is required')),
        NumberRange(min=1, message=trans('admin_coin_amount_min', default='Coin amount must be at least 1'))
    ], render_kw={'class': 'form-control'})
    submit = SubmitField(trans('admin_credit_coins', default='Credit Coins'), render_kw={'class': 'btn btn-primary w-100'})

class AgentManagementForm(FlaskForm):
    agent_id = StringField(trans('agents_agent_id', default='Agent ID'), [
        DataRequired(message=trans('agents_agent_id_required', default='Agent ID is required')),
        validators.Regexp(AGENT_ID_REGEX, message=trans('agents_agent_id_format', default='Agent ID must be 8 alphanumeric characters'))
    ], render_kw={'class': 'form-control'})
    status = SelectField(trans('agents_status', default='Status'), choices=[
        ('active', trans('agents_active', default='Active')),
        ('inactive', trans('agents_inactive', default='Inactive'))
    ], validators=[DataRequired(message=trans('agents_status_required', default='Status is required'))], render_kw={'class': 'form-select'})
    submit = SubmitField(trans('agents_manage_submit', default='Add/Update Agent'), render_kw={'class': 'btn btn-primary w-100'})

class NewsForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()], render_kw={'class': 'form-control'})
    content = TextAreaField('Content', validators=[DataRequired()], render_kw={'class': 'form-control'})
    source_link = StringField('Source Link', render_kw={'class': 'form-control'})
    category = StringField('Category', render_kw={'class': 'form-control'})
    submit = SubmitField('Save', render_kw={'class': 'btn btn-primary'})

class TaxRateForm(FlaskForm):
    role = SelectField('Role', choices=[('personal', 'Personal'), ('trader', 'Trader'), ('agent', 'Agent'), ('company', 'Company'), ('vat', 'VAT')], validators=[DataRequired()], render_kw={'class': 'form-select'})
    min_income = FloatField('Minimum Income', validators=[DataRequired(), NumberRange(min=0)], render_kw={'class': 'form-control'})
    max_income = FloatField('Maximum Income', validators=[DataRequired(), NumberRange(min=0)], render_kw={'class': 'form-control'})
    rate = FloatField('Rate', validators=[DataRequired(), NumberRange(min=0, max=1)], render_kw={'class': 'form-control'})
    description = StringField('Description', validators=[DataRequired()], render_kw={'class': 'form-control'})
    submit = SubmitField('Add Tax Rate', render_kw={'class': 'btn btn-primary'})

    def validate_max_income(self, field):
        if field.data <= self.min_income.data:
            raise ValidationError('Maximum income must be greater than minimum income.')

class RoleForm(FlaskForm):
    role = SelectField('Role', choices=[('personal', 'Personal'), ('trader', 'Trader'), ('agent', 'Agent'), ('admin', 'Admin')], validators=[DataRequired()], render_kw={'class': 'form-select'})
    submit = SubmitField('Update Role', render_kw={'class': 'btn btn-primary'})

class PaymentLocationForm(FlaskForm):
    name = StringField('Location Name', validators=[DataRequired(), validators.Length(min=2, max=100)], render_kw={'class': 'form-control'})
    address = StringField('Address', validators=[DataRequired(), validators.Length(min=5, max=200)], render_kw={'class': 'form-control'})
    city = StringField('City', validators=[DataRequired(), validators.Length(min=2, max=100)], render_kw={'class': 'form-control'})
    country = StringField('Country', validators=[DataRequired(), validators.Length(min=2, max=100)], render_kw={'class': 'form-control'})
    submit = SubmitField('Add Payment Location', render_kw={'class': 'btn btn-primary'})

class TaxDeadlineForm(FlaskForm):
    role = SelectField('Role', choices=[('personal', 'Personal'), ('trader', 'Trader'), ('agent', 'Agent'), ('company', 'Company'), ('vat', 'VAT')], validators=[DataRequired()], render_kw={'class': 'form-select'})
    deadline_date = DateField('Deadline Date', validators=[DataRequired()], format='%Y-%m-%d', render_kw={'class': 'form-control'})
    description = StringField('Description', validators=[DataRequired(), validators.Length(min=5, max=200)], render_kw={'class': 'form-control'})
    submit = SubmitField('Add Tax Deadline', render_kw={'class': 'btn btn-primary'})

# Helper Functions
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

def sanitize_input(text):
    """Sanitize HTML input for news content to prevent XSS."""
    allowed_tags = ['p', 'b', 'i', 'strong', 'em', 'ul', 'ol', 'li', 'a']
    allowed_attributes = {'a': ['href', 'target']}
    return bleach.clean(text, tags=allowed_tags, attributes=allowed_attributes)

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@admin_bp.route('/dashboard', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("100 per hour")
def dashboard():
    """Admin dashboard with system stats and tool usage."""
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
        payment_locations_count = db.payment_locations.count_documents({})
        tax_deadlines_count = db.tax_deadlines.count_documents({})
        
        # Tool usage statistics
        tool_usage = db.tool_usage.aggregate([
            {'$group': {
                '_id': '$tool_name',
                'count': {'$sum': 1}
            }}
        ])
        tool_usage_stats = {item['_id']: item['count'] for item in tool_usage}
        
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
                'learning_progress': learning_progress_count,
                'payment_locations': payment_locations_count,
                'tax_deadlines': tax_deadlines_count
            },
            tool_usage=tool_usage_stats,
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
    valid_collections = ['records', 'cashflows', 'inventory', 'budgets', 'bills', 'emergency_funds', 'net_worth_data', 'quiz_responses', 'learning_materials', 'payment_locations', 'tax_deadlines']
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
        return redirect(url_for(f'admin.admin_{collection}' if collection in ['budgets', 'bills', 'emergency_funds', 'net_worth_data', 'quiz_responses', 'learning_materials'] else 'admin.' + collection.replace('_', '')))
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

@admin_bp.route('/manage_courses', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_courses():
    """Manage courses: list all courses and upload new ones."""
    form = UploadForm()
    lang = session.get('lang', 'en')
    try:
        db = utils.get_mongo_db()
        courses = list(db.learning_materials.find({'type': 'course'}).sort('created_at', -1))
        for course in courses:
            course['_id'] = str(course['_id'])
            course['created_at_formatted'] = format_date(course['created_at'], format='medium', locale=lang)
        
        if request.method == 'POST' and form.validate_on_submit():
            if not allowed_file(form.file.data.filename):
                flash(trans('learning_hub_invalid_file_type', default='Invalid file type. Allowed: mp4, pdf, txt, md'), 'danger')
                return render_template('admin/learning_hub.html', form=form, courses=courses, progress=[])
            
            filename = secure_filename(form.file.data.filename)
            file_path = os.path.join(current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), filename)
            form.file.data.save(file_path)
            
            course_id = form.course_id.data
            roles = [form.roles.data] if form.roles.data != 'all' else ['civil_servant', 'nysc', 'agent']
            course_data = {
                'type': 'course',
                'id': course_id,
                '_id': ObjectId(),
                'title_key': f"learning_hub_course_{course_id}_title",
                'title_en': form.title.data,
                'title_ha': form.title.data,  # Placeholder; should support translation
                'description_en': form.description.data,
                'description_ha': form.description.data,  # Placeholder
                'is_premium': form.is_premium.data,
                'roles': roles,
                'modules': [{
                    'id': f"{course_id}-module-1",
                    'title_key': f"learning_hub_module_{course_id}_title",
                    'title_en': "Module 1",
                    'lessons': [{
                        'id': f"{course_id}-module-1-lesson-1",
                        'title_key': f"learning_hub_lesson_{course_id}_title",
                        'title_en': "Lesson 1",
                        'content_type': form.content_type.data,
                        'content_path': f"uploads/{filename}",
                        'content_en': "Uploaded content",
                        'quiz_id': None
                    }]
                }],
                'created_at': datetime.utcnow()
            }
            
            db.learning_materials.update_one(
                {'type': 'course', 'id': course_id},
                {'$set': course_data},
                upsert=True
            )
            
            flash(trans('learning_hub_upload_success', default='Content uploaded successfully'), 'success')
            logger.info(f"Admin {current_user.id} uploaded course {course_id}")
            log_audit_action('upload_course', {'course_id': course_id, 'filename': filename})
            return redirect(url_for('admin.manage_courses'))
        
        return render_template('admin/learning_hub.html', form=form, courses=courses, progress=[])
    
    except Exception as e:
        logger.error(f"Error managing courses for admin {current_user.id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/learning_hub.html', form=form, courses=[], progress=[]), 500

@admin_bp.route('/manage_courses/delete/<course_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def delete_course(course_id):
    """Delete a course."""
    try:
        db = utils.get_mongo_db()
        result = db.learning_materials.delete_one({'type': 'course', 'id': course_id})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Course not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Course deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted course {course_id}")
            log_audit_action('delete_course', {'course_id': course_id})
        return redirect(url_for('admin.manage_courses'))
    except Exception as e:
        logger.error(f"Error deleting course {course_id}: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.manage_courses'))

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
        form = UploadForm()  # For compatibility with template
        return render_template('admin/learning_hub.html', form=form, progress=progress, courses=[])
    except Exception as e:
        logger.error(f"Error fetching learning progress for admin: {str(e)}")
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('admin/learning_hub.html', form=UploadForm(), progress=[], courses=[]), 500

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

@admin_bp.route('/news', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def news_management():
    """Manage news articles: list all articles and add new ones."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    form = NewsForm()
    if request.method == 'POST' and form.validate_on_submit():
        title = form.title.data
        content = form.content.data
        source_link = form.source_link.data
        category = form.category.data
        sanitized_content = sanitize_input(content)
        article = {
            'title': title,
            'content': sanitized_content,
            'source_link': source_link if source_link else None,
            'category': category if category else None,
            'is_active': True,
            'published_at': datetime.datetime.utcnow(),
            'created_by': current_user.id
        }
        result = db.news.insert_one(article)
        article_id = str(result.inserted_id)
        logger.info(f"News article created: id={article_id}, title={title}, user={current_user.id}")
        log_audit_action('add_news_article', {'article_id': article_id, 'title': title})
        flash(trans('news_article_added', default='News article added successfully', lang=lang), 'success')
        return redirect(url_for('admin.news_management'))
    
    articles = list(db.news.find().sort('published_at', -1))
    for article in articles:
        article['_id'] = str(article['_id'])
        article['published_at_formatted'] = format_date(article['published_at'], format='medium', locale=lang)
    return render_template('admin/news_management.html', form=form, articles=articles, title='News Management')

@admin_bp.route('/news/edit/<article_id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def edit_news(article_id):
    """Edit an existing news article."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    article = db.news.find_one({'_id': ObjectId(article_id)})
    if not article:
        flash(trans('news_article_not_found', default='Article not found', lang=lang), 'danger')
        return redirect(url_for('admin.news_management'))
    
    form = NewsForm(obj=article)
    if request.method == 'POST' and form.validate_on_submit():
        sanitized_content = sanitize_input(form.content.data)
        db.news.update_one(
            {'_id': ObjectId(article_id)},
            {'$set': {
                'title': form.title.data,
                'content': sanitized_content,
                'source_link': form.source_link.data if form.source_link.data else None,
                'category': form.category.data if form.category.data else None,
                'updated_at': datetime.datetime.utcnow()
            }}
        )
        logger.info(f"News article updated: id={article_id}, user={current_user.id}")
        log_audit_action('edit_news_article', {'article_id': article_id})
        flash(trans('news_article_updated', default='News article updated successfully', lang=lang), 'success')
        return redirect(url_for('admin.news_management'))
    
    return render_template('admin/news_edit.html', form=form, article=article, title='Edit News Article')

@admin_bp.route('/news/delete/<article_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def delete_news(article_id):
    """Delete a news article."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    result = db.news.delete_one({'_id': ObjectId(article_id)})
    if result.deleted_count > 0:
        logger.info(f"News article deleted: id={article_id}, user={current_user.id}")
        log_audit_action('delete_news_article', {'article_id': article_id})
        flash(trans('news_article_deleted', default='News article deleted successfully', lang=lang), 'success')
    else:
        flash(trans('news_article_not_found', default='Article not found', lang=lang), 'danger')
    return redirect(url_for('admin.news_management'))

@admin_bp.route('/tax_rates', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_tax_rates():
    """Manage tax rates: list all tax rates and add new ones."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    form = TaxRateForm()
    if request.method == 'POST' and form.validate_on_submit():
        try:
            tax_rate = {
                'role': form.role.data,
                'min_income': form.min_income.data,
                'max_income': form.max_income.data,
                'rate': form.rate.data,
                'description': form.description.data,
                'created_by': current_user.id,
                'created_at': datetime.datetime.utcnow()
            }
            result = db.tax_rates.insert_one(tax_rate)
            rate_id = str(result.inserted_id)
            logger.info(f"Tax rate added: id={rate_id}, role={form.role.data}, user={current_user.id}")
            log_audit_action('add_tax_rate', {'rate_id': rate_id, 'role': form.role.data})
            flash(trans('tax_rate_added', default='Tax rate added successfully', lang=lang), 'success')
            return redirect(url_for('admin.manage_tax_rates'))
        except Exception as e:
            logger.error(f"Error adding tax rate: {str(e)}")
            flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
            return render_template('admin/tax_rates.html', form=form, rates=[])
    
    rates = list(db.tax_rates.find().sort('created_at', -1))
    for rate in rates:
        rate['_id'] = str(rate['_id'])
    return render_template('admin/tax_rates.html', form=form, rates=rates, title='Manage Tax Rates')

@admin_bp.route('/tax_rates/edit/<rate_id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def edit_tax_rate(rate_id):
    """Edit an existing tax rate."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    rate = db.tax_rates.find_one({'_id': ObjectId(rate_id)})
    if not rate:
        flash(trans('tax_rate_not_found', default='Tax rate not found', lang=lang), 'danger')
        return redirect(url_for('admin.manage_tax_rates'))
    
    form = TaxRateForm(obj=rate)
    if request.method == 'POST' and form.validate_on_submit():
        try:
            db.tax_rates.update_one(
                {'_id': ObjectId(rate_id)},
                {'$set': {
                    'role': form.role.data,
                    'min_income': form.min_income.data,
                    'max_income': form.max_income.data,
                    'rate': form.rate.data,
                    'description': form.description.data,
                    'updated_at': datetime.datetime.utcnow()
                }}
            )
            logger.info(f"Tax rate updated: id={rate_id}, user={current_user.id}")
            log_audit_action('edit_tax_rate', {'rate_id': rate_id})
            flash(trans('tax_rate_updated', default='Tax rate updated successfully', lang=lang), 'success')
            return redirect(url_for('admin.manage_tax_rates'))
        except Exception as e:
            logger.error(f"Error updating tax rate {rate_id}: {str(e)}")
            flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
            return render_template('admin/tax_rate_edit.html', form=form, rate=rate, title='Edit Tax Rate')
    
    return render_template('admin/tax_rate_edit.html', form=form, rate=rate, title='Edit Tax Rate')

@admin_bp.route('/tax_rates/delete/<rate_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def delete_tax_rate(rate_id):
    """Delete a tax rate."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    result = db.tax_rates.delete_one({'_id': ObjectId(rate_id)})
    if result.deleted_count > 0:
        logger.info(f"Tax rate deleted: id={rate_id}, user={current_user.id}")
        log_audit_action('delete_tax_rate', {'rate_id': rate_id})
        flash(trans('tax_rate_deleted', default='Tax rate deleted successfully', lang=lang), 'success')
    else:
        flash(trans('tax_rate_not_found', default='Tax rate not found', lang=lang), 'danger')
    return redirect(url_for('admin.manage_tax_rates'))

@admin_bp.route('/payment_locations', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_payment_locations():
    """Manage payment locations: list all locations and add new ones."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    form = PaymentLocationForm()
    if request.method == 'POST' and form.validate_on_submit():
        try:
            location = {
                'name': form.name.data,
                'address': form.address.data,
                'city': form.city.data,
                'country': form.country.data,
                'created_by': current_user.id,
                'created_at': datetime.utcnow()
            }
            result = db.payment_locations.insert_one(location)
            location_id = str(result.inserted_id)
            logger.info(f"Payment location added: id={location_id}, name={form.name.data}, user={current_user.id}")
            log_audit_action('add_payment_location', {'location_id': location_id, 'name': form.name.data})
            flash(trans('payment_location_added', default='Payment location added successfully', lang=lang), 'success')
            return redirect(url_for('admin.manage_payment_locations'))
        except Exception as e:
            logger.error(f"Error adding payment location: {str(e)}")
            flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
            return render_template('admin/payment_locations.html', form=form, locations=[])
    
    locations = list(db.payment_locations.find().sort('created_at', -1))
    for location in locations:
        location['_id'] = str(location['_id'])
    return render_template('admin/payment_locations.html', form=form, locations=locations, title='Manage Payment Locations')

@admin_bp.route('/payment_locations/edit/<location_id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def edit_payment_location(location_id):
    """Edit an existing payment location."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    location = db.payment_locations.find_one({'_id': ObjectId(location_id)})
    if not location:
        flash(trans('payment_location_not_found', default='Payment location not found', lang=lang), 'danger')
        return redirect(url_for('admin.manage_payment_locations'))
    
    form = PaymentLocationForm(obj=location)
    if request.method == 'POST' and form.validate_on_submit():
        try:
            db.payment_locations.update_one(
                {'_id': ObjectId(location_id)},
                {'$set': {
                    'name': form.name.data,
                    'address': form.address.data,
                    'city': form.city.data,
                    'country': form.country.data,
                    'updated_at': datetime.datetime.utcnow()
                }}
            )
            logger.info(f"Payment location updated: id={location_id}, user={current_user.id}")
            log_audit_action('edit_payment_location', {'location_id': location_id})
            flash(trans('payment_location_updated', default='Payment location updated successfully', lang=lang), 'success')
            return redirect(url_for('admin.manage_payment_locations'))
        except Exception as e:
            logger.error(f"Error updating payment location {location_id}: {str(e)}")
            flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
            return render_template('admin/payment_location_edit.html', form=form, location=location, title='Edit Payment Location')
    
    return render_template('admin/payment_location_edit.html', form=form, location=location, title='Edit Payment Location')

@admin_bp.route('/payment_locations/delete/<location_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def delete_payment_location(location_id):
    """Delete a payment location."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    result = db.payment_locations.delete_one({'_id': ObjectId(location_id)})
    if result.deleted_count > 0:
        logger.info(f"Payment location deleted: id={location_id}, user={current_user.id}")
        log_audit_action('delete_payment_location', {'location_id': location_id})
        flash(trans('payment_location_deleted', default='Payment location deleted successfully', lang=lang), 'success')
    else:
        flash(trans('payment_location_not_found', default='Payment location not found', lang=lang), 'danger')
    return redirect(url_for('admin.manage_payment_locations'))

@admin_bp.route('/tax_deadlines', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_tax_deadlines():
    """Manage tax deadlines: list all deadlines and add new ones."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    form = TaxDeadlineForm()
    if request.method == 'POST' and form.validate_on_submit():
        try:
            deadline = {
                'role': form.role.data,
                'deadline_date': form.deadline_date.data,
                'description': form.description.data,
                'created_by': current_user.id,
                'created_at': datetime.utcnow()
            }
            result = db.tax_deadlines.insert_one(deadline)
            deadline_id = str(result.inserted_id)
            logger.info(f"Tax deadline added: id={deadline_id}, role={form.role.data}, user={current_user.id}")
            log_audit_action('add_tax_deadline', {'deadline_id': deadline_id, 'role': form.role.data})
            flash(trans('tax_deadline_added', default='Tax deadline added successfully', lang=lang), 'success')
            return redirect(url_for('admin.manage_tax_deadlines'))
        except Exception as e:
            logger.error(f"Error adding tax deadline: {str(e)}")
            flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
            return render_template('admin/tax_deadlines.html', form=form, deadlines=[])
    
    deadlines = list(db.tax_deadlines.find().sort('deadline_date', -1))
    for deadline in deadlines:
        deadline['_id'] = str(deadline['_id'])
        deadline['deadline_date_formatted'] = format_date(deadline['deadline_date'], format='medium', locale=lang)
    return render_template('admin/tax_deadlines.html', form=form, deadlines=deadlines, title='Manage Tax Deadlines')

@admin_bp.route('/tax_deadlines/edit/<deadline_id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def edit_tax_deadline(deadline_id):
    """Edit an existing tax deadline."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    deadline = db.tax_deadlines.find_one({'_id': ObjectId(deadline_id)})
    if not deadline:
        flash(trans('tax_deadline_not_found', default='Tax deadline not found', lang=lang), 'danger')
        return redirect(url_for('admin.manage_tax_deadlines'))
    
    form = TaxDeadlineForm(obj=deadline)
    if request.method == 'POST' and form.validate_on_submit():
        try:
            db.tax_deadlines.update_one(
                {'_id': ObjectId(deadline_id)},
                {'$set': {
                    'role': form.role.data,
                    'deadline_date': form.deadline_date.data,
                    'description': form.description.data,
                    'updated_at': datetime.datetime.utcnow()
                }}
            )
            logger.info(f"Tax deadline updated: id={deadline_id}, user={current_user.id}")
            log_audit_action('edit_tax_deadline', {'deadline_id': deadline_id})
            flash(trans('tax_deadline_updated', default='Tax deadline updated successfully', lang=lang), 'success')
            return redirect(url_for('admin.manage_tax_deadlines'))
        except Exception as e:
            logger.error(f"Error updating tax deadline {deadline_id}: {str(e)}")
            flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
            return render_template('admin/tax_deadline_edit.html', form=form, deadline=deadline, title='Edit Tax Deadline')
    
    return render_template('admin/tax_deadline_edit.html', form=form, deadline=deadline, title='Edit Tax Deadline')

@admin_bp.route('/tax_deadlines/delete/<deadline_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def delete_tax_deadline(deadline_id):
    """Delete a tax deadline."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    result = db.tax_deadlines.delete_one({'_id': ObjectId(deadline_id)})
    if result.deleted_count > 0:
        logger.info(f"Tax deadline deleted: id={deadline_id}, user={current_user.id}")
        log_audit_action('delete_tax_deadline', {'deadline_id': deadline_id})
        flash(trans('tax_deadline_deleted', default='Tax deadline deleted successfully', lang=lang), 'success')
    else:
        flash(trans('tax_deadline_not_found', default='Tax deadline not found', lang=lang), 'danger')
    return redirect(url_for('admin.manage_tax_deadlines'))

@admin_bp.route('/reports/customers', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def customer_reports():
    """Generate customer reports in HTML, PDF, or CSV format."""
    db = utils.get_mongo_db()
    format = request.args.get('format', 'html')
    users = list(db.users.find())
    for user in users:
        user['_id'] = str(user['_id'])
    
    if format == 'pdf':
        return generate_customer_report_pdf(users)
    elif format == 'csv':
        return generate_customer_report_csv(users)
    
    return render_template('admin/customer_reports.html', users=users, title='Customer Reports')

def generate_customer_report_pdf(users):
    """Generate a PDF report of customer data."""
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica", 12)
    p.drawString(1 * inch, 10.5 * inch, "Customer Report")
    p.drawString(1 * inch, 10.2 * inch, f"Generated on: {datetime.datetime.utcnow().strftime('%Y-%m-%d')}")
    y = 9.5 * inch
    p.drawString(1 * inch, y, "Username")
    p.drawString(2.5 * inch, y, "Email")
    p.drawString(4 * inch, y, "Role")
    p.drawString(5.5 * inch, y, "Created At")
    y -= 0.3 * inch
    for user in users:
        p.drawString(1 * inch, y, user['_id'])
        p.drawString(2.5 * inch, y, user['email'])
        p.drawString(4 * inch, y, user['role'])
        p.drawString(5.5 * inch, y, user['created_at'].strftime('%Y-%m-%d'))
        y -= 0.3 * inch
        if y < 1 * inch:
            p.showPage()
            y = 10.5 * inch
    p.showPage()
    p.save()
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=customer_report.pdf'})

def generate_customer_report_csv(users):
    """Generate a CSV report of customer data."""
    output = [['Username', 'Email', 'Role', 'Created At']]
    for user in users:
        output.append([user['_id'], user['email'], user['role'], user['created_at'].strftime('%Y-%m-%d')])
    buffer = BytesIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerows(output)
    buffer.seek(0)
    return Response(buffer, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=customer_report.csv'})

@admin_bp.route('/users/roles', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_user_roles():
    """Manage user roles: list all users and update their roles."""
    db = utils.get_mongo_db()
    lang = session.get('lang', 'en')
    users = list(db.users.find())
    form = RoleForm()
    if request.method == 'POST' and form.validate_on_submit():
        user_id = request.form.get('user_id')
        if not user_id:
            flash(trans('user_id_required', default='User ID is required', lang=lang), 'danger')
            return redirect(url_for('admin.manage_user_roles'))
        try:
            user = db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                flash(trans('user_not_found', default='User not found', lang=lang), 'danger')
                return redirect(url_for('admin.manage_user_roles'))
            new_role = form.role.data
            db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'role': new_role, 'updated_at': datetime.datetime.utcnow()}}
            )
            logger.info(f"User role updated: id={user_id}, new_role={new_role}, user={current_user.id}")
            log_audit_action('update_user_role', {'user_id': user_id, 'new_role': new_role})
            flash(trans('user_role_updated', default='User role updated successfully', lang=lang), 'success')
            return redirect(url_for('admin.manage_user_roles'))
        except Exception as e:
            logger.error(f"Error updating user role {user_id}: {str(e)}")
            flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
            return render_template('admin/user_roles.html', form=form, users=users, title='Manage User Roles')
    
    for user in users:
        user['_id'] = str(user['_id'])
    return render_template('admin/user_roles.html', form=form, users=users, title='Manage User Roles')
