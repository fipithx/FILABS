from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify, session
from flask_login import login_required, current_user
from translations import trans
import utils
from bson import ObjectId
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import StringField, DateField, FloatField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional
import logging
import io

logger = logging.getLogger(__name__)

class PaymentForm(FlaskForm):
    party_name = StringField(trans('payments_recipient_name', default='Recipient Name'), validators=[DataRequired()])
    date = DateField(trans('general_date', default='Date'), validators=[DataRequired()])
    amount = FloatField(trans('payments_amount', default='Amount'), validators=[DataRequired()])
    method = SelectField(trans('general_payment_method', default='Payment Method'), choices=[
        ('cash', trans('general_cash', default='Cash')),
        ('card', trans('general_card', default='Card')),
        ('bank', trans('general_bank_transfer', default='Bank Transfer'))
    ], validators=[Optional()])
    category = StringField(trans('general_category', default='Category'), validators=[Optional()])
    submit = SubmitField(trans('payments_add_payment', default='Add Payment'))

payments_bp = Blueprint('payments', __name__, url_prefix='/payments')

@payments_bp.route('/')
@login_required
@utils.requires_role('trader')
def index():
    """List all payment cashflows for the current user."""
    try:
        db = utils.get_mongo_db()
        # TEMPORARY: Allow admin to view all payment cashflows during testing
        # TODO: Restore original user_id filter for production
        query = {'type': 'payment'} if utils.is_admin() else {'user_id': str(current_user.id), 'type': 'payment'}
        payments = list(db.cashflows.find(query).sort('created_at', -1))
        return render_template(
            'payments/index.html',
            payments=payments,
            format_currency=utils.format_currency,
            format_date=utils.format_date,
            title=trans('payments_title', default='Payments', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching payments for user {current_user.id}: {str(e)}")
        flash(trans('payments_fetch_error', default='An error occurred'), 'danger')
        return redirect(url_for('dashboard.index'))

@payments_bp.route('/view/<id>')
@login_required
@utils.requires_role('trader')
def view(id):
    """View detailed information about a specific payment."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'type': 'payment'} if utils.is_admin() else {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query)
        if not payment:
            return jsonify({'error': trans('payments_record_not_found', default='Record not found')}), 404
        
        # Convert ObjectId to string for JSON serialization
        payment['_id'] = str(payment['_id'])
        payment['created_at'] = payment['created_at'].isoformat() if payment.get('created_at') else None
        return jsonify(payment)
    except Exception as e:
        logger.error(f"Error fetching payment {id} for user {current_user.id}: {str(e)}")
        return jsonify({'error': trans('payments_fetch_error', default='An error occurred')}), 500

@payments_bp.route('/generate_pdf/<id>')
@login_required
@utils.requires_role('trader')
def generate_pdf(id):
    """Generate PDF receipt for a payment transaction."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'type': 'payment'} if utils.is_admin() else {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query)
        
        if not payment:
            flash(trans('payments_record_not_found', default='Record not found'), 'danger')
            return redirect(url_for('payments.index'))
        
        # Check coin balance for non-admin users
        if not utils.is_admin() and not utils.check_coin_balance(1):
            flash(trans('payments_insufficient_coins', default='Insufficient coins to generate receipt'), 'danger')
            return redirect(url_for('coins.purchase'))
        
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Header
        p.setFont("Helvetica-Bold", 24)
        p.drawString(inch, height - inch, "FiCore Records - Money Out Receipt")
        
        # Content
        p.setFont("Helvetica", 12)
        y_position = height - inch - 0.5 * inch
        p.drawString(inch, y_position, f"Recipient: {payment['party_name']}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"Amount Paid: {utils.format_currency(payment['amount'])}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"Payment Method: {payment.get('method', 'N/A')}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"Category: {payment.get('category', 'No category provided')}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"Date: {utils.format_date(payment['created_at'])}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"Payment ID: {str(payment['_id'])}")
        
        # Footer
        p.setFont("Helvetica-Oblique", 10)
        p.drawString(inch, inch, "This document serves as an official payment receipt generated by FiCore Records.")
        
        p.showPage()
        p.save()
        
        # Deduct coins for non-admin users
        if not utils.is_admin():
            user_query = utils.get_user_query(str(current_user.id))
            db.users.update_one(user_query, {'$inc': {'coin_balance': -1}})
            db.coin_transactions.insert_one({
                'user_id': str(current_user.id),
                'amount': -1,
                'type': 'spend',
                'date': datetime.utcnow(),
                'ref': f"Payment PDF generated for {payment['party_name']}"
            })
        
        buffer.seek(0)
        return Response(
            buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=payment_{payment["party_name"]}_{str(payment["_id"])}.pdf'
            }
        )
    except Exception as e:
        logger.error(f"Error generating PDF for payment {id}: {str(e)}")
        flash(trans('payments_pdf_generation_error', default='An error occurred'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/add', methods=['GET', 'POST'])
@login_required
@utils.requires_role('trader')
def add():
    """Add a new payment cashflow."""
    form = PaymentForm()
    # TEMPORARY: Bypass coin check for admin during testing
    # TODO: Restore original check_coin_balance(1) for production
    if not utils.is_admin() and not utils.check_coin_balance(1):
        flash(trans('payments_insufficient_coins', default='Insufficient coins to add a payment. Purchase more coins.'), 'danger')
        return redirect(url_for('coins.purchase'))
    if form.validate_on_submit():
        try:
            db = utils.get_mongo_db()
            # Convert datetime.date to datetime.datetime
            payment_date = datetime(form.date.data.year, form.date.data.month, form.date.data.day)
            cashflow = {
                'user_id': str(current_user.id),
                'type': 'payment',
                'party_name': form.party_name.data,
                'amount': form.amount.data,
                'method': form.method.data,
                'category': form.category.data,
                'created_at': payment_date,
                'updated_at': datetime.utcnow()
            }
            db.cashflows.insert_one(cashflow)
            # TEMPORARY: Skip coin deduction for admin during testing
            # TODO: Restore original coin deduction for production
            if not utils.is_admin():
                user_query = utils.get_user_query(str(current_user.id))
                db.users.update_one(
                    user_query,
                    {'$inc': {'coin_balance': -1}}
                )
                db.coin_transactions.insert_one({
                    'user_id': str(current_user.id),
                    'amount': -1,
                    'type': 'spend',
                    'date': datetime.utcnow(),
                    'ref': f"Payment creation: {cashflow['party_name']}"
                })
            flash(trans('payments_add_success', default='Payment added successfully'), 'success')
            return redirect(url_for('payments.index'))
        except Exception as e:
            logger.error(f"Error adding payment for user {current_user.id}: {str(e)}")
            flash(trans('payments_add_error', default='An error occurred'), 'danger')
    return render_template(
        'payments/add.html',
        form=form,
        title=trans('payments_add_title', default='Add Payment', lang=session.get('lang', 'en'))
    )

@payments_bp.route('/edit/<id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('trader')
def edit(id):
    """Edit an existing payment cashflow."""
    try:
        db = utils.get_mongo_db()
        # TEMPORARY: Allow admin to edit any payment cashflow during testing
        # TODO: Restore original user_id filter for production
        query = {'_id': ObjectId(id), 'type': 'payment'} if utils.is_admin() else {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query)
        if not payment:
            flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
            return redirect(url_for('payments.index'))
        form = PaymentForm(data={
            'party_name': payment['party_name'],
            'date': payment['created_at'],  # This is already a datetime.datetime object from MongoDB
            'amount': payment['amount'],
            'method': payment.get('method'),
            'category': payment.get('category')
        })
        if form.validate_on_submit():
            try:
                # Convert datetime.date to datetime.datetime
                payment_date = datetime(form.date.data.year, form.date.data.month, form.date.data.day)
                updated_cashflow = {
                    'party_name': form.party_name.data,
                    'amount': form.amount.data,
                    'method': form.method.data,
                    'category': form.category.data,
                    'created_at': payment_date,
                    'updated_at': datetime.utcnow()
                }
                db.cashflows.update_one(
                    {'_id': ObjectId(id)},
                    {'$set': updated_cashflow}
                )
                flash(trans('payments_edit_success', default='Payment updated successfully'), 'success')
                return redirect(url_for('payments.index'))
            except Exception as e:
                logger.error(f"Error updating payment {id} for user {current_user.id}: {str(e)}")
                flash(trans('payments_edit_error', default='An error occurred'), 'danger')
        return render_template(
            'payments/edit.html',
            form=form,
            payment=payment,
            title=trans('payments_edit_title', default='Edit Payment', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching payment {id} for user {current_user.id}: {str(e)}")
        flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/delete/<id>', methods=['POST'])
@login_required
@utils.requires_role('trader')
def delete(id):
    """Delete a payment cashflow."""
    try:
        db = utils.get_mongo_db()
        # TEMPORARY: Allow admin to delete any payment cashflow during testing
        # TODO: Restore original user_id filter for production
        query = {'_id': ObjectId(id), 'type': 'payment'} if utils.is_admin() else {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        result = db.cashflows.delete_one(query)
        if result.deleted_count:
            flash(trans('payments_delete_success', default='Payment deleted successfully'), 'success')
        else:
            flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
    except Exception as e:
        logger.error(f"Error deleting payment {id} for user {current_user.id}: {str(e)}")
        flash(trans('payments_delete_error', default='An error occurred'), 'danger')
    return redirect(url_for('payments.index'))
