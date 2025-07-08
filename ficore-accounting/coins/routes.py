from flask import Blueprint, request, render_template, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from gridfs import GridFS
from wtforms import FloatField, StringField, SelectField, SubmitField, validators
from translations import trans
import utils
from bson import ObjectId
from datetime import datetime
from logging import getLogger
from pymongo import errors

logger = getLogger(__name__)

coins_bp = Blueprint('coins', __name__, template_folder='templates/coins')

class PurchaseForm(FlaskForm):
    amount = SelectField(
        trans('coins_coin_amount', default='Coin Amount'),
        choices=[('10', '10 Coins'), ('50', '50 Coins'), ('100', '100 Coins')],
        validators=[validators.DataRequired(message=trans('coins_amount_required', default='Coin amount is required'))],
        render_kw={'class': 'form-select'}
    )
    payment_method = SelectField(
        trans('general_payment_method', default='Payment Method'),
        choices=[
            ('card', trans('general_card', default='Credit/Debit Card')),
            ('bank', trans('general_bank_transfer', default='Bank Transfer'))
        ],
        validators=[validators.DataRequired(message=trans('general_payment_method_required', default='Payment method is required'))],
        render_kw={'class': 'form-select'}
    )
    submit = SubmitField(trans('coins_purchase', default='Purchase'), render_kw={'class': 'btn btn-primary w-100'})

class ReceiptUploadForm(FlaskForm):
    receipt = FileField(
        trans('coins_receipt', default='Receipt'),
        validators=[
            FileAllowed(['jpg', 'png', 'pdf'], trans('coins_invalid_file_type', default='Only JPG, PNG, or PDF files are allowed')),
            validators.DataRequired(message=trans('coins_receipt_required', default='Receipt file is required'))
        ],
        render_kw={'class': 'form-control'}
    )
    submit = SubmitField(trans('coins_upload_receipt', default='Upload Receipt'), render_kw={'class': 'btn btn-primary w-100'})

def credit_coins(user_id: str, amount: int, ref: str, type: str = 'purchase') -> None:
    """Credit coins to a user and log transaction using MongoDB transaction."""
    db = utils.get_mongo_db()
    client = db.client
    user_query = utils.get_user_query(user_id)
    with client.start_session() as session:
        with session.start_transaction():
            try:
                result = db.users.update_one(
                    user_query,
                    {'$inc': {'coin_balance': amount}},
                    session=session
                )
                if result.matched_count == 0:
                    logger.error(f"No user found for ID {user_id} to credit coins")
                    raise ValueError(f"No user found for ID {user_id}")
                db.coin_transactions.insert_one({
                    'user_id': user_id,
                    'amount': amount,
                    'type': type,
                    'ref': ref,
                    'date': datetime.utcnow()
                }, session=session)
                db.audit_logs.insert_one({
                    'admin_id': 'system' if type == 'purchase' else str(current_user.id),
                    'action': f'credit_coins_{type}',
                    'details': {'user_id': user_id, 'amount': amount, 'ref': ref},
                    'timestamp': datetime.utcnow()
                }, session=session)
            except ValueError as e:
                logger.error(f"Transaction aborted: {str(e)}")
                session.abort_transaction()
                raise
            except errors.PyMongoError as e:
                logger.error(f"MongoDB error during coin credit transaction for user {user_id}: {str(e)}")
                session.abort_transaction()
                raise

@coins_bp.route('/purchase', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'personal'])
@utils.limiter.limit("50 per hour")
def purchase():
    """Handle coin purchase requests."""
    form = PurchaseForm()
    if form.validate_on_submit():
        try:
            amount = int(form.amount.data)
            payment_method = form.payment_method.data
            payment_ref = f"PAY_{datetime.utcnow().isoformat()}"
            credit_coins(str(current_user.id), amount, payment_ref, 'purchase')
            flash(trans('coins_purchase_success', default='Coins purchased successfully'), 'success')
            logger.info(f"User {current_user.id} purchased {amount} coins via {payment_method}")
            return redirect(url_for('coins.history'))
        except ValueError as e:
            logger.error(f"User not found for coin purchase: {str(e)}")
            flash(trans('general_user_not_found', default='User not found'), 'danger')
        except errors.PyMongoError as e:
            logger.error(f"MongoDB error purchasing coins for user {current_user.id}: {str(e)}")
            flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(f"Unexpected error purchasing coins for user {current_user.id}: {str(e)}")
            flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
    return render_template(
        'coins/purchase.html',
        form=form,
        title=trans('coins_purchase_title', default='Purchase Coins', lang=session.get('lang', 'en'))
    )

@coins_bp.route('/history', methods=['GET'])
@login_required
@utils.limiter.limit("100 per hour")
def history():
    """View coin transaction history."""
    try:
        db = utils.get_mongo_db()
        user_query = utils.get_user_query(str(current_user.id))
        user = db.users.find_one(user_query)
        query = {} if utils.is_admin() else {'user_id': str(current_user.id)}
        transactions = list(db.coin_transactions.find(query).sort('date', -1).limit(50))
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
        return render_template(
            'coins/history.html',
            transactions=transactions,
            coin_balance=user.get('coin_balance', 0) if user else 0,
            title=trans('coins_history_title', default='Coin Transaction History', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching coin history for user {current_user.id}: {str(e)}")
        flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        return render_template(
            'coins/history.html',
            transactions=[],
            coin_balance=0,
            title=trans('general_error', default='Error', lang=session.get('lang', 'en'))
        )

@coins_bp.route('/receipt_upload', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'personal'])
@utils.limiter.limit("10 per hour")
def receipt_upload():
    """Handle payment receipt uploads with transaction for coin deduction."""
    form = ReceiptUploadForm()
    if not utils.is_admin() and not utils.check_coin_balance(1):
        flash(trans('coins_insufficient_coins', default='Insufficient coins to upload receipt. Purchase more coins.'), 'danger')
        return redirect(url_for('coins.purchase'))
    if form.validate_on_submit():
        try:
            db = utils.get_mongo_db()
            client = db.client
            fs = GridFS(db)
            receipt_file = form.receipt.data
            ref = f"RECEIPT_UPLOAD_{datetime.utcnow().isoformat()}"
            with client.start_session() as session:
                with session.start_transaction():
                    file_id = fs.put(
                        receipt_file,
                        filename=receipt_file.filename,
                        user_id=str(current_user.id),
                        upload_date=datetime.utcnow(),
                        session=session
                    )
                    if not utils.is_admin():
                        user_query = utils.get_user_query(str(current_user.id))
                        result = db.users.update_one(
                            user_query,
                            {'$inc': {'coin_balance': -1}},
                            session=session
                        )
                        if result.matched_count == 0:
                            logger.error(f"No user found for ID {current_user.id} to deduct coins")
                            raise ValueError(f"No user found for ID {current_user.id}")
                        db.coin_transactions.insert_one({
                            'user_id': str(current_user.id),
                            'amount': -1,
                            'type': 'spend',
                            'ref': ref,
                            'date': datetime.utcnow()
                        }, session=session)
                    db.audit_logs.insert_one({
                        'admin_id': 'system',
                        'action': 'receipt_upload',
                        'details': {'user_id': str(current_user.id), 'file_id': str(file_id), 'ref': ref},
                        'timestamp': datetime.utcnow()
                    }, session=session)
            flash(trans('coins_receipt_uploaded', default='Receipt uploaded successfully'), 'success')
            logger.info(f"User {current_user.id} uploaded receipt {file_id}")
            return redirect(url_for('coins.history'))
        except ValueError as e:
            logger.error(f"User not found for receipt upload: {str(e)}")
            flash(trans('general_user_not_found', default='User not found'), 'danger')
        except errors.PyMongoError as e:
            logger.error(f"MongoDB error uploading receipt for user {current_user.id}: {str(e)}")
            flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(f"Unexpected error uploading receipt for user {current_user.id}: {str(e)}")
            flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
    return render_template(
        'coins/receipt_upload.html',
        form=form,
        title=trans('coins_receipt_upload_title', default='Upload Receipt', lang=session.get('lang', 'en'))
    )

@coins_bp.route('/receipts', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def view_receipts():
    """View all uploaded receipts (admin only)."""
    try:
        db = utils.get_mongo_db()
        fs = GridFS(db)
        receipts = list(fs.find().sort('upload_date', -1).limit(50))
        for receipt in receipts:
            receipt['_id'] = str(receipt['_id'])
            receipt['user_id'] = receipt.get('user_id', 'Unknown')
        return render_template(
            'coins/receipts.html',
            receipts=receipts,
            title=trans('coins_receipts_title', default='View Receipts', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching receipts for admin {current_user.id}: {str(e)}")
        flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        return render_template(
            'coins/receipts.html',
            receipts=[],
            title=trans('general_error', default='Error', lang=session.get('lang', 'en'))
        )

@coins_bp.route('/receipt/<file_id>', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def view_receipt(file_id):
    """Serve a specific receipt file (admin only)."""
    try:
        db = utils.get_mongo_db()
        fs = GridFS(db)
        file = fs.get(ObjectId(file_id))
        response = current_app.response_class(
            file.read(),
            mimetype=file.content_type or 'application/octet-stream',
            direct_passthrough=True
        )
        response.headers.set('Content-Disposition', 'inline', filename=file.filename)
        logger.info(f"Admin {current_user.id} viewed receipt {file_id}")
        return response
    except Exception as e:
        logger.error(f"Error serving receipt {file_id} for admin {current_user.id}: {str(e)}")
        flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        return redirect(url_for('coins.view_receipts'))

@coins_bp.route('/api/balance', methods=['GET'])
@login_required
@utils.limiter.limit("100 per hour")
def get_balance():
    """API endpoint to get current user's coin balance."""
    try:
        db = utils.get_mongo_db()
        user_query = utils.get_user_query(str(current_user.id))
        user = db.users.find_one(user_query)
        balance = user.get('coin_balance', 0) if user else 0
        return jsonify({'balance': balance})
    except Exception as e:
        logger.error(f"Error fetching coin balance for user {current_user.id}: {str(e)}")
        return jsonify({'error': 'Failed to fetch balance'}), 500
