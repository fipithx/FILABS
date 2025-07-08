from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from datetime import datetime, date, timedelta
from flask import current_app, url_for
from mailersend_email import send_email, trans, EMAIL_CONFIG
import time
import psutil
import os
from utils import get_mongo_db, send_sms_reminder, send_whatsapp_reminder, logger

def log_job_metrics(job_name):
    """Log duration and memory usage for a job."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            process = psutil.Process(os.getpid())
            start_memory = process.memory_info().rss / 1024 / 1024  # MB
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                end_memory = process.memory_info().rss / 1024 / 1024  # MB
                logger.info(
                    f"Job '{job_name}' completed: duration={duration:.2f}s, "
                    f"memory_start={start_memory:.2f}MB, memory_end={end_memory:.2f}MB"
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                end_memory = process.memory_info().rss / 1024 / 1024
                logger.error(
                    f"Job '{job_name}' failed: error={str(e)}, duration={duration:.2f}s, "
                    f"memory_start={start_memory:.2f}MB, memory_end={end_memory:.2f}MB",
                    exc_info=True
                )
                raise
        return wrapper
    return decorator

@log_job_metrics('update_overdue_status')
def update_overdue_status():
    """Update status to overdue for past-due bills."""
    with current_app.app_context():
        try:
            db = get_mongo_db()
            bills_collection = db.bills
            today = date.today()
            bills = bills_collection.find({'status': {'$in': ['pending', 'unpaid']}})
            updated_count = 0
            for bill in bills:
                bill_due_date = bill.get('due_date')
                if isinstance(bill_due_date, str):
                    try:
                        bill_due_date = datetime.strptime(bill_due_date, '%Y-%m-%d').date()
                    except ValueError:
                        logger.warning(f"Invalid due_date format for bill {bill.get('_id')}: {bill_due_date}")
                        continue
                if bill_due_date < today:
                    bills_collection.update_one(
                        {'_id': bill['_id']},
                        {'$set': {'status': 'overdue'}}
                    )
                    updated_count += 1
            logger.info(f"Updated {updated_count} overdue bill statuses")
        except Exception as e:
            logger.error(f"Error in update_overdue_status: {str(e)}", exc_info=True)
            raise

@log_job_metrics('send_bill_reminders')
def send_bill_reminders():
    """Send reminders for upcoming and overdue bills via email, SMS, and WhatsApp in batches."""
    with current_app.app_context():
        try:
            db = get_mongo_db()
            bills_collection = db.bills
            bill_reminders_collection = db.bill_reminders
            users_collection = db.users
            today = date.today()
            user_bills = {}
            max_notifications_per_run = 10  # Limit to 10 notifications (email/SMS/WhatsApp) per job execution
            notification_count = 0

            bills = bills_collection.find().limit(100)  # Process up to 100 bills per run
            for bill in bills:
                email = bill.get('user_email')
                phone = bill.get('user_phone')  # Added phone number for SMS/WhatsApp
                user = users_collection.find_one({'email': email}, {'lang': 1, 'phone': 1})
                lang = user.get('lang', 'en') if user else 'en'
                phone = user.get('phone') or phone  # Prefer user profile phone number
                if bill.get('send_notifications'):  # Check for general notification preference
                    reminder_window = today + timedelta(days=bill.get('reminder_days', 7))
                    bill_due_date = bill.get('due_date')
                    if isinstance(bill_due_date, str):
                        try:
                            bill_due_date = datetime.strptime(bill_due_date, '%Y-%m-%d').date()
                        except ValueError:
                            logger.warning(f"Invalid due_date format for bill {bill.get('_id')}: {bill_due_date}")
                            continue
                    if (bill['status'] in ['pending', 'overdue'] or 
                        (today <= bill_due_date <= reminder_window)):
                        if email not in user_bills:
                            user_bills[email] = {
                                'first_name': bill.get('first_name', 'User'),
                                'phone': phone,
                                'bills': [],
                                'lang': lang,
                                'send_email': bill.get('send_email', False),
                                'send_sms': bill.get('send_sms', False),
                                'send_whatsapp': bill.get('send_whatsapp', False)
                            }
                        user_bills[email]['bills'].append({
                            'bill_name': bill['bill_name'],
                            'amount': bill['amount'],
                            'due_date': bill_due_date.strftime('%Y-%m-%d'),
                            'category': trans(f"bill_category_{bill['category']}", lang=lang),
                            'status': trans(f"bill_status_{bill['status']}", lang=lang)
                        })

            for email, data in user_bills.items():
                if notification_count >= max_notifications_per_run:
                    logger.info(f"Reached max notifications ({max_notifications_per_run}), stopping")
                    break
                try:
                    reminder_data = {
                        'email': email,
                        'first_name': data['first_name'],
                        'phone': data['phone'],
                        'bills': data['bills'],
                        'lang': data['lang'],
                        'sent_at': datetime.utcnow(),
                        'cta_url': url_for('bill.dashboard', _external=True),
                        'unsubscribe_url': url_for('bill.unsubscribe', email=email, _external=True)
                    }

                    # Send email reminder
                    if data['send_email'] and email:
                        config = EMAIL_CONFIG.get("bill_reminder", {})
                        subject = trans(config.get("subject_key", "bill_reminder_subject"), lang=data['lang'])
                        send_email(
                            app=current_app,
                            logger=logger,
                            to_email=email,
                            subject=subject,
                            template_name=config.get("template", "bill_reminder.html"),
                            data=reminder_data,
                            lang=data['lang']
                        )
                        bill_reminders_collection.insert_one({
                            **reminder_data,
                            'notification_type': 'email'
                        })
                        logger.info(f"Sent bill reminder email to {email} and saved to bill_reminders")
                        notification_count += 1

                    # Send SMS reminder
                    if data['send_sms'] and data['phone'] and notification_count < max_notifications_per_run:
                        sms_message = trans(
                            "bill_reminder_sms",
                            lang=data['lang'],
                            bill_count=len(data['bills']),
                            due_date=data['bills'][0]['due_date']
                        )
                        success, response = send_sms_reminder(data['phone'], sms_message)
                        if success:
                            bill_reminders_collection.insert_one({
                                **reminder_data,
                                'notification_type': 'sms',
                                'response': response
                            })
                            logger.info(f"Sent bill reminder SMS to {data['phone']} and saved to bill_reminders")
                            notification_count += 1
                        else:
                            logger.error(f"Failed to send SMS to {data['phone']}: {response.get('error')}")

                    # Send WhatsApp reminder
                    if data['send_whatsapp'] and data['phone'] and notification_count < max_notifications_per_run:
                        whatsapp_message = trans(
                            "bill_reminder_whatsapp",
                            lang=data['lang'],
                            bill_count=len(data['bills']),
                            due_date=data['bills'][0]['due_date']
                        )
                        success, response = send_whatsapp_reminder(data['phone'], whatsapp_message)
                        if success:
                            bill_reminders_collection.insert_one({
                                **reminder_data,
                                'notification_type': 'whatsapp',
                                'response': response
                            })
                            logger.info(f"Sent bill reminder WhatsApp to {data['phone']} and saved to bill_reminders")
                            notification_count += 1
                        else:
                            logger.error(f"Failed to send WhatsApp to {data['phone']}: {response.get('error')}")

                except Exception as e:
                    logger.error(f"Failed to send reminders to {email}: {str(e)}", exc_info=True)
                    continue

            logger.info(f"Sent {notification_count} bill reminder notifications (email/SMS/WhatsApp)")
        except Exception as e:
            logger.error(f"Error in send_bill_reminders: {str(e)}", exc_info=True)
            raise

@log_job_metrics('cleanup_sessions')
def cleanup_sessions():
    """Remove expired sessions from the sessions collection."""
    with current_app.app_context():
        try:
            db = get_mongo_db()
            sessions_collection = db.sessions
            result = sessions_collection.delete_many({
                'expiration': {'$lt': datetime.utcnow()}
            })
            logger.info(f"Deleted {result.deleted_count} expired sessions")
        except Exception as e:
            logger.error(f"Error in cleanup_sessions: {str(e)}", exc_info=True)
            raise

def init_scheduler(app, mongo):
    """Initialize the background scheduler."""
    with app.app_context():
        try:
            jobstores = {
                'default': MemoryJobStore()
            }
            scheduler = BackgroundScheduler(jobstores=jobstores)
            scheduler.add_job(
                func=update_overdue_status,
                trigger='interval',
                days=1,
                id='overdue_status',
                name='Update overdue bill statuses daily',
                replace_existing=True,
                max_instances=1
            )
            scheduler.add_job(
                func=send_bill_reminders,
                trigger='interval',
                days=1,
                id='bill_reminders',
                name='Send bill reminders daily',
                replace_existing=True,
                max_instances=1
            )
            scheduler.add_job(
                func=cleanup_sessions,
                trigger='interval',
                days=1,
                id='cleanup_sessions',
                name='Clean up expired sessions daily',
                replace_existing=True,
                max_instances=1
            )
            scheduler.start()
            app.config['SCHEDULER'] = scheduler
            logger.info("Bill reminder, overdue status, and session cleanup scheduler started successfully")
            return scheduler
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {str(e)}", exc_info=True)
            raise RuntimeError(f"Scheduler initialization failed: {str(e)}")
