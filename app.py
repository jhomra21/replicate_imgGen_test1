from flask import Flask, request, render_template, redirect, url_for, flash
import replicate
import os
from collections import deque

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Set a secret key for flash messages

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Get the Replicate API token from the environment variables
replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
os.environ["REPLICATE_API_TOKEN"] = replicate_api_token

# Store the last 5 generated images
last_images = deque(maxlen=5)

def get_recent_predictions():
    client = replicate.Client(api_token=replicate_api_token)
    predictions = list(client.predictions.list())[:10]  # Fetch all and slice the first 10
    return [
        {
            "url": pred.output[0] if pred.output and isinstance(pred.output, list) else None,
            "prompt": pred.input.get("prompt", "No prompt available"),
            "status": pred.status
        }
        for pred in predictions
        if pred.status == "succeeded" and pred.output
    ]

@app.route("/", methods=["GET", "POST"])
def generate_image():
    image_url = None
    prompt = None
    if request.method == "POST":
        prompt = request.form["prompt"]
        if prompt:
            num_inference_steps = int(request.form["num_inference_steps"])
            guidance_scale = float(request.form["guidance_scale"])
            lora_scale = float(request.form["lora_scale"])
            
            try:
                output = replicate.run(
                    "lucataco/flux-dev-lora:a22c463f11808638ad5e2ebd582e07a469031f48dd567366fb4c6fdab91d614d",
                    input={
                        "prompt": prompt,
                        "hf_lora": "jhomra21/elsapon-LoRA",
                        "num_inference_steps": num_inference_steps,
                        "guidance_scale": guidance_scale,
                        "width": 512,
                        "height": 512,
                        "num_outputs": 1,
                        "output_quality": 80,
                        "lora_scale": lora_scale
                    }
                )
                image_url = output[0]
                
                # Add the new image to the last_images list
                last_images.appendleft({"url": image_url, "prompt": prompt})
            except replicate.exceptions.ModelError as e:
                if "NSFW" in str(e):
                    flash("NSFW content detected. Please try a different prompt.", "error")
                else:
                    flash(f"An error occurred: {str(e)}", "error")
                return redirect(url_for('generate_image'))
    
    recent_predictions = get_recent_predictions()
    return render_template("index.html", image_url=image_url, prompt=prompt, last_images=list(last_images), recent_predictions=recent_predictions)

if __name__ == "__main__":
    app.run(debug=True)