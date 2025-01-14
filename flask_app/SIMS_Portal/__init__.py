from apscheduler.triggers.cron import CronTrigger
from datetime import datetime	
from dotenv import load_dotenv
from flask import Flask, redirect, url_for, request, render_template
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_apscheduler import APScheduler
from flask_babel import Babel
from flask_bcrypt import Bcrypt
from flask_caching import Cache
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy, inspect
from flaskext.markdown import Markdown
from logging.config import dictConfig
from logging.handlers import RotatingFileHandler
from logtail import LogtailHandler
from SIMS_Portal.config import Config
import babel
import flask_migrate
import logging
import os
import sqlalchemy as sa
from flask_wtf.csrf import CSRFProtect

load_dotenv()
db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'users.login' 
login_manager.login_message_category = 'danger'
cache = Cache()

def init_logging():
    dictConfig({
            'version': 1,
            'handlers': {
                    "console": {
                            "class": "logging.StreamHandler",
                    },
                    "logtail": {
                            "class": "logtail.LogtailHandler",
                            "source_token": os.environ.get('LOGTAIL_SOURCE_TOKEN'),
							"flush_interval": 60,
							"buffer_capacity": 1000,
                    },
            },
            "root": {"level": "INFO", "handlers": ["logtail", "console"]},
    })
init_logging()

from SIMS_Portal import models
from SIMS_Portal.main.utils import get_ns_list

# run utility to generate active NS list
def build_ns_dropdown():
	ns_list = get_ns_list()
	return {'ns_list': ns_list}

# AdminView inherits from ModelView to only show tables in the admin page if user is logged in AND is listed as an admin
class AdminView(ModelView):
	column_exclude_list = ('birthday', 'password', 'molnix_id', 'job_title', 'bio', 'roles', 'image_file', 'twitter', 'slack_id', 'github', 'created_at', 'updated_at', 'linked_in', 'messaging_number_country_code', 'messaging_number')
	column_hide_backrefs = False
	def is_accessible(self):
		try:
			if current_user.is_admin == 1:
				return current_user.is_authenticated
		except:
			pass
	
	def inaccessible_callback(self, name, **kwargs):
		return render_template('errors/403.html'), 403

def create_app(config_class=Config):
	app = Flask(__name__)
	app.config.from_object(Config)
	app.config['MAX_CONTENT_LENGTH'] = 75 * 1000 * 1000

	db.init_app(app)
	migrate.init_app(app, db)
	
	# send build_ns_dropdown() data to context_processor for use in layout.html
	app.context_processor(build_ns_dropdown)
	
	bcrypt.init_app(app)
	login_manager.init_app(app)
	admin = Admin(app, name='SIMS Admin Portal', template_mode='bootstrap4', endpoint='admin')
	babel = Babel(app)
	Markdown(app)
	cache.init_app(app)
	
	csrf = CSRFProtect(app)
	
	# @babel.localeselector
	# def get_locale():
	# 	user_lang = request.accept_languages.best_match(app.config['LANGUAGES'])
	# 	return request.accept_languages.best_match(app.config['LANGUAGES'])
	
	# logging
	if not app.debug:
		if not os.path.exists('logs'):
			os.mkdir('logs')
		file_handler = RotatingFileHandler('logs/sims-portal.log', maxBytes=1000000, backupCount=10)
		file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
		file_handler.setLevel(logging.INFO)
		app.logger.addHandler(file_handler)
		
		logtail_handler = logging.getLogger().handlers[1]
		app.logger.addHandler(logtail_handler)
		
		app.logger.setLevel(logging.INFO)
		app.logger.info('SIMS Portal Started Up')
	
	# only turn scheduled tasks on in production
	if app.config['DEBUG'] == False:
	
		scheduler = APScheduler()
		scheduler.init_app(app)
		scheduler.start()
		
		@scheduler.task('cron', id='run_surge_alert_refresh', hour='1,4,7,10,13,16')
		def run_surge_alert_refresh():
			with scheduler.app.app_context():
				from SIMS_Portal.alerts.utils import refresh_surge_alerts_latest
				from SIMS_Portal.main.utils import heartbeats
				refresh_surge_alerts_latest()
				heartbeats('run_surge_alert_refresh', 'https://uptime.betterstack.com/api/v1/heartbeat/7DQYkNR4cM96cKsY69xQah4k')
				
		@scheduler.task('cron', id='run_auto_badge_assigners', hour='17')
		def run_auto_badge_assigners():
			with scheduler.app.app_context():
				from SIMS_Portal.main.utils import auto_badge_assigner_big_wig, auto_badge_assigner_maiden_voyage, auto_badge_assigner_self_promoter, auto_badge_assigner_polyglot, auto_badge_assigner_autobiographer, auto_badge_assigner_world_traveler, auto_badge_assigner_edward_tufte, auto_badge_assigner_old_salt
				from SIMS_Portal.main.utils import heartbeats
				auto_badge_assigner_maiden_voyage()
				auto_badge_assigner_big_wig()
				auto_badge_assigner_self_promoter()
				auto_badge_assigner_polyglot()
				auto_badge_assigner_autobiographer()
				auto_badge_assigner_edward_tufte()
				auto_badge_assigner_world_traveler()
				auto_badge_assigner_old_salt()
				heartbeats('run_auto_badge_assigners', 'https://uptime.betterstack.com/api/v1/heartbeat/QWvz7BCEoLnpKeCFMFbK3d2a')
		
		# scheduler to automatically ping all associated members to active disasters to request availability
		# @scheduler.task('cron', id='request_availability', week='*', day_of_week='mon', hour=8)
		# def run_request_availability():
		# 	with scheduler.app.app_context():
		# 		from SIMS_Portal.availability.utils import request_availability_updates
		# 		from SIMS_Portal.main.utils import heartbeats
		# 		request_availability_updates()
		# 		heartbeats('request_availability', 'https://uptime.betterstack.com/api/v1/heartbeat/5WUSoe7kqnkKxQVLr1iKTFuq')
	
	from SIMS_Portal.main.routes import main
	from SIMS_Portal.assignments.routes import assignments
	from SIMS_Portal.emergencies.routes import emergencies
	from SIMS_Portal.portfolios.routes import portfolios
	from SIMS_Portal.users.routes import users
	from SIMS_Portal.stories.routes import stories
	from SIMS_Portal.learnings.routes import learnings
	from SIMS_Portal.reviews.routes import reviews
	from SIMS_Portal.alerts.routes import alerts
	from SIMS_Portal.errors.handlers import errors
	from SIMS_Portal.availability.routes import availability
	from SIMS_Portal.acronym.routes import acronym

	app.register_blueprint(main)
	app.register_blueprint(assignments)
	app.register_blueprint(emergencies)
	app.register_blueprint(portfolios)
	app.register_blueprint(users)
	app.register_blueprint(stories)
	app.register_blueprint(learnings)
	app.register_blueprint(reviews)
	app.register_blueprint(alerts)
	app.register_blueprint(errors)
	app.register_blueprint(availability)
	app.register_blueprint(acronym)
	
	from SIMS_Portal.models import User, Assignment, Emergency, Portfolio, NationalSociety, Story, Learning, Review, Alert, Badge, Availability, Documentation
	admin.add_view(AdminView(User, db.session))
	admin.add_view(AdminView(Assignment, db.session))
	admin.add_view(AdminView(Emergency, db.session))
	admin.add_view(AdminView(Portfolio, db.session))
	admin.add_view(AdminView(Story, db.session))
	admin.add_view(AdminView(Learning, db.session))
	admin.add_view(AdminView(Review, db.session))
	admin.add_view(AdminView(Alert, db.session))
	admin.add_view(AdminView(NationalSociety, db.session))
	admin.add_view(AdminView(Badge, db.session))
	admin.add_view(AdminView(Documentation, db.session))
	
	with app.app_context():
		inspector = inspect(db.engine)
		if not inspector.has_table("alembic_version") and inspector.has_table("user"):
			# for DBs created pre-migrations, skip initial migration
			flask_migrate.stamp(revision="17e65488bd11")
		flask_migrate.upgrade()
	
	# required to reinit logging after flask_migrate
	init_logging()
	
	return app