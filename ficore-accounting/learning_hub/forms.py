from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, FileField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional, Length, Regexp
from utils import trans
from flask import session

class UploadForm(FlaskForm):
    """Form for uploading lesson or course content for the learning hub."""
    title = StringField(
        trans('learning_hub_course_title', default='Lesson/Course Title (English)'),
        validators=[DataRequired(), Length(min=3, max=100)],
        description="Enter the lesson or course title in English."
    )
    title_ha = StringField(
        'Lesson Title (Hausa)',
        validators=[Optional(), Length(min=3, max=100)],
        description="Enter the lesson title in Hausa (optional)."
    )
    course_id = StringField(
        trans('learning_hub_course_id', default='Course ID'),
        validators=[DataRequired(), Regexp(r'^[a-z0-9_]+$')],
        description="Enter the course ID (e.g., budgeting_101)."
    )
    module_id = StringField(
        'Module ID',
        validators=[Optional(), Regexp(r'^[a-z0-9_-]+$')],
        description="Enter the module ID this lesson belongs to (e.g., module-1, optional)."
    )
    description = TextAreaField(
        trans('learning_hub_description', default='Description'),
        validators=[Optional(), Length(max=5000)],
        description="Enter the course or lesson description."
    )
    content_type = SelectField(
        trans('learning_hub_content_type', default='Content Type'),
        choices=[('text', 'Text'), ('video', 'Video'), ('pdf', 'PDF')],
        validators=[DataRequired()],
        description="Select the type of content."
    )
    content_file = FileField(
        trans('learning_hub_upload_file', default='Upload File'),
        validators=[Optional()],
        description="Upload a file (e.g., MP4 for video, PDF for documents)."
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
    is_premium = BooleanField(
        trans('learning_hub_is_premium', default='Premium Content'),
        default=False,
        description="Mark this content as premium."
    )
    roles = SelectField(
        trans('learning_hub_roles', default='Roles'),
        choices=[
            ('all', 'All Roles'), ('trader', 'Trader'),
            ('personal', 'personal Member'), ('agent', 'Agent')
        ],
        validators=[Optional()],
        description="Select the roles that can access this content."
    )
    theme = SelectField(
        trans('learning_hub_theme', default='Theme'),
        choices=[
            ('personal_finance', 'Personal Finance'),
            ('business_essentials', 'Business Essentials'),
            ('agent_training', 'Agent Training'),
            ('compliance', 'Compliance'),
            ('tool_tutorials', 'Tool Tutorials')
        ],
        validators=[Optional()],
        description="Select the theme for this content."
    )
    submit = SubmitField(trans('learning_hub_upload', default='Upload'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.title.validators[0].message = trans('learning_hub_course_title_required', default='Course/lesson title is required', lang=lang)
        self.course_id.validators[0].message = trans('learning_hub_course_id_required', default='Course ID is required', lang=lang)
        if self.description.validators:
            self.description.validators[0].message = trans('learning_hub_description_required', default='Description is required', lang=lang)
        self.content_type.validators[0].message = trans('learning_hub_content_type_required', default='Content type is required', lang=lang)
        if self.content_file.validators and self.content_type.data in ['video', 'pdf']:
            self.content_file.validators = [DataRequired(message=trans('learning_hub_file_required', default='File is required', lang=lang))]
        if self.roles.validators:
            self.roles.validators[0].message = trans('learning_hub_roles_required', default='Role is required', lang=lang)
        if self.theme.validators:
            self.theme.validators[0].message = trans('learning_hub_theme_required', default='Theme is required', lang=lang)

class LearningHubProfileForm(FlaskForm):
    """Form for updating user profile settings in the learning hub."""
    full_name = StringField(
        trans('general_first_name', default='Full Name'),
        validators=[DataRequired(), Length(min=2, max=100)],
        description="Enter your full name."
    )
    email = StringField(
        trans('general_email', default='Email'),
        validators=[Optional(), Email()],
        description="Enter your email address (optional)."
    )
    phone_number = StringField(
        'Phone Number',
        validators=[Optional(), Regexp(r'^\+?234\d{10}$', message="Enter a valid Nigerian phone number (e.g., +2348031234567).")],
        description="Enter your phone number (optional)."
    )
    language = SelectField(
        'Preferred Language',
        choices=[('en', 'English'), ('ha', 'Hausa')],
        validators=[DataRequired()],
        description="Select your preferred language for the learning hub."
    )
    role = SelectField(
        'Role',
        choices=[
            ('trader', 'Trader'),
            ('personal', 'personal Member'),
            ('agent', 'Agent')
        ],
        validators=[DataRequired()],
        description="Select your role to access relevant courses."
    )
    send_email = BooleanField(
        trans('general_send_email', default='Send Email Notifications'),
        default=False,
        description="Check to receive email notifications."
    )
    submit = SubmitField(trans('general_submit', default='Update Profile'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.full_name.validators[0].message = trans('general_first_name_required', default='Full name is required', lang=lang)
        if self.email.validators:
            self.email.validators[1].message = trans('general_email_invalid', default='Please enter a valid email address', lang=lang)
