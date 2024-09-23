from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session
from flask_session import Session
import replicate
import os
from collections import deque
from werkzeug.utils import secure_filename
import zipfile
from datetime import datetime, timezone
import base64
import io
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime
import requests
from celery import Celery
import hmac
import hashlib
from flask_cors import CORS
from models import db, Users, Models  # Import models
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:5173"}}, supports_credentials=True, allow_headers=["Content-Type", "Authorization"])
app.secret_key = os.urandom(24)  # Set a secret key for flash messages
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SECURE'] = True  # For HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'  # Required for cross-origin requests
Session(app)
WEBHOOK_SECRET = "whsec_V1ch24sYuN1xO2SqW4jX2EP8/NyCOASA"
# Configure SQLAlchemy
db_connection = os.getenv("POSTGRES_DB")
app.config['SQLALCHEMY_DATABASE_URI'] = db_connection
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)  # Initialize SQLAlchemy with the app

# Configure Celery
app.config['CELERY_BROKER_URL'] = 'redis://172.20.116.49:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://172.20.116.49:6379/0'
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Get the Replicate API token from the environment variables
replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
hf_token = os.getenv("HF_TOKEN")

# lemon squeezy
LEMON_SQUEEZY_API_KEY = os.getenv("LEMON_TEST_SQUEEZY_API_KEY")
LEMON_SQUEEZY_STORE_ID = os.getenv("LEMON_SQUEEZY_STORE_ID")
SAMPLE_PRODUCT_ID = os.getenv("SAMPLE_PRODUCT_ID")

# Add these variables at the top of the file, after the imports
CURRENT_MODEL = "Flux-Dev"
CURRENT_LORA = "also working on this..."

# controlling img zip
UPLOAD_FOLDER = 'input_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

#TODO:   will be changed later and loaded from usr table in the database
TRIGGER_WORD = "ramon"
NEW_MODEL_NAME = "jhonra121/ramon-lora-20240910-154729:dd117084cca97542e09f6a2a458295054b4afb0b97417db068c20ff573997fc9"

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# get most recent predictions using replicate api, then limit to 10
def get_recent_predictions():
    client = replicate.Client(api_token=replicate_api_token)
    predictions = list(client.predictions.list())[:20]  # Fetch all and slice the first 10
    return [
        {
            "url": pred.output[0] if pred.output and isinstance(pred.output, list) else None,
            "prompt": pred.input.get("prompt", "No prompt available"),
            "status": pred.status
        }
        for pred in predictions
        if pred.status == "succeeded" and pred.output
    ]

# simple AUTH
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Replicate-Signature')
    if not signature:
        return jsonify({"error": "No signature provided"}), 400

    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        request.data,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return jsonify({"error": "Invalid signature"}), 400

    data = request.json
    # Process the webhook data
    print(f"Received valid webhook: {data}")
    return '', 200

#new route ("/")
@app.route("/")
def index():
    return jsonify({"message": "Welcome to the API"})

# main route
@app.route("/generate", methods=["POST"])
@login_required
def generate_image():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    prompt = data.get("prompt")
    model_id = data.get("modelId")
    num_inference_steps = data.get("num_inference_steps", 22)
    guidance_scale = data.get("guidance_scale", 3.5)
    lora_scale = data.get("lora_scale", 0.8)

    if not prompt or not model_id:
        return jsonify({"error": "Prompt and modelId are required"}), 400

    try:
        model = db.session.get(Models, model_id)
        if not model:
            return jsonify({"error": "Model not found"}), 404

        version = replicate.models.get(model.name).versions.get(model.model_version)

        output = replicate.run(
            version,
            input={
                "prompt": f"{prompt}; professional photo and lens",
                "model": "dev",
                "lora_scale": lora_scale,
                "num_outputs": 1,
                "aspect_ratio": "1:1",
                "output_format": "webp",
                "guidance_scale": guidance_scale,
                "output_quality": 90,
                "num_inference_steps": num_inference_steps
            }
        )
        output = list(output)  # Convert iterator to list
        image_url = output[0] if output else None
        
        if not image_url:
            return jsonify({"error": "Failed to generate image"}), 500

        return jsonify({
            "image_url": image_url,
            "predict_time": None,  # We're not fetching these metrics anymore
            "total_time": None,
            "guidance_scale": guidance_scale,
            "num_inference_steps": num_inference_steps,
            "lora_scale": lora_scale
        })
    except Exception as e:
        app.logger.error(f"Error in generate_image: {str(e)}")
        return jsonify({"error": str(e)}), 500

def get_latest_trigger_word():
    # Implement this function to retrieve the latest trigger word
    # For now, we'll return a default value
    return TRIGGER_WORD

@app.route('/training_processing/<training_id>')
@login_required
def training_processing(training_id):
    try:
        training = replicate.trainings.get(training_id)
        if training is None:
            return jsonify({"error": "Training not found"}), 404
        elapsed_str = "00:00:00"
        # Calculate elapsed time
        start_time = datetime.fromisoformat(training.created_at.replace('Z', '+00:00')) if training.created_at else None
        if start_time:
            current_time = datetime.now(timezone.utc)
            elapsed_time = current_time - start_time
            # Convert to hours, minutes, seconds
            hours, remainder = divmod(int(elapsed_time.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        if training.status == 'failed':
            session.pop('trainings', None)
            session.modified = True
            flash(f'Training failed for model: {training.id}', 'error')
            return jsonify({"training_id": training.id, "status": training.status, "elapsed_time": elapsed_str})
        elif training.status == 'canceled':
            session.pop('trainings', None)
            session.modified = True
            flash(f'Training canceled for model: {training.id}', 'warning')
            return jsonify({"training_id": training.id, "status": training.status, "elapsed_time": elapsed_str})
        
        elif training.status == 'succeeded':
            user_id = session.get('user_id')
            if training.output and 'version' in training.output:
                version = training.output['version']
                print("version:", version)
            model = replicate.models.get(version)
            latest_version = model.latest_version
            if latest_version:
                print("latest_version:", latest_version)
                Models.insert_model(user_id=user_id, name=model.id, description='', model_version=latest_version.id, status="succeeded")
           
            else:
                print("No version available for the model")
            session.pop('trainings', None)
            session.modified = True
            flash(f'Training finished successfully! Model: {training.id}', 'success')
            return jsonify({
                "id": training.id,
                "status": 'succeeded'
            }),200
        else:
            return jsonify({
                "id": training.id,
                "status": training.status,
                "elapsed_time": elapsed_str,
                "created_at": training.created_at or None,
                "cancel_url": getattr(training.urls, 'cancel', None) if training.status in ['starting', 'processing'] else None
            })
    except Exception as e:
        return jsonify({"error": str(e), "training_id": training_id}), 400

@celery.task
def async_train(model_id, training_input):
    training = replicate.trainings.create(**training_input)
    return {
        'id': training.id,
        'status': training.status,
        'created_at': training.created_at if training.created_at else None,
        'completed_at': training.completed_at if training.completed_at else None,
        'error': str(training.error) if training.error else None,
        'input': training.input,
        'output': training.output,
        'logs': training.logs,

        'urls': {
            'get': training.urls['get'],
            'cancel': training.urls['cancel']
        } if training.urls else None
    }

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_images():
    user_id = session.get('user_id')
    if request.method == 'POST':
        if 'files[]' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        files = request.files.getlist('files[]')
        
        if not files or files[0].filename == '':
            flash('No selected files', 'error')
            return redirect(request.url)
        
        trigger_word = request.form.get('trigger_word')
        if not trigger_word:
            flash('Trigger word is required', 'error')
            return redirect(request.url)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zipf:
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    zipf.writestr(filename, file.read())
        
        # Reset the buffer position to the beginning
        zip_buffer.seek(0)
        # Convert zip_buffer to base64 and create a data URI
        zip_base64 = base64.b64encode(zip_buffer.getvalue()).decode('utf-8')
        zip_uri = f"data:application/zip;base64,{zip_base64}"

        try:
            # Create a new model on Replicate
            new_model = replicate.models.create(
                owner="juanmartbulnes",
                name=f"{trigger_word}-lora-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
                visibility="private",
                hardware="gpu-a100-large"
            )
            # Create the training using Replicate API
            training_input = {
                "destination": f"juanmartbulnes/{new_model.name}",
                "version": "ostris/flux-dev-lora-trainer:d995297071a44dcb72244e6c19462111649ec86a9646c32df56daa7f14801944",
                "input": {
                    "steps": 800,
                    "lora_rank": 16,
                    "optimizer": "adamw8bit",
                    "batch_size": 1,
                    "resolution": "512,768,1024",
                    "autocaption": False,
                    "input_images": zip_uri,
                    "trigger_word": trigger_word,
                    "learning_rate": 0.0004,
                },
                # 'webhook': url_for('webhook', _external=True)
            }

            task = async_train.delay(new_model.id, training_input)

            # add training to session
            user_id = session.get('user_id')
            new_training = Models.insert_model(user_id=user_id, name=new_model.name, description='', model_version='', status="succeeded")
            #return json with training info and add to session
            return jsonify({
                "task_id": task.id,
                "model_id": new_model.id,
                "model_name": new_model.name,
                "status": "pending",
            }), 202

        except Exception as e:
            flash(f'Error creating model or starting training: {str(e)}', 'error')
            return jsonify({"status": "error", "message": str(e)})
    
    return render_template('upload.html')

@app.route('/training_status/<task_id>')
@login_required
def check_training_status(task_id):
    task = async_train.AsyncResult(task_id)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Task is pending...'
        }
    elif task.state == 'SUCCESS':
        training_data = task.result
        response = {
            'state': task.state,
            'status': training_data['status'],
            'id': training_data['id'],
            'created_at': training_data['created_at'],
            'completed_at': training_data['completed_at'],
            'error': training_data['error']
        }
    else:
        response = {
            'state': task.state,
            'status': str(task.info),
        }
    return jsonify(response)

# -------- user stuff --------
@app.route('/allusers')
@login_required
def all_users():
    users = Users.query.all()
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')
    return render_template('allusers.html', users=users, is_logged_in=is_logged_in, user_id=user_id)

# Add this after your other configurations
app.config['JWT_SECRET_KEY'] = 'your-secret-key'  # Change this to a secure random key
app.config['JWT_TOKEN_LOCATION'] = ['headers']
jwt = JWTManager(app)

# Add this new route for token verification
@app.route('/api/verify-token', methods=['GET', 'OPTIONS'])
def verify_token():
    if request.method == 'OPTIONS':
        return '', 200
    
    @jwt_required()
    def get():
        current_user_id = get_jwt_identity()
        user = Users.query.get(current_user_id)
        if user:
            return jsonify({
                "id": user.id,
                "username": user.username,
            }), 200
        return jsonify({"msg": "User not found"}), 404
    
    return get()

# Modify your login route to return a JWT token
@app.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    user = Users.get_user_by_username(username)
    if user and user.password_hash and user.check_password(password):
        access_token = create_access_token(identity=user.id)
        models = user.get_models()
        serialized_models = [
            {
                'id': model.id,
                'name': model.name,
                'model_version': model.model_version,
                'status': model.status
            } for model in models
        ]
        
        return jsonify({
            "message": "Logged in successfully",
            "user_id": user.id,
            "username": user.username,
            "models": serialized_models,
            "access_token": access_token
        })
    else:
        return jsonify({"error": "Invalid username or password"}), 401

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return redirect(url_for('signup'))
        
        existing_user = Users.get_user_by_email(email)
        if existing_user:
            flash('Email already registered.', 'error')
            return redirect(url_for('signup'))
        
        # Create new user
        new_user = Users.create_user(username=username, email=email, password=password)
        if new_user:
            flash('Account created successfully. Please log in.', 'success')
            return redirect(url_for('login'))
    
    return render_template('signup.html')

# lemon squeezy sample product
def get_variant_id(product_id):
    headers = {
        'Accept': 'application/vnd.api+json',
        'Authorization': f'Bearer {LEMON_SQUEEZY_API_KEY}'
    }
    try:
        product_response = requests.get(f'https://api.lemonsqueezy.com/v1/products/{product_id}', headers=headers)
        product_data = product_response.json()
        
        if 'data' in product_data and 'relationships' in product_data['data']:
            variants_url = product_data['data']['relationships']['variants']['links']['related']
            
            # Now, fetch the variants
            variants_response = requests.get(variants_url, headers=headers)
            variants_data = variants_response.json()
            
            if 'data' in variants_data and variants_data['data']:
                # Return the ID of the first variant
                return variants_data['data'][0]['id']
        
        print("No variants found for the product")
    except Exception as e:
        print(f"Error in get_variant_id: {str(e)}")
    return None

@app.route('/buy-sample')
@login_required
def buy_sample():
    return render_template('buy_sample.html', 
                           store_id=LEMON_SQUEEZY_STORE_ID, 
                           product_id=SAMPLE_PRODUCT_ID)

@app.route('/create-checkout', methods=['POST'])
@login_required
def create_checkout():
    headers = {
        'Accept': 'application/vnd.api+json',
        'Content-Type': 'application/vnd.api+json',
        'Authorization': f'Bearer {LEMON_SQUEEZY_API_KEY}'
    }
    
    store_id = LEMON_SQUEEZY_STORE_ID
    product_id = SAMPLE_PRODUCT_ID  # This should be the actual product ID
    print(f"Store ID: {store_id}")
    print(f"Product ID: {product_id}")

    variant_id = get_variant_id(product_id)
    print(f"Variant ID: {variant_id}")

    if not store_id or not variant_id:
        print(f"Store ID or Variant ID is missing")
        return jsonify({'error': 'Store ID or Variant ID is missing'}), 400

    payload = {
    "data": {
        "type": "checkouts",
        "relationships": {
            "store": {
                "data": {
                    "type": "stores",
                    "id": str(store_id)
                }
            },
            "variant": {
                "data": {
                    "type": "variants",
                    "id": str(variant_id)
                }
            }
        }
    }
}
    
    response = requests.post('https://api.lemonsqueezy.com/v1/checkouts', 
                             json=payload, headers=headers)
    print(f"Checkout Status Code: {response.status_code}")
    print(f"Checkout Response: {response.text}")

    if response.status_code == 201:
        checkout_url = response.json()['data']['attributes']['url']
        return jsonify({'checkout_url': checkout_url})
    else:
        print(f"Error response: {response.text}")
        return jsonify({'error': 'Failed to create checkout'}), 400
    

@app.route('/api/data', methods=['GET', 'OPTIONS'])
@jwt_required()
def get_data():
    if request.method == 'OPTIONS':
        return '', 200
    current_user_id = get_jwt_identity()
    user = Users.query.get(current_user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    models = Models.query.filter_by(user_id=current_user_id).all()
    models_data = [
        {
            'id': model.id,
            'user_id': model.user_id,
            'name': model.name,
            'description': model.description,
            'created_at': str(model.created_at),
            'updated_at': str(model.updated_at),
            'model_version': model.model_version,
            'status': model.status
        }
        for model in models
    ]
    return jsonify(models_data)

@app.route('/logout', methods=['POST', 'OPTIONS'])
@jwt_required()
def logout():
    if request.method == 'OPTIONS':
        return '', 200
    # Perform any server-side logout operations here
    return jsonify({"message": "Logged out successfully"}), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error
    app.logger.error(f"Unhandled exception: {str(e)}")
    # Return JSON instead of HTML for HTTP errors
    return jsonify({"error": "An unexpected error occurred"}), 500



if __name__ == "__main__":
    with app.app_context():
        db.create_all()
      
    app.run(debug=True)
