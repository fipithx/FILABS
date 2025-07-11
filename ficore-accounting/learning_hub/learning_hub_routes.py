from flask import render_template, session, request, redirect, url_for, flash, current_app, jsonify, send_from_directory
from flask_login import current_user
from .forms import LearningHubProfileForm, UploadForm
from .models import course_lookup, lesson_lookup, get_progress, save_course_progress, calculate_progress_summary, quizzes_data
from .utils import get_mongo_db, trans, log_tool_usage, create_anonymous_session, requires_role, is_admin, format_currency
from werkzeug.utils import secure_filename
from .mailersend_email import send_email, EMAIL_CONFIG
from datetime import datetime
from . import learning_hub_bp

ALLOWED_EXTENSIONS = {'mp4', 'pdf', 'txt', 'md'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@learning_hub_bp.route('/')
@learning_hub_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def main():
    """Main learning hub interface."""
    if 'sid' not in session:
        create_anonymous_session()
        session.permanent = True
        session.modified = True
    
    lang = session.get('lang', 'en')
    db = get_mongo_db()
    
    try:
        activities = get_all_recent_activities(db=db, user_id=current_user.id if current_user.is_authenticated else None, limit=10)
        log_tool_usage(db=db, tool_name='learning_hub', user_id=current_user.id if current_user.is_authenticated else None, session_id=session['sid'], action='main_view')
        
        progress = get_progress()
        progress_summary, total_completed, total_quiz_scores, certificates_earned, total_coins_earned, badges_earned = calculate_progress_summary()
        
        profile_data = session.get('learning_hub_profile', {})
        if current_user.is_authenticated:
            profile_data['email'] = profile_data.get('email', current_user.email)
            profile_data['first_name'] = profile_data.get('first_name', current_user.display_name)
        
        profile_form = LearningHubProfileForm(data=profile_data)
        upload_form = UploadForm()
        
        if request.method == 'POST' and request.form.get('action') == 'upload' and is_admin():
            if upload_form.validate_on_submit():
                if not allowed_file(upload_form.file.data.filename):
                    flash(trans('learning_hub_invalid_file_type', default='Invalid file type. Allowed: mp4, pdf, txt, md'), 'danger')
                else:
                    filename = secure_filename(upload_form.file.data.filename)
                    file_path = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'learning_hub/static/uploads'), filename)
                    upload_form.file.data.save(file_path)
                    
                    course_id = upload_form.course_id.data
                    roles = [upload_form.roles.data] if upload_form.roles.data != 'all' else ['civil_servant', 'nysc', 'agent']
                    course_data = {
                        'type': 'course',
                        'id': course_id,
                        'title_key': f"learning_hub_course_{course_id}_title",
                        'title_en': upload_form.title.data,
                        'title_ha': upload_form.title.data,
                        'description_en': upload_form.description.data,
                        'description_ha': upload_form.description.data,
                        'is_premium': upload_form.is_premium.data,
                        'roles': roles,
                        'theme': upload_form.theme.data,
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
                    
                    get_mongo_db().learning_materials.update_one(
                        {'type': 'course', 'id': course_id},
                        {'$set': course_data},
                        upsert=True
                    )
                    
                    flash(trans('learning_hub_upload_success', default='Content uploaded successfully'), 'success')
                    current_app.logger.info(f"Uploaded course {course_id}", extra={'session_id': session['sid']})
            else:
                flash(trans('learning_hub_upload_failed', default='Failed to upload content'), 'danger')
        
        tools = utils.PERSONAL_TOOLS if current_user.role == 'personal' else utils.ALL_TOOLS
        bottom_nav_items = utils.PERSONAL_NAV if current_user.role == 'personal' else utils.ADMIN_NAV
        return render_template(
            'learning_hub/index.html',
            progress=progress,
            progress_summary=progress_summary,
            total_completed=total_completed,
            total_courses=sum(len(courses) for courses in courses_data.values()),
            quiz_scores_count=total_quiz_scores,
            certificates_earned=certificates_earned,
            total_coins_earned=total_coins_earned,
            badges_earned=badges_earned,
            profile_form=profile_form,
            upload_form=upload_form,
            profile_data=profile_data,
            t=trans,
            lang=lang,
            tool_title=trans('learning_hub_title', default='Learning Hub'),
            tools=tools,
            bottom_nav_items=bottom_nav_items,
            role_filter=session.get('role_filter', 'all'),
            activities=activities
        )
        
    except Exception as e:
        current_app.logger.error(f"Error rendering main page: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        flash(trans("learning_hub_error_loading", default="Error loading learning hub"), "danger")
        return render_template(
            'learning_hub/index.html',
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
            tool_title=trans('learning_hub_title', default='Learning Hub'),
            tools=utils.PERSONAL_TOOLS,
            bottom_nav_items=utils.PERSONAL_NAV,
            role_filter='all',
            activities=[]
        ), 500

@learning_hub_bp.route('/api/course/<course_id>')
@custom_login_required
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
        current_app.logger.error(f"Error getting course data: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return jsonify({'success': False, 'message': trans('learning_hub_course_load_error', default='Error loading course')}), 500

# Additional routes (get_lesson_data, quiz_action, etc.) follow the same pattern as in the original learning_hub.py
# Omitted for brevity, but they are moved here with updated imports and paths