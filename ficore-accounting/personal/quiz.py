from flask import Blueprint, jsonify, current_app, redirect, url_for, flash, render_template, request, session
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import StringField, SelectField, BooleanField, SubmitField, RadioField
from wtforms.validators import DataRequired, Email, Optional, ValidationError
from flask_login import current_user
from bson import ObjectId
from datetime import datetime
from translations import trans
from mailersend_email import send_email, EMAIL_CONFIG
from models import log_tool_usage
from session_utils import create_anonymous_session
from utils import requires_role, is_admin, get_mongo_db, limiter

quiz_bp = Blueprint(
    'quiz',
    __name__,
    template_folder='templates/personal/QUIZ',
    url_prefix='/QUIZ'
)

csrf = CSRFProtect()

def custom_login_required(f):
    """Custom login decorator that allows both authenticated users and anonymous sessions."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated and not session.get('is_anonymous', False):
            create_anonymous_session()
        return f(*args, **kwargs)
    return decorated_function

class QuizForm(FlaskForm):
    first_name = StringField(
        trans('general_first_name', default='First Name'),
        validators=[DataRequired(message=trans('general_first_name_required', default='Please enter your first name.'))],
        render_kw={
            'placeholder': trans('general_first_name_placeholder', default='e.g., Muhammad, Bashir, Umar'),
            'title': trans('general_first_name_title', default='Enter your first name to personalize your quiz results'),
            'aria-describedby': 'first-name-help'
        }
    )
    email = StringField(
        trans('general_email', default='Email'),
        validators=[Optional(), Email(message=trans('general_email_invalid', default='Please enter a valid email address.'))],
        render_kw={
            'placeholder': trans('general_email_placeholder', default='e.g., muhammad@example.com'),
            'title': trans('general_email_title', default='Enter your email to receive quiz results'),
            'aria-describedby': 'email-help'
        }
    )
    lang = SelectField(
        trans('general_language', default='Language'),
        choices=[('en', trans('general_english', default='English')), ('ha', trans('general_hausa', default='Hausa'))],
        default='en',
        validators=[Optional()],
        render_kw={'aria-describedby': 'language-help'}
    )
    send_email = BooleanField(
        trans('general_send_email', default='Send Email'),
        default=False,
        validators=[Optional()],
        render_kw={
            'title': trans('general_send_email_title', default='Check to receive an email with your quiz results'),
            'aria-describedby': 'send-email-help'
        }
    )
    question_1 = RadioField(
        trans('quiz_track_expenses_label', default='Do you track your expenses regularly?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_1',
        render_kw={'aria-describedby': 'question_1_help'}
    )
    question_2 = RadioField(
        trans('quiz_save_regularly_label', default='Do you save a portion of your income regularly?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_2',
        render_kw={'aria-describedby': 'question_2_help'}
    )
    question_3 = RadioField(
        trans('quiz_budget_monthly_label', default='Do you set a monthly budget?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_3',
        render_kw={'aria-describedby': 'question_3_help'}
    )
    question_4 = RadioField(
        trans('quiz_emergency_fund_label', default='Do you have an emergency fund?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_4',
        render_kw={'aria-describedby': 'question_4_help'}
    )
    question_5 = RadioField(
        trans('quiz_invest_regularly_label', default='Do you invest your money regularly?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_5',
        render_kw={'aria-describedby': 'question_5_help'}
    )
    question_6 = RadioField(
        trans('quiz_spend_impulse_label', default='Do you often spend money on impulse?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_6',
        render_kw={'aria-describedby': 'question_6_help'}
    )
    question_7 = RadioField(
        trans('quiz_financial_goals_label', default='Do you set financial goals?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_7',
        render_kw={'aria-describedby': 'question_7_help'}
    )
    question_8 = RadioField(
        trans('quiz_review_spending_label', default='Do you review your spending habits regularly?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_8',
        render_kw={'aria-describedby': 'question_8_help'}
    )
    question_9 = RadioField(
        trans('quiz_multiple_income_label', default='Do you have multiple sources of income?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_9',
        render_kw={'aria-describedby': 'question_9_help'}
    )
    question_10 = RadioField(
        trans('quiz_retirement_plan_label', default='Do you have a retirement savings plan?'),
        validators=[DataRequired(message=trans('quiz_question_required', default='Please answer this question'))],
        choices=[('Yes', trans('quiz_yes', default='Yes')), ('No', trans('quiz_no', default='No'))],
        id='question_10',
        render_kw={'aria-describedby': 'question_10_help'}
    )
    submit = SubmitField(
        trans('quiz_submit_quiz', default='Submit Quiz'),
        render_kw={'aria-label': trans('quiz_submit_quiz', default='Submit Quiz')}
    )

    def validate_email(self, field):
        if self.send_email.data and not field.data:
            current_app.logger.warning(f"Email required for notifications for session {session.get('sid', 'no-session-id')}", extra={'session_id': session.get('sid', 'no-session-id')})
            raise ValidationError(trans('general_email_required', default='Valid email is required for notifications'))

    def __init__(self, lang='en', *args, **kwargs):
        super().__init__(*args, **kwargs)
        questions = [
            {'id': 'question_1', 'tooltip_key': 'quiz_track_expenses_tooltip'},
            {'id': 'question_2', 'tooltip_key': 'quiz_save_regularly_tooltip'},
            {'id': 'question_3', 'tooltip_key': 'quiz_budget_monthly_tooltip'},
            {'id': 'question_4', 'tooltip_key': 'quiz_emergency_fund_tooltip'},
            {'id': 'question_5', 'tooltip_key': 'quiz_invest_regularly_tooltip'},
            {'id': 'question_6', 'tooltip_key': 'quiz_spend_impulse_tooltip'},
            {'id': 'question_7', 'tooltip_key': 'quiz_financial_goals_tooltip'},
            {'id': 'question_8', 'tooltip_key': 'quiz_review_spending_tooltip'},
            {'id': 'question_9', 'tooltip_key': 'quiz_multiple_income_tooltip'},
            {'id': 'question_10', 'tooltip_key': 'quiz_retirement_plan_tooltip'},
        ]
        for q in questions:
            field = getattr(self, q['id'])
            field.description = trans(q['tooltip_key'], default='', lang=lang)

def calculate_score(answers):
    score = 0
    positive_questions = ['question_1', 'question_2', 'question_3', 'question_4', 'question_5', 'question_7', 'question_8', 'question_9', 'question_10']
    negative_questions = ['question_6']
    for i, answer in enumerate(answers, 1):
        qid = f'question_{i}'
        if qid in positive_questions and answer == 'Yes':
            score += 3
        elif qid in positive_questions and answer == 'No':
            score -= 1
        elif qid in negative_questions and answer == 'No':
            score += 3
        elif qid in negative_questions and answer == 'Yes':
            score -= 1
    return max(0, score)

def assign_personality(score, lang='en'):
    if score >= 21:
        return {
            'name': trans('quiz_planner', default='Planner', lang=lang),
            'description': trans('quiz_planner_description', default='You plan your finances meticulously.', lang=lang),
            'insights': [trans('quiz_insight_planner_1', default='You have a strong grasp of financial planning.', lang=lang)],
            'tips': [trans('quiz_tip_planner_1', default='Continue setting long-term goals.', lang=lang)]
        }
    elif score >= 13:
        return {
            'name': trans('quiz_saver', default='Saver', lang=lang),
            'description': trans('quiz_saver_description', default='You prioritize saving consistently.', lang=lang),
            'insights': [trans('quiz_insight_saver_1', default='You excel at saving regularly.', lang=lang)],
            'tips': [trans('quiz_tip_saver_1', default='Consider investing to grow your savings.', lang=lang)]
        }
    elif score >= 7:
        return {
            'name': trans('quiz_balanced', default='Balanced', lang=lang),
            'description': trans('quiz_balanced_description', default='You maintain a balanced financial approach.', lang=lang),
            'insights': [trans('quiz_insight_balanced_1', default='You balance saving and spending well.', lang=lang)],
            'tips': [trans('quiz_tip_balanced_1', default='Try a budgeting app to optimize habits.', lang=lang)]
        }
    elif score >= 3:
        return {
            'name': trans('quiz_spender', default='Spender', lang=lang),
            'description': trans('quiz_spender_description', default='You enjoy spending freely.', lang=lang),
            'insights': [trans('quiz_insight_spender_1', default='Spending is a strength, but can be controlled.', lang=lang)],
            'tips': [trans('quiz_tip_spender_1', default='Track expenses to avoid overspending.', lang=lang)]
        }
    else:
        return {
            'name': trans('quiz_avoider', default='Avoider', lang=lang),
            'description': trans('quiz_avoider_description', default='You avoid financial planning.', lang=lang),
            'insights': [trans('quiz_insight_avoider_1', default='Planning feels challenging but is learnable.', lang=lang)],
            'tips': [trans('quiz_tip_avoider_1', default='Start with a simple monthly budget.', lang=lang)]
        }

def assign_badges(score, lang='en'):
    badges = []
    if score >= 21:
        badges.append({
            'name': trans('badge_financial_guru', default='Financial Guru', lang=lang),
            'color_class': 'bg-primary',
            'description': trans('badge_financial_guru_desc', default='Awarded for excellent financial planning.', lang=lang)
        })
    elif score >= 13:
        badges.append({
            'name': trans('badge_savings_star', default='Savings Star', lang=lang),
            'color_class': 'bg-success',
            'description': trans('badge_savings_star_desc', default='Recognized for consistent saving habits.', lang=lang)
        })
    badges.append({
        'name': trans('badge_first_quiz', default='First Quiz Completed', lang=lang),
        'color_class': 'bg-info',
        'description': trans('badge_first_quiz_desc', default='Completed your first financial quiz.', lang=lang)
    })
    return badges

@quiz_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def main():
    """Main quiz interface with tabbed layout."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    lang = session.get('lang', 'en')
    course_id = request.args.get('course_id', 'financial_quiz')
    
    form_data = {'lang': lang}
    if current_user.is_authenticated:
        form_data['email'] = current_user.email
        form_data['first_name'] = current_user.get_first_name()
    
    form = QuizForm(lang=lang, data=form_data)
    
    try:
        log_tool_usage(
            tool_name='quiz',
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session['sid'],
            action='main_view',
            mongo=get_mongo_db()
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('quiz_log_error', default='Error logging quiz activity. Please try again.'), 'warning')
    
    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'submit_quiz' and form.validate_on_submit():
                try:
                    log_tool_usage(
                        tool_name='quiz',
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session['sid'],
                        action='submit_quiz',
                        mongo=get_mongo_db()
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log quiz submission: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('quiz_log_error', default='Error logging quiz submission. Continuing with submission.'), 'warning')

                if form.lang.data != lang:
                    session['lang'] = form.lang.data
                    lang = form.lang.data
                    current_app.logger.info(f"Language changed to {lang} for session {session['sid']}", extra={'session_id': session['sid']})

                answers = [getattr(form, f'question_{i}').data for i in range(1, 11)]
                score = calculate_score(answers)
                personality = assign_personality(score, lang)
                badges = assign_badges(score, lang)
                
                created_at = datetime.utcnow()
                quiz_result = {
                    '_id': ObjectId(),
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session['sid'],
                    'created_at': created_at,
                    'first_name': form.first_name.data,
                    'email': form.email.data,
                    'send_email': form.send_email.data,
                    'personality': personality['name'],
                    'description': personality['description'],
                    'score': score,
                    'badges': badges,
                    'insights': personality['insights'],
                    'tips': personality['tips'],
                    'course_id': course_id
                }
                
                try:
                    get_mongo_db().quiz_responses.insert_one(quiz_result)
                    current_app.logger.info(f"Successfully saved quiz result {quiz_result['_id']} for session {session['sid']}", extra={'session_id': session['sid']})
                    flash(trans('quiz_completed_successfully', default='Quiz completed successfully!'), 'success')
                except Exception as e:
                    current_app.logger.error(f"Failed to save quiz result to MongoDB: {str(e)}", extra={'session_id': session['sid']})
                    flash(trans('quiz_storage_error', default='Error saving quiz results.'), 'danger')
                    return redirect(url_for('quiz.main', course_id=course_id))

                if form.send_email.data and form.email.data:
                    try:
                        config = EMAIL_CONFIG["quiz"]
                        subject = trans(config["subject_key"], default='Your Financial Quiz Results', lang=lang)
                        template = config["template"]
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=form.email.data,
                            subject=subject,
                            template_name=template,
                            data={
                                'first_name': quiz_result['first_name'],
                                'score': quiz_result['score'],
                                'max_score': 30,
                                'personality': quiz_result['personality'],
                                'description': quiz_result['description'],
                                'badges': quiz_result['badges'],
                                'insights': quiz_result['insights'],
                                'tips': quiz_result['tips'],
                                'created_at': quiz_result['created_at'].strftime('%Y-%m-%d'),
                                'cta_url': url_for('quiz.main', course_id=course_id, _external=True),
                                'unsubscribe_url': url_for('quiz.unsubscribe', email=form.email.data, _external=True)
                            },
                            lang=lang
                        )
                        current_app.logger.info(f"Email sent to {form.email.data} for session {session['sid']}", extra={'session_id': session['sid']})
                    except Exception as e:
                        current_app.logger.error(f"Failed to send quiz results email: {str(e)}", extra={'session_id': session['sid']})
                        flash(trans('general_email_send_failed', default='Failed to send email.'), 'warning')

        quiz_results = list(get_mongo_db().quiz_responses.find(filter_criteria).sort('created_at', -1))
        
        if not quiz_results and current_user.is_authenticated and current_user.email:
            quiz_results = list(get_mongo_db().quiz_responses.find({'email': current_user.email}).sort('created_at', -1))

        records = []
        for result in quiz_results:
            record_data = {
                'id': str(result['_id']),
                'score': result.get('score', 0),
                'personality': result.get('personality', ''),
                'description': result.get('description', ''),
                'badges': result.get('badges', []),
                'insights': result.get('insights', []),
                'tips': result.get('tips', []),
                'created_at': result.get('created_at').strftime('%Y-%m-%d') if result.get('created_at') else 'N/A',
                'course_id': result.get('course_id', 'financial_quiz')
            }
            records.append((record_data['id'], record_data))
        
        latest_record = records[0][1] if records else {
            'score': 0,
            'personality': '',
            'description': '',
            'badges': [],
            'insights': [],
            'tips': [],
            'created_at': 'N/A',
            'course_id': course_id
        }
        
        all_results = list(get_mongo_db().quiz_responses.find({'course_id': course_id}))
        all_scores = [result['score'] for result in all_results if result.get('score') is not None]
        total_users = len(all_scores)
        rank = 0
        average_score = 0
        if all_scores:
            all_scores.sort(reverse=True)
            user_score = latest_record.get('score', 0)
            rank = sum(1 for score in all_scores if score > user_score) + 1
            average_score = sum(all_scores) / total_users if total_users > 0 else 0

        cross_tool_insights = []
        filter_kwargs_net_worth = {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        net_worth_data = get_mongo_db().net_worth_data.find(filter_kwargs_net_worth).sort('created_at', -1)
        net_worth_data = list(net_worth_data)
        if net_worth_data and latest_record and latest_record.get('score', 0) < 13:
            latest_net_worth = net_worth_data[0]
            if latest_net_worth.get('net_worth', 0) > 0:
                cross_tool_insights.append(trans(
                    'quiz_cross_tool_net_worth',
                    default='Your net worth is positive, indicating good financial health despite lower quiz scores.',
                    lang=lang
                ))

        questions = [
            {
                'id': 'question_1',
                'text_key': 'quiz_track_expenses_label',
                'text': trans('quiz_track_expenses_label', default='Do you track your expenses regularly?', lang=lang),
                'tooltip': 'quiz_track_expenses_tooltip',
                'icon': '💰'
            },
            {
                'id': 'question_2',
                'text_key': 'quiz_save_regularly_label',
                'text': trans('quiz_save_regularly_label', default='Do you save a portion of your income regularly?', lang=lang),
                'tooltip': 'quiz_save_regularly_tooltip',
                'icon': '💰'
            },
            {
                'id': 'question_3',
                'text_key': 'quiz_budget_monthly_label',
                'text': trans('quiz_budget_monthly_label', default='Do you set a monthly budget?', lang=lang),
                'tooltip': 'quiz_budget_monthly_tooltip',
                'icon': '📝'
            },
            {
                'id': 'question_4',
                'text_key': 'quiz_emergency_fund_label',
                'text': trans('quiz_emergency_fund_label', default='Do you have an emergency fund?', lang=lang),
                'tooltip': 'quiz_emergency_fund_tooltip',
                'icon': '🚨'
            },
            {
                'id': 'question_5',
                'text_key': 'quiz_invest_regularly_label',
                'text': trans('quiz_invest_regularly_label', default='Do you invest your money regularly?', lang=lang),
                'tooltip': 'quiz_invest_regularly_tooltip',
                'icon': '📈'
            },
            {
                'id': 'question_6',
                'text_key': 'quiz_spend_impulse_label',
                'text': trans('quiz_spend_impulse_label', default='Do you often spend money on impulse?', lang=lang),
                'tooltip': 'quiz_spend_impulse_tooltip',
                'icon': '🛒'
            },
            {
                'id': 'question_7',
                'text_key': 'quiz_financial_goals_label',
                'text': trans('quiz_financial_goals_label', default='Do you set financial goals?', lang=lang),
                'tooltip': 'quiz_financial_goals_tooltip',
                'icon': '🎯'
            },
            {
                'id': 'question_8',
                'text_key': 'quiz_review_spending_label',
                'text': trans('quiz_review_spending_label', default='Do you review your spending habits regularly?', lang=lang),
                'tooltip': 'quiz_review_spending_tooltip',
                'icon': '🔍'
            },
            {
                'id': 'question_9',
                'text_key': 'quiz_multiple_income_label',
                'text': trans('quiz_multiple_income_label', default='Do you have multiple sources of income?', lang=lang),
                'tooltip': 'quiz_multiple_income_tooltip',
                'icon': '💼'
            },
            {
                'id': 'question_10',
                'text_key': 'quiz_retirement_plan_label',
                'text': trans('quiz_retirement_plan_label', default='Do you have a retirement savings plan?', lang=lang),
                'tooltip': 'quiz_retirement_plan_tooltip',
                'icon': '🏖️'
            },
        ]

        return render_template('personal/QUIZ/quiz_main.html',
            form=form,
            questions=questions,
            records=records,
            latest_record=latest_record,
            insights=latest_record.get('insights', []),
            cross_tool_insights=cross_tool_insights,
            tips=latest_record.get('tips', []),
            course_id=course_id,
            lang=lang,
            max_score=30,
            rank=rank,
            total_users=total_users,
            average_score=average_score,
            t=trans,
            tool_title=trans('quiz_title', default='Financial Quiz', lang=lang)
        )

    except Exception as e:
        current_app.logger.error(f"Error in quiz.main for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('quiz_error_results', default='An error occurred while loading quiz. Please try again.'), 'danger')
        return render_template('personal/QUIZ/quiz_main.html',
            form=form,
            questions=questions,
            records=[],
            latest_record={
                'score': 0,
                'personality': '',
                'description': '',
                'badges': [],
                'insights': [],
                'tips': [],
                'created_at': 'N/A',
                'course_id': course_id
            },
            insights=[],
            cross_tool_insights=[],
            tips=[],
            course_id=course_id,
            lang=lang,
            max_score=30,
            rank=0,
            total_users=0,
            average_score=0,
            t=trans,
            tool_title=trans('quiz_title', default='Financial Quiz', lang=lang)
        ), 500

@quiz_bp.route('/unsubscribe/<email>')
@custom_login_required
@requires_role(['personal', 'admin'])
def unsubscribe(email):
    """Unsubscribe user from quiz emails using MongoDB."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    lang = session.get('lang', 'en')
    
    try:
        try:
            log_tool_usage(
                tool_name='quiz',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='unsubscribe',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log unsubscribe action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('quiz_log_error', default='Error logging unsubscribe action. Continuing with unsubscription.'), 'warning')

        filter_criteria = {'email': email} if is_admin() else {'email': email, 'user_id': current_user.id} if current_user.is_authenticated else {'email': email, 'session_id': session['sid']}
        
        existing_record = get_mongo_db().quiz_responses.find_one(filter_criteria)
        if not existing_record:
            current_app.logger.warning(f"No matching record found for email {email} to unsubscribe for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans('quiz_unsubscribe_failed', default='No matching email found or already unsubscribed'), 'danger')
            return redirect(url_for('personal.index'))

        result = get_mongo_db().quiz_responses.update_many(
            filter_criteria,
            {'$set': {'send_email': False}}
        )
        if result.modified_count > 0:
            current_app.logger.info(f"Successfully unsubscribed email {email} for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans('quiz_unsubscribed_success', default='Successfully unsubscribed from emails'), 'success')
        else:
            current_app.logger.warning(f"No records updated for email {email} during unsubscribe for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans('quiz_unsubscribe_failed', default='Failed to unsubscribe. Email not found or already unsubscribed.'), 'danger')
        return redirect(url_for('personal.index'))
    except Exception as e:
        current_app.logger.error(f"Error in quiz.unsubscribe for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('quiz_unsubscribe_error', default='Error processing unsubscribe request'), 'danger')
        return redirect(url_for('personal.index'))

@quiz_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    lang = session.get('lang', 'en')
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'unknown')})
    flash(trans('quiz_csrf_error', default='Form submission failed due to a missing security token. Please refresh and try again.'), 'danger')
    return render_template('personal/QUIZ/quiz_main.html',
        form=QuizForm(lang=lang),
        questions=[],
        records=[],
        latest_record={
            'score': 0,
            'personality': '',
            'description': '',
            'badges': [],
            'insights': [],
            'tips': [],
            'created_at': 'N/A',
            'course_id': 'financial_quiz'
        },
        insights=[],
        cross_tool_insights=[],
        tips=[],
        course_id='financial_quiz',
        lang=lang,
        max_score=30,
        rank=0,
        total_users=0,
        average_score=0,
        t=trans,
        tool_title=trans('quiz_title', default='Financial Quiz', lang=lang)
    ), 400
