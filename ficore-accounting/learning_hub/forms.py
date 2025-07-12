from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, FileField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional, Length, Regexp
from utils import trans
from flask import session

class UploadForm(FlaskForm):
    """Form for uploading lesson content (e.g., videos, text) for the learning hub."""
    title = StringField(
        'Lesson Title (English)',
        validators=[DataRequired(), Length(min=3, max=100)],
        description="Enter the lesson title in English."
    )
    title_ha = StringField(
        'Lesson Title (Hausa)',
        validators=[DataRequired(), Length(min=3, max=100)],
        description="Enter the lesson title in Hausa."
    )
    content_type = SelectField(
        'Content Type',
        choices=[('text', 'Text'), ('video', 'Video')],
        validators=[DataRequired()],
        description="Select the type of content for this lesson."
    )
    content_file = FileField(
        'Content File',
        validators=[Optional()],
        description="Upload a video file (e.g., MP4) for video lessons."
    )
    content_text = TextAreaField(
        'Content Text (English)',
        validators=[Optional(), Length(max=5000)],
        description="Enter the lesson content in English (for text-based lessons)."
    )
    content_text_ha = TextAreaField(
        'Content Text (Hausa)',
        validators=[Optional(), Length(max=5000)],
        description="Enter the lesson content in Hausa (for text-based lessons)."
    )
    course_id = StringField(
        'Course ID',
        validators=[DataRequired(), Regexp(r'^[a-z0-9_]+$')],
        description="Enter the course ID this lesson belongs to (e.g., budgeting_101)."
    )
    module_id = StringField(
        'Module ID',
        validators=[DataRequired(), Regexp(r'^[a-z0-9_-]+$')],
        description="Enter the module ID this lesson belongs to (e.g., module-1)."
    )
    submit = SubmitField('Upload Lesson')

class LearningHubProfileForm(FlaskForm):
    """Form for updating user profile settings in the learning hub."""
    language = SelectField(
        'Preferred Language',
        choices=[('en', 'English'), ('ha', 'Hausa')],
        validators=[DataRequired()],
        description="Select your preferred language for the learning hub."
    )
    role = SelectField(
        'Role',
        choices=[
            ('civil_servant', 'Civil Servant'),
            ('nysc', 'NYSC Member'),
            ('agent', 'Agent')
        ],
        validators=[DataRequired()],
        description="Select your role to access relevant courses."
    )
    full_name = StringField(
        'Full Name',
        validators=[DataRequired(), Length(min=2, max=100)],
        description="Enter your full name."
    )
    phone_number = StringField(
        'Phone Number',
        validators=[Optional(), Regexp(r'^\+?234\d{10}$', message="Enter a valid Nigerian phone number (e.g., +2348031234567).")],
        description="Enter your phone number (optional)."
    )
    submit = SubmitField('Update Profile')
    

class LearningHubProfileForm(FlaskForm):
    first_name = StringField(trans('general_first_name', default='First Name'), validators=[DataRequired()])
    email = StringField(trans('general_email', default='Email'), validators=[Optional(), Email()])
    send_email = BooleanField(trans('general_send_email', default='Send Email'), default=False)
    submit = SubmitField(trans('general_submit', default='Submit'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.first_name.validators[0].message = trans('general_first_name_required', default='First name is required', lang=lang)
        if self.email.validators:
            self.email.validators[1].message = trans('general_email_invalid', default='Please enter a valid email address', lang=lang)

class UploadForm(FlaskForm):
    title = StringField(trans('learning_hub_course_title', default='Course Title'), validators=[DataRequired()])
    course_id = StringField(trans('learning_hub_course_id', default='Course ID'), validators=[DataRequired()])
    description = TextAreaField(trans('learning_hub_description', default='Description'), validators=[DataRequired()])
    content_type = SelectField(trans('learning_hub_content_type', default='Content Type'), choices=[
        ('video', 'Video'), ('text', 'Text'), ('pdf', 'PDF')
    ], validators=[DataRequired()])
    is_premium = BooleanField(trans('learning_hub_is_premium', default='Premium Content'), default=False)
    roles = SelectField(trans('learning_hub_roles', default='Roles'), choices=[
        ('all', 'All Roles'), ('civil_servant', 'Civil Servant'), ('nysc', 'NYSC Member'), ('agent', 'Agent')
    ], validators=[DataRequired()])
    theme = SelectField(trans('learning_hub_theme', default='Theme'), choices=[
        ('personal_finance', 'Personal Finance'),
        ('business_essentials', 'Business Essentials'),
        ('agent_training', 'Agent Training'),
        ('compliance', 'Compliance'),
        ('tool_tutorials', 'Tool Tutorials')
    ], validators=[DataRequired()])
    file = FileField(trans('learning_hub_upload_file', default='Upload File'), validators=[DataRequired()])
    submit = SubmitField(trans('learning_hub_upload', default='Upload'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.title.validators[0].message = trans('learning_hub_course_title_required', default='Course title is required', lang=lang)
        self.course_id.validators[0].message = trans('learning_hub_course_id_required', default='Course ID is required', lang=lang)
        self.description.validators[0].message = trans('learning_hub_description_required', default='Description is required', lang=lang)
        self.content_type.validators[0].message = trans('learning_hub_content_type_required', default='Content type is required', lang=lang)
        self.file.validators[0].message = trans('learning_hub_file_required', default='File is required', lang=lang)
        self.roles.validators[0].message = trans('learning_hub_roles_required', default='Role is required', lang=lang)
        self.theme.validators[0].message = trans('learning_hub_theme_required', default='Theme is required', lang=lang)
