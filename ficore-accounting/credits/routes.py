from flask import Blueprint, request, render_template, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from gridfs import GridFS
from wtforms import SelectField, SubmitField, validators
from translations import trans
import utils
from bson import ObjectId
from datetime import datetime
from logging import getLogger
from pymongo import errors

logger = getLogger(__name__)

credits_bp = Blueprint('credits', __name__, template_folder='templates/credits')

class RequestCreditsForm(FlaskForm):
    amount = SelectField(
        trans('credits_amount', default='Ficore Credit Amount'),
        choices=[('10', '10 Ficore Credits'), ('50', '50 Ficore Credits'), ('100', '100 Ficore Credits')],
        validators=[validators.DataRequired(message=trans('credits_amount_required', default='Ficore Credit amount is required'))],
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
    receipt = FileField(
        trans('credits_receipt', default='Receipt (Optional)'),
        validators=[
            FileAllowed(['jpg', 'png', 'pdf'], trans('credits_invalid_file_type', default='Only JPG, PNG, or PDF files are allowed'))
        ],
        render_kw={'class': 'form-control'}
    )
    submit = SubmitField(trans('credits_request', default='Request Ficorem Credits'), render_kw={'class': 'btn btn-primary w-100'})

class ApproveCreditRequestForm(FlaskForm):
    status = SelectField(
        trans('credits_request_status', default='Request Status'),
        choices=[('approved', 'Approve'), ('denied', 'Deny')],
        validators=[validators.DataRequired(message=trans('credits_status_required', default='Status is required'))],
        render_kw={'class': 'form-select'}
    )
    submit = SubmitField(trans('credits_update_status', default='Update Request Status'), render_kw={'class': 'btn btn-primary w-100'})

class ReceiptUploadForm(FlaskForm):
    receipt = FileField(
        trans('credits_receipt', default='Receipt'),
        validators=[
            FileAllowed(['jpg', 'png', 'pdf'], trans('credits_invalid_file_type', default='Only JPG, PNG, or PDF files are allowed')),
            validators.DataRequired(message=trans('credits_receipt_required', default='Receipt file is required'))
        ],
        render_kw={'class': 'form-control'}
    )
    submit = SubmitField(trans('credits_upload_receipt', default='Upload Receipt'), render_kw={'class': 'btn btn-primary w-100'})

def credit_ficore_credits(user_id: str, amount: int, ref: str, type: str = 'add', admin_id: str = None) -> None:
    """Credit or log Ficore Credits with MongoDB transaction."""
    db = utils.get_mongo_db()
    client = db.client
    user_query = utils.get_user_query(user_id)
    with client.start_session() as session:
        with session.start_transaction():
            try:
                if type == 'add':
                    result = db.users.update_one(
                        user_query,
                        {'$inc': {'ficore_credit_balance': amount}},
                        session=session
                    )
                    if result.matched_count == 0:
                        logger.error(f"No user found for ID {user_id} to credit Ficore Credits")
                        raise ValueError(f"No user found for ID {user_id}")
                db.ficore_credit_transactions.insert_one({
                    'user_id': user_id,
                    'amount': amount,
                    'type': type,
                    'ref': ref,
                    'payment_method': 'approved_request' if type == 'add' else None,
                    'facilitated_by_agent': admin_id or 'system',
                    'date': datetime.utcnow()
                }, session=session)
                db.audit_logs.insert_one({
                    'admin_id': admin_id or 'system',
                    'action': f'credit_ficore_credits_{type}',
                    'details': {'user_id': user_id, 'amount': amount, 'ref': ref},
                    'timestamp': datetime.utcnow()
                }, session=session)
            except ValueError as e:
                logger.error(f"Transaction aborted: {str(e)}")
                session.abort_transaction()
                raise
            except errors.PyMongoError as e:
                logger.error(f"MongoDB error during Ficore Credit transaction for user {user_id}: {str(e)}")
                session.abort_transaction()
                raise

@credits_bp.route('/request', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'personal'])
@utils.limiter.limit("50 per hour")
def request_credits():
    """Handle Ficore Credit request submissions."""
    form = RequestCreditsForm()
    if form.validate_on_submit():
        try:
            db = utils.get_mongo_db()
            client = db.client
            fs = GridFS(db)
            amount = int(form.amount.data)
            payment_method = form.payment_method.data
            receipt_file = form.receipt.data
            ref = f"REQ_{datetime.utcnow().isoformat()}"
            receipt_file_id = None

            with client.start_session() as session:
                with session.start_transaction():
                    if receipt_file:
                        receipt_file_id = fs.put(
                            receipt_file,
                            filename=receipt_file.filename,
                            user_id=str(current_user.id),
                            upload_date=datetime.utcnow(),
                            session=session
                        )
                    db.credit_requests.insert_one({
                        'user_id': str(current_user.id),
                        'amount': amount,
                        'payment_method': payment_method,
                        'receipt_file_id': receipt_file_id,
                        'status': 'pending',
                        'created_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow(),
                        'admin_id': None
                    }, session=session)
                    db.audit_logs.insert_one({
                        'admin_id': 'system',
                        'action': 'credit_request_submitted',
                        'details': {'user_id': str(current_user.id), 'amount': amount, 'ref': ref},
                        'timestamp': datetime.utcnow()
                    }, session=session)
            flash(trans('credits_request_success', default='Ficore Credit request submitted successfully'), 'success')
            logger.info(f"User {current_user.id} submitted credit request for {amount} Ficore Credits via {payment_method}")
            return redirect(url_for('credits.history'))
        except errors.PyMongoError as e:
            logger.error(f"MongoDB error submitting credit request for user {current_user.id}: {str(e)}")
            flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(f"Unexpected error submitting credit request for user {current_user.id}: {str(e)}")
            flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
    return render_template(
        'credits/request.html',
        form=form,
        title=trans('credits_request_title', default='Request Ficore Credits', lang=session.get('lang', 'en'))
    )

@credits_bp.route('/history', methods=['GET'])
@login_required
@utils.limiter.limit("100 per hour")
def history():
    """View Ficore Credit transaction and request history."""
    try:
        db = utils.get_mongo_db()
        user_query = utils.get_user_query(str(current_user.id))
        user = db.users.find_one(user_query)
        query = {} if utils.is_admin() else {'user_id': str(current_user.id)}
        transactions = list(db.ficore_credit_transactions.find(query).sort('date', -1).limit(50))
        requests = list(db.credit_requests.find(query).sort('created_at', -1).limit(50))
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
        for req in requests:
            req['_id'] = str(req['_id'])
            req['receipt_file_id'] = str(req['receipt_file_id']) if req.get('receipt_file_id') else None
        return render_template(
            'credits/history.html',
            transactions=transactions,
            requests=requests,
            ficore_credit_balance=user.get('ficore_credit_balance', 0) if user else 0,
            title=trans('credits_history_title', default='Ficore Credit Transaction History', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching history for user {current_user.id}: {str(e)}")
        flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        return render_template(
            'credits/history.html',
            transactions=[],
            requests=[],
            ficore_credit_balance=0,
            title=trans('general_error', default='Error', lang=session.get('lang', 'en'))
        )

@credits_bp.route('/requests', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def view_credit_requests():
    """View all pending credit requests (admin only)."""
    try:
        db = utils.get_mongo_db()
        requests = list(db.credit_requests.find({'status': 'pending'}).sort('created_at', -1).limit(50))
        for req in requests:
            req['_id'] = str(req['_id'])
            req['receipt_file_id'] = str(req['receipt_file_id']) if req.get('receipt_file_id') else None
        return render_template(
            'credits/requests.html',
            requests=requests,
            title=trans('credits_requests_title', default='Pending Credit Requests', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching credit requests for admin {current_user.id}: {str(e)}")
        flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        return render_template(
            'credits/requests.html',
            requests=[],
            title=trans('general_error', default='Error', lang=session.get('lang', 'en'))
        )

@credits_bp.route('/request/<request_id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("20 per hour")
def manage_credit_request(request_id):
    """Approve or deny a credit request (admin only)."""
    form = ApproveCreditRequestForm()
    try:
        db = utils.get_mongo_db()
        client = db.client
        request_data = db.credit_requests.find_one({'_id': ObjectId(request_id)})
        if not request_data:
            flash(trans('credits_request_not_found', default='Credit request not found'), 'danger')
            return redirect(url_for('credits.view_credit_requests'))

        if form.validate_on_submit():
            status = form.status.data
            ref = f"REQ_PROCESS_{datetime.utcnow().isoformat()}"
            with client.start_session() as session:
                with session.start_transaction():
                    db.credit_requests.update_one(
                        {'_id': ObjectId(request_id)},
                        {
                            '$set': {
                                'status': status,
                                'updated_at': datetime.utcnow(),
                                'admin_id': str(current_user.id)
                            }
                        },
                        session=session
                    )
                    if status == 'approved':
                        credit_ficore_credits(
                            user_id=request_data['user_id'],
                            amount=request_data['amount'],
                            ref=ref,
                            type='add',
                            admin_id=str(current_user.id)
                        )
                    db.audit_logs.insert_one({
                        'admin_id': str(current_user.id),
                        'action': f'credit_request_{status}',
                        'details': {'request_id': request_id, 'user_id': request_data['user_id'], 'amount': request_data['amount']},
                        'timestamp': datetime.utcnow()
                    }, session=session)
            flash(trans(f'credits_request_{status}', default=f'Credit request {status} successfully'), 'success')
            logger.info(f"Admin {current_user.id} {status} credit request {request_id} for user {request_data['user_id']}")
            return redirect(url_for('credits.view_credit_requests'))
        
        return render_template(
            'credits/manage_request.html',
            form=form,
            request=request_data,
            title=trans('credits_manage_request_title', default='Manage Credit Request', lang=session.get('lang', 'en'))
        )
    except errors.PyMongoError as e:
        logger.error(f"MongoDB error managing credit request {request_id} by admin {current_user.id}: {str(e)}")
        flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
    except Exception as e:
        logger.error(f"Unexpected error managing credit request {request_id} by admin {current_user.id}: {str(e)}")
        flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
    return redirect(url_for('credits.view_credit_requests'))

@credits_bp.route('/receipt_upload', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'personal'])
@utils.limiter.limit("10 per hour")
def receipt_upload():
    """Handle payment receipt uploads with transaction for Ficore Credit deduction."""
    form = ReceiptUploadForm()
    if not utils.is_admin() and not utils.check_ficore_credit_balance(1):
        flash(trans('credits_insufficient_credits', default='Insufficient Ficore Credits to upload receipt. Get more Ficore Credits.'), 'danger')
        return redirect(url_for('credits.request'))
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
                            {'$inc': {'ficore_credit_balance': -1}},
                            session=session
                        )
                        if result.matched_count == 0:
                            logger.error(f"No user found for ID {current_user.id} to deduct Ficore Credits")
                            raise ValueError(f"No user found for ID {current_user.id}")
                        db.ficore_credit_transactions.insert_one({
                            'user_id': str(current_user.id),
                            'amount': -1,
                            'type': 'spend',
                            'ref': ref,
                            'payment_method': None,
                            'facilitated_by_agent': 'system',
                            'date': datetime.utcnow()
                        }, session=session)
                    db.audit_logs.insert_one({
                        'admin_id': 'system',
                        'action': 'receipt_upload',
                        'details': {'user_id': str(current_user.id), 'file_id': str(file_id), 'ref': ref},
                        'timestamp': datetime.utcnow()
                    }, session=session)
            flash(trans('credits_receipt_uploaded', default='Receipt uploaded successfully'), 'success')
            logger.info(f"User {current_user.id} uploaded receipt {file_id}")
            return redirect(url_for('credits.history'))
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
        'credits/receipt_upload.html',
        form=form,
        title=trans('credits_receipt_upload_title', default='Upload Receipt', lang=session.get('lang', 'en'))
    )

@credits_bp.route('/receipts', methods=['GET'])
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
            'credits/receipts.html',
            receipts=receipts,
            title=trans('credits_receipts_title', default='View Receipts', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching receipts for admin {current_user.id}: {str(e)}")
        flash(trans('general_something_went_wrong', default='An error occurred'), 'danger')
        return render_template(
            'credits/receipts.html',
            receipts=[],
            title=trans('general_error', default='Error', lang=session.get('lang', 'en'))
        )

@credits_bp.route('/receipt/<file_id>', methods=['GET'])
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
        return redirect(url_for('credits.view_receipts'))

@credits_bp.route('/api/balance', methods=['GET'])
@login_required
@utils.limiter.limit("100 per hour")
def get_balance():
    """API endpoint to get current user's Ficore Credit balance."""
    try:
        db = utils.get_mongo_db()
        user_query = utils.get_user_query(str(current_user.id))
        user = db.users.find_one(user_query)
        balance = user.get('ficore_credit_balance', 0) if user else 0
        return jsonify({'balance': balance})
    except Exception as e:
        logger.error(f"Error fetching Ficore Credit balance for user {current_user.id}: {str(e)}")
        return jsonify({'error': 'Failed to fetch balance'}), 500

@credits_bp.route('/info', methods=['GET'])
@login_required
@utils.limiter.limit("100 per hour")
def ficore_credits_info():
    """Display information about Ficore Credits."""
    return render_template(
        'credits/info.html',
        title=trans('credits_info_title', default='What Are Ficore Credits?', lang=session.get('lang', 'en'))
    )
