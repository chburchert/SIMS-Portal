import ast
import json
import logging
from collections import Counter
from datetime import datetime

from flask import (
	request, render_template, url_for, flash, redirect,
	jsonify, Blueprint, current_app
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, func, and_
from sqlalchemy.orm import sessionmaker, aliased
from flask_login import (
	login_user, logout_user, current_user, login_required
)

from SIMS_Portal import db
from SIMS_Portal.config import Config
from SIMS_Portal.models import (
	User, Assignment, Emergency, NationalSociety,
	EmergencyType, Alert, Portfolio, Story,
	Learning, Review, Availability, Log
)
from SIMS_Portal.emergencies.forms import (
	NewEmergencyForm, UpdateEmergencyForm
)
from SIMS_Portal.emergencies.utils import (
	update_response_locations, update_active_response_locations,
	get_trello_tasks, emergency_availability_chart_data
)
from SIMS_Portal.assignments.utils import aggregate_availability
from SIMS_Portal.learnings.utils import request_learnings


emergencies = Blueprint('emergencies', __name__)

@emergencies.route('/emergencies/all')
@login_required
def view_all_emergencies():
	emergencies = db.session.query(Emergency, Assignment, NationalSociety, EmergencyType).join(Assignment, Assignment.id == Emergency.id, isouter=True).join(NationalSociety, NationalSociety.ns_go_id == Emergency.emergency_location_id, isouter=True).join(EmergencyType, EmergencyType.emergency_type_go_id == Emergency.emergency_type_id, isouter=True).filter(Emergency.emergency_status != "Removed").all()
	
	return render_template('emergencies_all.html', emergencies=emergencies)

@emergencies.route('/emergency/new', methods=['GET', 'POST'])
@login_required
def new_emergency():
	form = NewEmergencyForm()
	if form.validate_on_submit():
		emergency = Emergency(
			emergency_name=form.emergency_name.data, 
			emergency_location_id=form.emergency_location_id.data.ns_go_id, 
			emergency_type_id=form.emergency_type_id.data.emergency_type_go_id, 
			emergency_glide=form.emergency_glide.data, 
			emergency_go_id=form.emergency_go_id.data, 
			activation_details=form.activation_details.data, 
			slack_channel=form.slack_channel.data, 
			dropbox_url=form.dropbox_url.data, 
			trello_url=form.trello_url.data
		)
		db.session.add(emergency)
		db.session.commit()
		
		# run updates to csvs that hold data for visualizations
		update_response_locations()
		update_active_response_locations()
		
		log_message = f"[INFO] User {current_user.id} created emergency record: {emergency.emergency_name}."
		new_log = Log(message=log_message, user_id=current_user.id)
		db.session.add(new_log)
		db.session.commit()
		
		flash('New emergency successfully created.', 'success')
		
		return redirect(url_for('main.dashboard'))
	try:
		# try to get the latest emergencies from the GO API
		latest_emergencies = Emergency.get_latest_go_emergencies()
	except:
		latest_emergencies = [{'dis_id': 0, 'dis_name': 'GO API CALL FAILED'}]
		current_app.logger.error('The GO API failed to return recent emergencies for the New Emergency form.')
	return render_template('create_emergency.html', title='Create New Emergency', form=form, latest_emergencies=latest_emergencies)

@emergencies.route('/emergency/<int:id>', methods=['GET', 'POST'])
@login_required
def view_emergency(id):
	# get user info for various filtering
	user_info = db.session.query(User).filter(User.id == current_user.id).first()
	
	# build availability chart
	week_dates, frequency_count = emergency_availability_chart_data(id)
	if frequency_count == [0, 0, 0, 0, 0, 0, 0]:
		kill_chart = True
	else:
		kill_chart = False
	
	# get IDs of all this emergency's sims remote coordinators
	sims_co_ids = db.session.query(User, Assignment, Emergency).join(Assignment, Assignment.user_id == User.id).join(Emergency, Emergency.id == Assignment.emergency_id).filter(Emergency.id == id, Assignment.role == 'SIMS Remote Coordinator').all()

	# loop through IDs to see if current user is one of the coordinators
	sims_co_list = []
	for coordinator in sims_co_ids:
		sims_co_list.append(coordinator.User.id)
	if current_user.id in sims_co_list:
		user_is_sims_co = True
	else:
		user_is_sims_co = False
	
	# build availability query parameters
	emergency_id = id
	user_id = current_user.id
	today = datetime.today().year
	week_number = datetime.today().isocalendar()[1]
	timeframe = f"{today}-{week_number}"
	
	# build availability query
	availability_subquery = db.session.query(func.max(Availability.created_at)).filter(
		Availability.emergency_id == emergency_id,
		Availability.user_id == user_id,
		Availability.timeframe == timeframe 
	).scalar_subquery()
	availability_query = db.session.query(
		Availability.id, 
		Availability.emergency_id,
		Availability.created_at,
		Availability.dates
	).filter(
		Availability.emergency_id == emergency_id,
		Availability.user_id == user_id,
		Availability.timeframe == timeframe,
		Availability.created_at == availability_subquery
	)
	availability_results = availability_query.first()
	
	# check for products that need to be approved
	pending_products = db.session.query(Portfolio).filter(Portfolio.emergency_id == id, Portfolio.product_status == 'Pending Approval').all()
	
	# get simscos
	sims_cos = db.session.query(Assignment, Emergency, User, NationalSociety).join(Emergency, Emergency.id==Assignment.emergency_id).join(User, User.id==Assignment.user_id).join(NationalSociety, NationalSociety.ns_go_id==User.ns_id).filter(Emergency.id==id, Assignment.assignment_status=='Active', Assignment.role=='SIMS Remote Coordinator').order_by(User.firstname).all()
	
	# get deployed IM roles
	deployed_im = db.session.query(Assignment, Emergency, User, NationalSociety).\
	join(Emergency, Emergency.id == Assignment.emergency_id).\
	join(User, User.id == Assignment.user_id).\
	join(NationalSociety, NationalSociety.ns_go_id == User.ns_id).\
	filter(
		Emergency.id == id,
		Assignment.assignment_status == 'Active',
		or_(
			Assignment.role == 'Information Management Coordinator',
			Assignment.role == 'Information Analyst',
			Assignment.role == 'Primary Data Collection Officer',
			Assignment.role == 'Mapping and Visualization Officer'
		)
	).order_by(User.firstname).all()
	
	# get remote supporters
	deployments = db.session.query(Assignment, Emergency, User, NationalSociety).join(Emergency, Emergency.id==Assignment.emergency_id).join(User, User.id==Assignment.user_id).join(NationalSociety, NationalSociety.ns_go_id==User.ns_id).filter(Emergency.id==id, Assignment.assignment_status=='Active', Assignment.role=='Remote IM Support').order_by(User.firstname).all()
	
	# trigger quick action box if user has active remote assignment
	user_ids = [user.id for assignment, emergency, user, national_society in deployments]
	quick_action = current_user.id in user_ids
	if quick_action:
		quick_action_id = db.session.query(Assignment).filter(
			and_(
				Assignment.emergency_id == emergency_id,
				Assignment.assignment_status == 'Active',
				Assignment.user_id == current_user.id,
				Assignment.role == 'Remote IM Support'
			)
		).first()
	else:
		quick_action_id = 0
	
	# get emergency information
	emergency_info = db.session.query(Emergency, EmergencyType, NationalSociety).join(EmergencyType, EmergencyType.emergency_type_go_id == Emergency.emergency_type_id).join(NationalSociety, NationalSociety.ns_go_id == Emergency.emergency_location_id).filter(Emergency.id == id).first()
	
	# count approved products for emergency
	emergency_portfolio_size = len(db.session.query(Portfolio, Emergency).join(Emergency, Emergency.id == Portfolio.emergency_id).filter(Emergency.id == id, Portfolio.product_status == 'Approved').all())
	
	# get 3 portfolio products for emergency
	emergency_portfolio = db.session.query(Portfolio, Emergency).join(Emergency, Emergency.id == Portfolio.emergency_id).filter(Emergency.id == id, Portfolio.product_status == 'Approved').limit(3).all()
	
	# check if story already exists for button filtering
	check_for_story = db.session.query(Story, Emergency).join(Emergency, Emergency.id == Story.emergency_id).filter(Story.emergency_id == id).first()

	# count how many learnings have been logged by remote supporters
	learning_count = db.session.query(Learning, Assignment, Emergency).join(Assignment, Assignment.id == Learning.assignment_id).join(Emergency, Emergency.id == Assignment.emergency_id).filter(Emergency.id == id).count()

	# get the average learning scores across all operations
	learning_data = db.engine.execute('SELECT AVG(overall_score) as "Overall", AVG(got_support) as "Support", AVG(internal_resource) as "Internal Resources", AVG(external_resource) as "External Resources", AVG(clear_tasks) as "Task Clarity", AVG(field_communication) as "Field Communication", AVG(clear_deadlines) as "Deadlines", AVG(coordination_tools) as "Coordination Tools" FROM learning JOIN assignment ON assignment.id = learning.assignment_id JOIN emergency ON emergency.id = assignment.emergency_id WHERE emergency.id = {}'.format(id))
	
	# build chart's x and y
	data_dict_learnings = [x._asdict() for x in learning_data]
	learning_keys = []
	learning_values = []
	for k, v in data_dict_learnings[0].items():
		learning_keys.append(k)
		learning_values.append(v)
	
	try:
		learning_values = [round(float(val), 2) for val in learning_values]
	except:
		learning_values = [0]
	
	avg_learning_data = db.engine.execute('SELECT AVG(overall_score) as "Overall", AVG(got_support) as "Support", AVG(internal_resource) as "Internal Resources", AVG(external_resource) as "External Resources", AVG(clear_tasks) as "Task Clarity", AVG(field_communication) as "Field Communication", AVG(clear_deadlines) as "Deadlines", AVG(coordination_tools) as "Coordination Tools" FROM learning')
	
	# convert avg learnings data to dict and parse into keys and values
	data_dict_avg_learnings = [x._asdict() for x in avg_learning_data]
	avg_learning_keys = []
	avg_learning_values = []
	for k, v in data_dict_avg_learnings[0].items():
		avg_learning_keys.append(k)
		avg_learning_values.append(v)
	
	try:
		avg_learning_values = [round(float(val), 2) for val in avg_learning_values]	
	except:
		avg_learning_values = [0]
	
	existing_reviews = db.session.query(Review).filter(Review.emergency_id == id).all()
	
	deployment_history_count = db.session.query(func.count(func.distinct(Assignment.user_id))).filter(Assignment.emergency_id == id).filter(Assignment.assignment_status == 'Active', Assignment.role == 'Remote IM Support').scalar()
	
	try:
		# check for trello tasks
		to_do_trello = get_trello_tasks(emergency_info.Emergency.trello_url)
		count_cards = len(to_do_trello)
	except:
		to_do_trello = None
		count_cards = 0
	
	today = datetime.today()
	current_weekday = today.weekday()
	year, week_number, _ = today.isocalendar()
	current_week_num = f"{year}-{week_number:02d}"
	next_week = week_number + 1
	next_week_num = f"{year}-{next_week:02d}"
	days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
	
	# current week supporters
	available_supporters_current_week = db.session.query(User, Availability).join(Availability, User.id == Availability.user_id).filter(
		Availability.emergency_id == id,
		Availability.timeframe == current_week_num
	)
	available_supporter_current_week_list = available_supporters_current_week.all()
	
	# next week supporters
	available_supporters_next_week = db.session.query(User, Availability).join(Availability, User.id == Availability.user_id).filter(
		Availability.emergency_id == id,
		Availability.timeframe == next_week_num 
	)
	available_supporter_next_week_list = available_supporters_next_week.all()
	
	def extract_day_of_week(date_string):
		try:
			date_obj = datetime.strptime(date_string, '%A, %B %d')
			return date_obj.strftime('%A')
		except ValueError:
			return date_string
	
	# iterate through the results and format the dates
	for member in available_supporter_current_week_list:
		availability = member.Availability
		dates = availability.dates[1:-1].split(', ')
		formatted_dates = [extract_day_of_week(date.strip("'")) for date in dates]
		availability.dates = ', '.join(formatted_dates)
		availability.dates = availability.dates.replace(',','').split()
		
		available_days_of_week = []
		for date in availability.dates:
			if date in days_of_week:
				available_days_of_week.append(date)
		availability.dates = available_days_of_week
	
	return render_template(
		'emergency.html', 
		title='Emergency View', 
		emergency_info=emergency_info, 
		deployments=deployments, 
		emergency_portfolio=emergency_portfolio, 
		check_for_story=check_for_story, 
		learning_data=learning_data, 
		learning_keys=learning_keys, 
		learning_values=learning_values, 
		learning_count=learning_count, 
		avg_learning_keys=avg_learning_keys, 
		avg_learning_values=avg_learning_values, 
		deployment_history_count=deployment_history_count, 
		user_is_sims_co=user_is_sims_co, 
		pending_products=pending_products, 
		emergency_portfolio_size=emergency_portfolio_size,  
		existing_reviews=existing_reviews, 
		to_do_trello=to_do_trello, 
		count_cards=count_cards, 
		current_weekday=current_weekday, 
		availability_results=availability_results,
		user_info=user_info, 
		sims_cos=sims_cos,
		deployed_im=deployed_im,
		week_dates=week_dates, 
		frequency_count=frequency_count,
		kill_chart=kill_chart,
		quick_action=quick_action,
		quick_action_id=quick_action_id,
		available_supporter_current_week_list=available_supporter_current_week_list,
		available_supporter_next_week_list=available_supporter_next_week_list
	)

@emergencies.route('/emergency/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_emergency(id):
	form = UpdateEmergencyForm()
	emergency_info = db.session.query(Emergency).filter(Emergency.id == id).first()
	if form.validate_on_submit():
		emergency_info.emergency_name = form.emergency_name.data
		try: 
			emergency_info.emergency_location_id = form.emergency_location_id.data.ns_go_id
		except:
			pass
		try:
			selected_id = form.emergency_type_id.data.emergency_type_go_id
			db.session.query(Emergency).filter(Emergency.id==id).update({'emergency_type_id':selected_id})
		except:
			pass
		try: 
			emergency_info.emergency_go_id = form.emergency_go_id.data
		except:
			pass
		emergency_info.emergency_glide = form.emergency_glide.data
		emergency_info.activation_details = form.activation_details.data
		emergency_info.slack_channel = form.slack_channel.data
		emergency_info.dropbox_url = form.dropbox_url.data
		emergency_info.trello_url = form.trello_url.data
		db.session.commit()
		flash('Emergency record updated!', 'success')
		
		log_message = f"[INFO] User {current_user.id} edited emergency {emergency_info.emergency_name}."
		new_log = Log(message=log_message, user_id=current_user.id)
		db.session.add(new_log)
		db.session.commit()
		
		return redirect(url_for('emergencies.view_emergency', id=id))
	elif request.method == 'GET':
		form.emergency_name.data = emergency_info.emergency_name
		form.emergency_glide.data = emergency_info.emergency_glide
		form.emergency_go_id.data = emergency_info.emergency_go_id
		form.activation_details.data = emergency_info.activation_details
		form.slack_channel.data = emergency_info.slack_channel
		form.dropbox_url.data = emergency_info.dropbox_url
		form.trello_url.data = emergency_info.trello_url
	return render_template('emergency_edit.html', form=form, emergency_info=emergency_info)

@emergencies.route('/emergency/gantt/<int:id>')
@login_required
def emergency_gantt(id):
	emergency_info = db.session.query(Emergency).filter(Emergency.id == id).first()
	
	assignments = db.session.query(Assignment, Emergency, User).join(Emergency, Emergency.id == Assignment.emergency_id).join(User, User.id == Assignment.user_id).filter(Emergency.id == id, Assignment.assignment_status == 'Active', Assignment.role == 'SIMS Remote Coordinator').with_entities(Assignment.start_date, Assignment.end_date, User.fullname, Assignment.role).order_by(Assignment.start_date.asc()).all()
	
	start_end_dates = []
	for dates in assignments:
		start_end_dates.append([dates.start_date.strftime('%Y-%m-%d'), dates.end_date.strftime('%Y-%m-%d')])
	
	member_labels = []
	for member in assignments:
		member_labels.append(member.fullname)
	
	if start_end_dates:
		min_date = min(start_end_dates)
		min_date = min_date[0]
	else: 
		min_date = '2000-01-01'
	
	return render_template('emergency_gantt.html', start_end_dates=start_end_dates, member_labels=member_labels, min_date=min_date, emergency_info=emergency_info)

@emergencies.route('/emergency/closeout/<int:id>')
@login_required
def closeout_emergency(id):
	if current_user.is_admin == 1:
		try:
			db.session.query(Emergency).filter(Emergency.id==id).update({'emergency_status':'Closed'})
			db.session.commit()
			
			# update map on dashboard
			update_active_response_locations()
			
			# request learnings from remote supporters
			request_learnings(id)
			
			current_app.logger.info("Emergency-{} has been closed out.".format(id))
			flash("Emergency closed out.", 'success')
		except:
			flash("Error closing emergency. Check that the emergency ID exists.")
		return redirect(url_for('main.dashboard'))
	else:
		list_of_admins = db.session.query(User).filter(User.is_admin==True).all()
		return render_template('errors/403.html', list_of_admins=list_of_admins), 403

@emergencies.route('/emergency/delete/<int:id>')
@login_required
def delete_emergency(id):
	if current_user.is_admin == 1:
		try:
			db.session.query(Emergency).filter(Emergency.id==id).update({'emergency_status':'Removed'})
			db.session.commit()
			update_active_response_locations()
			flash("Emergency deleted.", 'success')
			
			emergency_info = db.session.query(Emergency).filter(Emergency.id==id).first()
			log_message = f"[WARNING] User {current_user.id} deleted emergency {emergency_info.emergency_name}."
			new_log = Log(message=log_message, user_id=current_user.id)
			db.session.add(new_log)
			db.session.commit()
			
		except:
			flash("Error deleting emergency. Check that the emergency ID exists.")
		return redirect(url_for('main.dashboard'))
	else:
		list_of_admins = db.session.query(User).filter(User.is_admin==True).all()
		return render_template('errors/403.html', list_of_admins=list_of_admins), 403

@emergencies.route('/api/emergencies', methods=['GET'])
def api_get_emergencies():
	status_param = request.args.get('status')
	emergency_id_param = request.args.get('emergency_id')
	iso3_param = request.args.get('iso3')

	# subquery establishes custom column for assignment_counter
	subquery = (
		db.session.query(
			Assignment.emergency_id,
			func.count(Assignment.id).label("assignment_count")
		)
		.group_by(Assignment.emergency_id)
		.subquery()
	)

	# set aliases for the joined tables to distinguish
	emergency_alias = aliased(Emergency)
	emergency_type_alias = aliased(EmergencyType)
	national_society_alias = aliased(NationalSociety)

	query = (
		db.session.query(
			emergency_alias,
			emergency_type_alias.emergency_type_name,
			national_society_alias.iso3,
			national_society_alias.country_name,
			subquery.c.assignment_count
		)
		.outerjoin(subquery, emergency_alias.id == subquery.c.emergency_id)
		.join(emergency_type_alias, emergency_type_alias.id == emergency_alias.emergency_type_id)
		.join(national_society_alias, national_society_alias.ns_go_id == emergency_alias.emergency_location_id)
		.group_by(emergency_alias.id, emergency_type_alias.emergency_type_name, national_society_alias.iso3, national_society_alias.country_name, subquery.c.assignment_count)
	)

	if status_param:
		query = query.filter(emergency_alias.emergency_status == status_param)

	if emergency_id_param:
		query = query.filter(emergency_alias.emergency_go_id == emergency_id_param)

	if iso3_param:
		query = query.filter(national_society_alias.iso3 == iso3_param)

	emergencies = query.all()

	result = []
	for emergency, emergency_type_name, iso3, country_name, assignment_count in emergencies:
		result.append({
			'emergency_name': emergency.emergency_name,
			'go_emergency_id': emergency.emergency_go_id,
			'status': emergency.emergency_status,
			'emergency_type': emergency_type_name,
			'iso3': iso3,
			'country_name': country_name,
			'slack_channel': emergency.slack_channel,
			'activation_details': emergency.activation_details,
			'glide': emergency.emergency_glide,
			'assignment_count': assignment_count or 0  # set count to 0 if none
		})

	return jsonify(result)