from flask import (
    Blueprint, render_template, session, request, redirect, url_for, flash,
    jsonify, current_app, send_from_directory
)
from flask_wtf.csrf import CSRFError
from flask_login import current_user
from .forms import LearningHubProfileForm, UploadForm
from .models import (
    get_progress, save_course_progress, course_lookup, lesson_lookup,
    calculate_progress_summary, init_storage, get_mongo_db
)
from utils import requires_role, is_admin, trans, format_currency, clean_currency, get_all_recent_activities, log_tool_usage
from session_utils import create_anonymous_session
from mailersend_email import send_email, EMAIL_CONFIG
from werkzeug.utils import secure_filename
import logging
from . import learning_hub_bp

# Configure logging
logger = logging.getLogger('ficore_app.learning_hub')
logger.setLevel(logging.INFO)

# Allowed file extensions for uploads
ALLOWED_EXTENSIONS = {'mp4', 'pdf', 'txt', 'md'}
UPLOAD_FOLDER = 'learning_hub/static/uploads'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@learning_hub_bp.route('/')
def main():
    """Render the main Learning Hub landing page."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    try:
        return render_template(
            'learning_hub/index.html',
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang)
        )
    except Exception as e:
        logger.error(f"Error rendering main page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_error_loading', default='Error loading Learning Hub'), 'danger')
        return render_template('personal/GENERAL/error.html', error=str(e), title=trans('error', lang=lang)), 500

@learning_hub_bp.route('/personal')
def personal():
    """Render the Personal Finance Learning page."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    try:
        return render_template(
            'learning_hub/personal/index.html',
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_personal_title', default='Personal Finance Learning', lang=lang)
        )
    except Exception as e:
        logger.error(f"Error rendering personal page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_error_loading', default='Error loading Personal Finance Learning'), 'danger')
        return render_template('personal/GENERAL/error.html', error=str(e), title=trans('error', lang=lang)), 500

@learning_hub_bp.route('/business')
def business():
    """Render the Business Learning page."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    try:
        return render_template(
            'learning_hub/business/index.html',
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_business_title', default='Business Learning', lang=lang)
        )
    except Exception as e:
        logger.error(f"Error rendering business page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_error_loading', default='Error loading Business Learning'), 'danger')
        return render_template('personal/GENERAL/error.html', error=str(e), title=trans('error', lang=lang)), 500

@learning_hub_bp.route('/agents')
def agents():
    """Render the Agents Learning page."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    try:
        return render_template(
            'learning_hub/agents/index.html',
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_agents_title', default='Agent Learning', lang=lang)
        )
    except Exception as e:
        logger.error(f"Error rendering agents page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_error_loading', default='Error loading Agent Learning'), 'danger')
        return render_template('personal/GENERAL/error.html', error=str(e), title=trans('error', lang=lang)), 500

@learning_hub_bp.route('/compliance')
def compliance():
    """Render the Compliance Learning page."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    try:
        return render_template(
            'learning_hub/compliance/index.html',
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_compliance_title', default='Compliance Learning', lang=lang)
        )
    except Exception as e:
        logger.error(f"Error rendering compliance page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_error_loading', default='Error loading Compliance Learning'), 'danger')
        return render_template('personal/GENERAL/error.html', error=str(e), title=trans('error', lang=lang)), 500

@learning_hub_bp.route('/tool-tutorials')
def tool_tutorials():
    """Render the Tool Tutorials page."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    try:
        return render_template(
            'learning_hub/tool_tutorials/index.html',
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_tool_tutorials_title', default='Tool Tutorials', lang=lang)
        )
    except Exception as e:
        logger.error(f"Error rendering tool tutorials page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_error_loading', default='Error loading Tool Tutorials'), 'danger')
        return render_template('personal/GENERAL/error.html', error=str(e), title=trans('error', lang=lang)), 500

@learning_hub_bp.route('/main', methods=['GET', 'POST'])
@requires_role(['personal', 'admin'])
def learning_hub_main():
    """Main learning hub interface with all functionality."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    db = get_mongo_db()
    
    try:
        # Fetch recent activities
        activities = get_all_recent_activities(db=db, user_id=current_user.id if current_user.is_authenticated else None, limit=10)
        logger.debug(f"Fetched {len(activities)} recent activities for user {current_user.id if current_user.is_authenticated else 'anonymous'}", extra={'session_id': session.get('sid', 'unknown')})
        
        # Log tool usage
        log_tool_usage(
            db=db,
            tool_name='learning_hub',
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session['sid'],
            action='main_view'
        )
        
        # Get courses filtered by role
        role_filter = session.get('role_filter', 'all')
        courses = {k: v for k, v in course_lookup('all').items() if role_filter == 'all' or role_filter in v.get('roles', [])}
        
        # Get progress and calculate summary
        progress = get_progress()
        progress_summary, total_completed, total_quiz_scores, certificates_earned, total_coins_earned, badges_earned = calculate_progress_summary()
        
        # Get profile data
        profile_data = session.get('learning_hub_profile', {})
        if current_user.is_authenticated:
            profile_data['email'] = profile_data.get('email', current_user.email)
            profile_data['first_name'] = profile_data.get('first_name', current_user.display_name)
        
        # Create forms
        profile_form = LearningHubProfileForm(data=profile_data)
        upload_form = UploadForm()
        
        if request.method == 'POST' and request.form.get('action') == 'upload' and is_admin():
            if upload_form.validate_on_submit():
                if not allowed_file(upload_form.file.data.filename):
                    flash(trans('learning_hub_invalid_file_type', default='Invalid file type. Allowed: mp4, pdf, txt, md'), 'danger')
                else:
                    filename = secure_filename(upload_form.file.data.filename)
                    file_path = os.path.join(current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), filename)
                    upload_form.file.data.save(file_path)
                    
                    # Update MongoDB
                    course_id = upload_form.course_id.data
                    roles = [upload_form.roles.data] if upload_form.roles.data != 'all' else ['civil_servant', 'nysc', 'agent']
                    course_data = {
                        'type': 'course',
                        'id': course_id,
                        '_id': ObjectId(),
                        'title_key': f"learning_hub_course_{course_id}_title",
                        'title_en': upload_form.title.data,
                        'title_ha': upload_form.title.data,  # Placeholder; should support translation
                        'description_en': upload_form.description.data,
                        'description_ha': upload_form.description.data,  # Placeholder
                        'is_premium': upload_form.is_premium.data,
                        'roles': roles,
                        'modules': [{
                            'id': f"{course_id}-module-1",
                            'title_key': f"learning_hub_module_{course_id}_title",
                            'title_en': "Module 1",
                            'lessons': [{
                                'id': f"{course_id}-module-1-lesson-1",
                                'title_key': f"learning_hub_lesson_{course_id}_title",
                                'title_en': "Lesson 1",
                                'content_type': upload_form.content_type.data,
                                'content_path': f"uploads/{filename}",
                                'content_en': "Uploaded content",
                                'quiz_id': None
                            }]
                        }],
                        'created_at': datetime.utcnow()
                    }
                    
                    # Save to MongoDB
                    get_mongo_db().learning_materials.update_one(
                        {'type': 'course', 'id': course_id},
                        {'$set': course_data},
                        upsert=True
                    )
                    
                    flash(trans('learning_hub_upload_success', default='Content uploaded successfully'), 'success')
                    logger.info(f"Uploaded course {course_id}", extra={'session_id': session['sid']})
            else:
                flash(trans('learning_hub_upload_failed', default='Failed to upload content'), 'danger')
        
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        
        return render_template(
            'learning_hub/learning_hub_main.html',
            courses=courses,
            progress=progress,
            progress_summary=progress_summary,
            total_completed=total_completed,
            total_courses=len(courses),
            quiz_scores_count=total_quiz_scores,
            certificates_earned=certificates_earned,
            total_coins_earned=total_coins_earned,
            badges_earned=badges_earned,
            profile_form=profile_form,
            upload_form=upload_form,
            profile_data=profile_data,
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang),
            tools=tools,
            bottom_nav_items=bottom_nav_items,
            role_filter=role_filter,
            activities=activities
        )
        
    except Exception as e:
        logger.error(f"Error rendering main learning hub page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_error_loading", default="Error loading learning hub", lang=lang), "danger")
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        return render_template(
            'learning_hub/learning_hub_main.html',
            courses={},
            progress={},
            progress_summary=[],
            total_completed=0,
            total_courses=0,
            quiz_scores_count=0,
            certificates_earned=0,
            total_coins_earned=format_currency(0, currency='NGN'),
            badges_earned=[],
            profile_form=LearningHubProfileForm(),
            upload_form=UploadForm(),
            profile_data={},
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang),
            tools=tools,
            bottom_nav_items=bottom_nav_items,
            role_filter='all',
            activities=[],
            error=str(e)
        ), 500

@learning_hub_bp.route('/api/course/<course_id>')
@requires_role(['personal', 'admin'])
def get_course_data(course_id):
    """API endpoint to get course data."""
    try:
        course = course_lookup(course_id)
        if not course:
            return jsonify({'success': False, 'message': trans('learning_hub_course_not_found', default='Course not found')}), 404
        
        progress = get_progress()
        course_progress = progress.get(course_id, {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []})
        
        return jsonify({
            'success': True,
            'course': course,
            'progress': course_progress
        })
    except Exception as e:
        logger.error(f"Error getting course data: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_course_load_error', default='Error loading course')}), 500

@learning_hub_bp.route('/api/lesson')
@requires_role(['personal', 'admin'])
def get_lesson_data():
    """API endpoint to get lesson data."""
    try:
        course_id = request.args.get('course_id')
        lesson_id = request.args.get('lesson_id')
        
        course = course_lookup(course_id)
        if not course:
            return jsonify({'success': False, 'message': trans('learning_hub_course_not_found', default='Course not found')}), 404
        
        lesson, module = lesson_lookup(course, lesson_id)
        if not lesson:
            return jsonify({'success': False, 'message': trans('learning_hub_lesson_not_found', default='Lesson not found')}), 404
        
        progress = get_progress()
        course_progress = progress.get(course_id, {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []})
        
        # Find next lesson
        next_lesson_id = None
        found = False
        for m in course['modules']:
            for l in m['lessons']:
                if found and l.get('id'):
                    next_lesson_id = l['id']
                    break
                if l['id'] == lesson_id:
                    found = True
            if next_lesson_id:
                break
        
        return jsonify({
            'success': True,
            'course': course,
            'lesson': lesson,
            'progress': course_progress,
            'next_lesson_id': next_lesson_id
        })
    except Exception as e:
        logger.error(f"Error getting lesson data: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_lesson_load_error', default='Error loading lesson')}), 500

@learning_hub_bp.route('/api/quiz')
@requires_role(['personal', 'admin'])
def get_quiz_data():
    """API endpoint to get quiz data."""
    try:
        course_id = request.args.get('course_id')
        quiz_id = request.args.get('quiz_id')
        
        course = course_lookup(course_id)
        if not course:
            return jsonify({'success': False, 'message': trans('learning_hub_course_not_found', default='Course not found')}), 404
        
        quiz = get_mongo_db().learning_materials.find_one({'type': 'quiz', 'id': quiz_id})
        if not quiz:
            return jsonify({'success': False, 'message': trans('learning_hub_quiz_not_found', default='Quiz not found')}), 404
        
        progress = get_progress()
        course_progress = progress.get(course_id, {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []})
        
        return jsonify({
            'success': True,
            'course': course,
            'quiz': quiz,
            'progress': course_progress
        })
    except Exception as e:
        logger.error(f"Error getting quiz data: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_quiz_load_error', default='Error loading quiz')}), 500

@learning_hub_bp.route('/api/lesson/action', methods=['POST'])
@requires_role(['personal', 'admin'])
def lesson_action():
    """Handle lesson actions like marking complete."""
    try:
        course_id = request.form.get('course_id')
        lesson_id = request.form.get('lesson_id')
        action = request.form.get('action')
        
        if action == 'mark_complete':
            progress = get_progress()
            if course_id not in progress:
                course_progress = {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': lesson_id, 'coins_earned': 0, 'badges_earned': []}
                progress[course_id] = course_progress
            else:
                course_progress = progress[course_id]
            
            if lesson_id not in course_progress['lessons_completed']:
                course_progress['lessons_completed'].append(lesson_id)
                course_progress['current_lesson'] = lesson_id
                # Award coins and badges
                coins_earned = 0
                badge_earned = None
                if course_id == 'tax_reforms_2025' and lesson_id == 'tax_reforms_2025-module-1-lesson-1':
                    coins_earned = 3
                elif course_id == 'digital_foundations' and lesson_id == 'digital_foundations-module-1-lesson-1':
                    coins_earned = 3
                    badge_earned = {'title_key': 'learning_hub_badge_digital_starter', 'title_en': 'Digital Starter'}
                course_progress['coins_earned'] = clean_currency(course_progress.get('coins_earned', 0)) + coins_earned
                if badge_earned and badge_earned not in course_progress['badges_earned']:
                    course_progress['badges_earned'].append(badge_earned)
                save_course_progress(course_id, course_progress)
                
                # Send email if user has provided details and opted in
                profile = session.get('learning_hub_profile', {})
                if profile.get('send_email') and profile.get('email'):
                    try:
                        course = course_lookup(course_id)
                        lesson, _ = lesson_lookup(course, lesson_id)
                        
                        config = EMAIL_CONFIG.get("learning_hub_lesson_completed", {})
                        subject = trans(config.get("subject_key", "learning_hub_lesson_completed_subject"), default="Lesson Completed", lang=session.get('lang', 'en'))
                        template = config.get("template", "learning_hub_lesson_completed.html")
                        
                        send_email(
                            app=current_app,
                            logger=logger,
                            to_email=profile['email'],
                            subject=subject,
                            template_name=template,
                            data={
                                "first_name": profile.get('first_name', ''),
                                "course_title": course.get('title_en', ''),
                                "lesson_title": lesson.get('title_en', ''),
                                "completed_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                                "cta_url": url_for('learning_hub.main', _external=True),
                                "unsubscribe_url": url_for('learning_hub.unsubscribe', email=profile['email'], _external=True),
                                "coins_earned": format_currency(coins_earned, currency='NGN'),
                                "badge_earned": badge_earned.get('title_en') if badge_earned else None
                            },
                            lang=session.get('lang', 'en')
                        )
                    except Exception as e:
                        logger.error(f"Failed to send email for lesson {lesson_id}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
                
                return jsonify({
                    'success': True,
                    'message': trans('learning_hub_lesson_completed', default='Lesson marked as complete'),
                    'coins_earned': format_currency(coins_earned, currency='NGN'),
                    'badge_earned': badge_earned.get('title_en') if badge_earned else None
                })
            else:
                return jsonify({
                    'success': True,
                    'message': trans('learning_hub_lesson_already_completed', default='Lesson already completed'),
                    'coins_earned': format_currency(0, currency='NGN'),
                    'badge_earned': None
                })
        
        return jsonify({'success': False, 'message': trans('learning_hub_invalid_action', default='Invalid action')}), 400
    except Exception as e:
        logger.error(f"Error in lesson action: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_action_error', default='Error processing action')}), 500

@learning_hub_bp.route('/api/quiz/action', methods=['POST'])
@requires_role(['personal', 'admin'])
def quiz_action():
    """Handle quiz actions like submitting answers, including Reality Check Quiz."""
    try:
        course_id = request.form.get('course_id')
        quiz_id = request.form.get('quiz_id')
        action = request.form.get('action')
        
        if action == 'submit_quiz' or action == 'submit_reality_check':
            quiz = get_mongo_db().learning_materials.find_one({'type': 'quiz', 'id': quiz_id})
            if not quiz:
                return jsonify({'success': False, 'message': trans('learning_hub_quiz_not_found', default='Quiz not found')}), 404
            
            # Calculate score
            score = 0
            for i, question in enumerate(quiz['questions']):
                user_answer = request.form.get(f'q{i}')
                if user_answer and user_answer == question['answer_en']:
                    score += 1
            
            # Check if quiz score meets passmark (60% for most quizzes)
            passmark = 0.6 * len(quiz['questions']) if quiz_id != 'reality_check_quiz' else 0
            passed = score >= passmark
            
            # Save score and award coins/badges
            progress = get_progress()
            if course_id not in progress and quiz_id != 'reality_check_quiz':
                course_progress = {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []}
                progress[course_id] = course_progress
            else:
                course_progress = progress.get(course_id, {'lessons_completed': [], 'quiz_scores': {}, 'current_lesson': None, 'coins_earned': 0, 'badges_earned': []})
            
            coins_earned = 0
            badge_earned = None
            if quiz_id == 'quiz-tax-reforms-2025' and passed and quiz_id not in course_progress.get('quiz_scores', {}):
                coins_earned = 3
            elif quiz_id == 'reality_check_quiz' and quiz_id not in course_progress.get('quiz_scores', {}):
                coins_earned = 3
                badge_earned = {'title_key': 'learning_hub_badge_reality_check', 'title_en': 'Reality Check'}
            
            course_progress['quiz_scores'][quiz_id] = score
            course_progress['coins_earned'] = clean_currency(course_progress.get('coins_earned', 0)) + coins_earned
            if badge_earned and badge_earned not in course_progress['badges_earned']:
                course_progress['badges_earned'].append(badge_earned)
            if quiz_id != 'reality_check_quiz':
                save_course_progress(course_id, course_progress)
            else:
                session['reality_check_score'] = score
                session.permanent = True
                session.modified = True
            
            # Send email notification for quiz completion
            profile = session.get('learning_hub_profile', {})
            if profile.get('send_email') and profile.get('email'):
                try:
                    course = course_lookup(course_id) if course_id else {'title_en': 'Reality Check Quiz'}
                    config = EMAIL_CONFIG.get("learning_hub_quiz_completed", {})
                    subject = trans(config.get("subject_key", "learning_hub_quiz_completed_subject"), default="Quiz Completed", lang=session.get('lang', 'en'))
                    template = config.get("template", "learning_hub_quiz_completed.html")
                    
                    send_email(
                        app=current_app,
                        logger=logger,
                        to_email=profile['email'],
                        subject=subject,
                        template_name=template,
                        data={
                            "first_name": profile.get('first_name', ''),
                            "course_title": course.get('title_en', ''),
                            "quiz_title": quiz.get('id', ''),
                            "score": score,
                            "total": len(quiz['questions']),
                            "passed": passed,
                            "coins_earned": format_currency(coins_earned, currency='NGN'),
                            "badge_earned": badge_earned.get('title_en') if badge_earned else None,
                            "completed_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                            "cta_url": url_for('learning_hub.main', _external=True),
                            "unsubscribe_url": url_for('learning_hub.unsubscribe', email=profile['email'], _external=True)
                        },
                        lang=session.get('lang', 'en')
                    )
                except Exception as e:
                    logger.error(f"Failed to send email for quiz {quiz_id}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
            
            message = trans('learning_hub_quiz_submitted', default='Quiz submitted successfully')
            if quiz_id == 'reality_check_quiz':
                message = trans('learning_hub_quiz_submitted', default='Quiz submitted successfully') + '. '
                message += trans('learning_hub_quiz_recommendation', default='We recommend starting with the Digital Foundations course to build your ICT skills!') if score < 2 else trans('learning_hub_quiz_perfect', default='Great job! You have strong ICT basics!')
            
            return jsonify({
                'success': True,
                'message': message,
                'score': score,
                'total': len(quiz['questions']),
                'passed': passed,
                'coins_earned': format_currency(coins_earned, currency='NGN'),
                'badge_earned': badge_earned.get('title_en') if badge_earned else None
            })
        
        return jsonify({'success': False, 'message': trans('learning_hub_invalid_action', default='Invalid action')}), 400
    except Exception as e:
        logger.error(f"Error in quiz action: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_quiz_error', default='Error processing quiz')}), 500

@learning_hub_bp.route('/api/set_role_filter', methods=['POST'])
@requires_role(['personal', 'admin'])
def set_role_filter():
    """Set role filter for course display."""
    try:
        role = request.form.get('role')
        if role not in ['all', 'civil_servant', 'nysc', 'agent']:
            return jsonify({'success': False, 'message': trans('learning_hub_invalid_role', default='Invalid role selected')}), 400
        session['role_filter'] = role
        session.permanent = True
        session.modified = True
        logger.info(f"Set role filter to {role}", extra={'session_id': session['sid']})
        return jsonify({'success': True, 'message': trans('learning_hub_role_updated', default='Role filter updated')})
    except Exception as e:
        logger.error(f"Error setting role filter: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_role_error', default='Error updating role filter')}), 500

@learning_hub_bp.route('/register_webinar', methods=['POST'])
@requires_role(['personal', 'admin'])
def register_webinar():
    """Handle webinar registration."""
    try:
        email = request.form.get('email')
        if not email:
            flash(trans('general_email_required', default='Email is required'), 'danger')
            return redirect(url_for('learning_hub.main'))
        
        # Save webinar registration to MongoDB
        get_mongo_db().webinar_registrations.insert_one({
            'email': email,
            'user_id': current_user.id if current_user.is_authenticated else None,
            'session_id': session['sid'],
            'registered_at': datetime.utcnow()
        })
        
        # Send confirmation email
        config = EMAIL_CONFIG.get("learning_hub_webinar_registration", {})
        subject = trans(config.get("subject_key", "learning_hub_webinar_registration_subject"), default="Webinar Registration Confirmed", lang=session.get('lang', 'en'))
        template = config.get("template", "learning_hub_webinar_registration.html")
        
        send_email(
            app=current_app,
            logger=logger,
            to_email=email,
            subject=subject,
            template_name=template,
            data={
                "first_name": session.get('learning_hub_profile', {}).get('first_name', ''),
                "webinar_date": "TBD",  # Placeholder; update with actual date
                "cta_url": url_for('learning_hub.main', _external=True),
                "unsubscribe_url": url_for('learning_hub.unsubscribe', email=email, _external=True)
            },
            lang=session.get('lang', 'en')
        )
        
        flash(trans('learning_hub_webinar_registered', default='Successfully registered for the webinar!'), 'success')
        logger.info(f"Registered email {email} for webinar", extra={'session_id': session['sid']})
        return redirect(url_for('learning_hub.main'))
    except Exception as e:
        logger.error(f"Error registering for webinar: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_webinar_error', default='Error registering for webinar'), 'danger')
        return redirect(url_for('learning_hub.main')), 500

@learning_hub_bp.route('/profile', methods=['GET', 'POST'])
@requires_role(['personal', 'admin'])
def profile():
    """Handle user profile form for first name and email."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    db = get_mongo_db()
    
    try:
        log_tool_usage(
            db=db,
            tool_name='learning_hub',
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session['sid'],
            action='profile_submit' if request.method == 'POST' else 'profile_view'
        )
        
        profile_form = LearningHubProfileForm()
        if request.method == 'POST' and profile_form.validate_on_submit():
            session['learning_hub_profile'] = {
                'first_name': profile_form.first_name.data,
                'email': profile_form.email.data,
                'send_email': profile_form.send_email.data
            }
            session.permanent = True
            session.modified = True
            
            logger.info(f"Profile saved for user {current_user.id if current_user.is_authenticated else 'anonymous'}", extra={'session_id': session.get('sid', 'no-session-id')})
            flash(trans('learning_hub_profile_saved', default='Profile saved successfully', lang=lang), 'success')
            return redirect(url_for('personal.index'))
        
        elif request.method == 'POST':
            flash(trans('learning_hub_profile_failed', default='Failed to save profile', lang=lang), 'danger')
        
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        return render_template(
            'learning_hub/learning_hub_profile.html',
            profile_form=profile_form,
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_profile_title', default='Learning Hub Profile', lang=lang),
            tools=tools,
            bottom_nav_items=bottom_nav_items
        )
        
    except Exception as e:
        logger.error(f"Error in profile page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_error_loading", default="Error loading profile", lang=lang), "danger")
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        return render_template(
            'learning_hub/learning_hub_profile.html',
            profile_form=LearningHubProfileForm(),
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_profile_title', default='Learning Hub Profile', lang=lang),
            tools=tools,
            bottom_nav_items=bottom_nav_items,
            error=str(e)
        ), 500

@learning_hub_bp.route('/unsubscribe/<email>')
@requires_role(['personal', 'admin'])
def unsubscribe(email):
    """Unsubscribe user from learning hub emails."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
        db = get_mongo_db()
    
    try:
        log_tool_usage(
            db=db,
            tool_name='learning_hub',
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session['sid'],
            action='unsubscribe'
        )
        
        lang = session.get('lang', 'en')
        profile = session.get('learning_hub_profile', {})
        
        if is_admin() or (profile.get('email') == email and profile.get('send_email', False)):
            profile['send_email'] = False
            session['learning_hub_profile'] = profile
            session.permanent = True
            session.modified = True
            logger.info(f"Unsubscribed email {email}", extra={'session_id': session.get('sid', 'no-session-id')})
            flash(trans("learning_hub_unsubscribed_success", default="Successfully unsubscribed from emails", lang=lang), "success")
        else:
            logger.warning(f"Failed to unsubscribe email {email}: No matching profile or already unsubscribed", extra={'session_id': session.get('sid', 'no-session-id')})
            flash(trans("learning_hub_unsubscribe_failed", default="Failed to unsubscribe. Email not found or already unsubscribed.", lang=lang), "danger")
        
        return redirect(url_for('personal.index'))
        
    except Exception as e:
        logger.error(f"Error in unsubscribe: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_unsubscribe_error", default="Error processing unsubscribe request", lang=lang), "danger")
        return redirect(url_for('personal.index')), 500

@learning_hub_bp.route('/static/uploads/<path:filename>')
@requires_role(['personal', 'admin'])
def serve_uploaded_file(filename):
    """Serve uploaded files securely with caching."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
        db = get_mongo_db()
    
    try:
        log_tool_usage(
            db=db,
            tool_name='learning_hub',
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session['sid'],
            action='serve_file'
        )
        
        response = send_from_directory(current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), filename)
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        logger.info(f"Served file: {filename}", extra={'session_id': session.get('sid', 'no-session-id')})
        return response
        
    except Exception as e:
        logger.error(f"Error serving uploaded file {filename}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_file_not_found", default="File not found", lang=session.get('lang', 'en')), "danger")
        return redirect(url_for('personal.index')), 404

@learning_hub_bp.errorhandler(404)
def handle_not_found(e):
    """Handle 404 errors with user-friendly message."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
    bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
    logger.error(f"404 error on {request.path}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
    flash(trans("learning_hub_not_found", default="The requested page was not found. Please check the URL or return to the main page.", lang=lang), "danger")
    return render_template(
        'learning_hub/learning_hub_main.html',
        courses={},
        progress={},
        progress_summary=[],
        total_completed=0,
        total_courses=0,
        quiz_scores_count=0,
        certificates_earned=0,
        total_coins_earned=format_currency(0, currency='NGN'),
        badges_earned=[],
        profile_form=LearningHubProfileForm(),
        upload_form=UploadForm(),
        profile_data={},
        t=trans,
        lang=lang,
        tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang),
        tools=tools,
        bottom_nav_items=bottom_nav_items,
        role_filter='all',
        activities=[],
        error=str(e)
    ), 404

@learning_hub_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
    bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
    logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'no-session-id')})
    flash(trans("learning_hub_csrf_error", default="Form submission failed due to a missing security token. Please refresh and try again.", lang=lang), "danger")
    return render_template(
        'learning_hub/learning_hub_main.html',
        courses={},
        progress={},
        progress_summary=[],
        total_completed=0,
        total_courses=0,
        quiz_scores_count=0,
        certificates_earned=0,
        total_coins_earned=format_currency(0, currency='NGN'),
        badges_earned=[],
        profile_form=LearningHubProfileForm(),
        upload_form=UploadForm(),
        profile_data={},
        t=trans,
        lang=lang,
        tool_title=trans('learning_hub_title', default='Learning Hub', lang=lang),
        tools=tools,
        bottom_nav_items=bottom_nav_items,
        role_filter='all',
        activities=[],
        error=e.description
    ), 403

@learning_hub_bp.route('/legacy/<course_id>')
@requires_role(['personal', 'admin'])
def legacy_course_redirect(course_id):
    """Redirect legacy course URLs to the main learning hub."""
    try:
        if 'sid' not in session:
            create_anonymous_session()
            session.permanent = True
            session.modified = True
        
        logger.info(f"Redirecting legacy course {course_id} to main", extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_legacy_redirect', default='This course URL has been updated. Redirecting to the main Learning Hub.', lang=session.get('lang', 'en')), 'info')
        return redirect(url_for('learning_hub.main'))
    except Exception as e:
        logger.error(f"Error redirecting legacy course {course_id}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_error_loading', default='Error loading course', lang=session.get('lang', 'en')), 'danger')
        return redirect(url_for('personal.index')), 500

@learning_hub_bp.route('/legacy/quiz/<quiz_id>')
@requires_role(['personal', 'admin'])
def legacy_quiz_redirect(quiz_id):
    """Redirect legacy quiz URLs to the main learning hub."""
    try:
        if 'sid' not in session:
            create_anonymous_session()
            session.permanent = True
            session.modified = True
        
        logger.info(f"Redirecting legacy quiz {quiz_id} to main", extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_legacy_redirect', default='This quiz URL has been updated. Redirecting to the main Learning Hub.', lang=session.get('lang', 'en')), 'info')
        return redirect(url_for('learning_hub.main'))
    except Exception as e:
        logger.error(f"Error redirecting legacy quiz {quiz_id}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans('learning_hub_error_loading', default='Error loading quiz', lang=session.get('lang', 'en')), 'danger')
        return redirect(url_for('personal.index')), 500

@learning_hub_bp.route('/courses')
@requires_role(['personal', 'admin'])
def courses():
    """Redirect to main page with courses tab."""
    return redirect(url_for('learning_hub.main') + '#courses')

@learning_hub_bp.route('/courses/<course_id>')
@requires_role(['personal', 'admin'])
def course_overview(course_id):
    """Redirect to main page and load course overview."""
    return redirect(url_for('learning_hub.main') + f'#course-{course_id}')

@learning_hub_bp.route('/courses/<course_id>/lesson/<lesson_id>')
@requires_role(['personal', 'admin'])
def lesson(course_id, lesson_id):
    """Redirect to main page and load lesson."""
    return redirect(url_for('learning_hub.main') + f'#lesson-{course_id}-{lesson_id}')

@learning_hub_bp.route('/courses/<course_id>/quiz/<quiz_id>')
@requires_role(['personal', 'admin'])
def quiz(course_id, quiz_id):
    """Redirect to main page and load quiz."""
    return redirect(url_for('learning_hub.main') + f'#quiz-{course_id}-{quiz_id}')
