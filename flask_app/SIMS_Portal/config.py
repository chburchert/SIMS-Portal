import os

class Config:
	SECRET_KEY = os.environ.get('SECRET_KEY')
	SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')
	CONSUMER_KEY = os.environ.get('CONSUMER_KEY')
	CONSUMER_SECRET = os.environ.get('CONSUMER_SECRET')
	ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
	ACCESS_TOKEN_SECRET = os.environ.get('ACCESS_TOKEN_SECRET')
	SQLALCHEMY_TRACK_MODIFICATIONS = False
	MAIL_SERVER = 'smtp.dreamhost.com'
	MAIL_PORT = 465
	MAIL_USE_TLS = False
	MAIL_USE_SSL = True
	MAIL_USERNAME = 'sims_portal@dissolvingdata.com'
	MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
	MAIL_DEBUG = True
	SCHEDULER_API_ENABLED = True
	TRELLO_KEY = os.environ.get('TRELLO_KEY')
	TRELLO_TOKEN = os.environ.get('TRELLO_TOKEN')
	DATA_FOLDER = '/SIMS_Portal/static/data/'
	SLACK_BOT_TOKEN_NEW_USER = os.environ.get('SLACK_BOT_TOKEN_NEW_USER')
	SIMS_PORTAL_SLACK_BOT = os.environ.get('SIMS_PORTAL_SLACK_BOT')
	ROOT_URL = 'http://127.0.0.1:5000'
	DROPBOX_BOT = os.environ.get('DROPBOX_BOT')
	DROPBOX_APP_KEY = os.environ.get('DROPBOX_APP_KEY')
	DROPBOX_APP_SECRET = os.environ.get('DROPBOX_APP_SECRET')
	DROPBOX_REFRESH_TOKEN = os.environ.get('DROPBOX_REFRESH_TOKEN')
	SCHEDULER_TIMEZONE = "America/New_York"
	LANGUAGES = ['en', 'es']
	UPLOAD_EXTENSIONS = ['.jpg', '.png', '.gif']
	PORTFOLIO_TYPES = ['Map', 'Infographic', 'Dashboard', 'Mobile Data Collection', 'Assessment', 'Internal Analysis', 'External Report', 'Other']
	LOGTAIL_SOURCE_TOKEN = os.environ.get('LOGTAIL_SOURCE_TOKEN')
	POSITION_STACK_TOKEN = os.environ.get('POSITION_STACK_TOKEN')
	GOOGLE_MAPS_TOKEN = os.environ.get('GOOGLE_MAPS_TOKEN')
	WERKZEUG_DEBUG_PIN = '443-431-665'