from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
import openai
import os
import pytesseract
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from PIL import Image
import psycopg2
from psycopg2 import sql
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()  # Load .env variables

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")  
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Check if OpenAI API key is set in environment
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it using: export OPENAI_API_KEY='your-api-key'")

# Strip any whitespace or newlines from the API key
openai.api_key = os.getenv("OPENAI_API_KEY").strip()

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")  # Retrieve DATABASE_URL from environment variables
    return psycopg2.connect(db_url)


def send_email(sender_email, recipient_email, subject, body):
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        app_password = os.getenv("SMTP_APP_PASSWORD")
        if app_password:
            app_password = app_password.replace('\xa0', ' ').strip()  # Remove non-breaking spaces and extra whitespace
        else:
            print("SMTP_APP_PASSWORD is not set or empty.")

        print(f"App password: {repr(app_password)}")

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject

        body_text = MIMEText(body, 'plain', 'utf-8')
        msg.attach(body_text)

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, app_password)
            server.send_message(msg)
            print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")




# -----------
# PAGE ROUTES
# -----------

# Home route
@app.route('/')
def home():
    # Redirect to the editor (decides based on login state)
    return redirect(url_for('editor'))

# Editor route (dynamic based on login state)
@app.route('/editor')
def editor():
    # Check if the user is logged in
    if 'user_email' in session:
        # Logged-in users get the personalized editor
        return render_template('rubricai_user.html')
    else:
        # Guests see the general rubric editor
        return render_template('rubricai.html')

# Sign up route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Check if the email already exists
            cur.execute("SELECT email_address FROM users WHERE email_address = %s", (email,))
            user = cur.fetchone()
            if user:
                flash("Email already exists. Please log in.", "error")
                return redirect(url_for('signup'))

            # Insert the new user
            cur.execute(
                "INSERT INTO users (email_address, password) VALUES (%s, %s)",
                (email, hashed_password)
            )
            conn.commit()
            cur.close()
            conn.close()

            flash("Signup successful! Please log in.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            flash("An error occurred. Please try again later.", "error")
            return redirect(url_for('signup'))

    return render_template('signup.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Check if the user exists
            cur.execute("SELECT password FROM users WHERE email_address = %s", (email,))
            user = cur.fetchone()
            cur.close()
            conn.close()

            if user and check_password_hash(user[0], password):
                session['user_email'] = email  # Store user email in session
                flash("Login successful!", "success")
                return redirect(url_for('editor'))
            else:
                flash("Invalid email or password. Please try again.", "error")
                return redirect(url_for('login'))
        except Exception as e:
            flash("An error occurred. Please try again later.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')

# User editor route (for direct access)
@app.route('/user_editor')
def user_editor():
    if 'user_email' not in session:
        flash("Please log in to access the editor.", "error")
        return redirect(url_for('login'))

    return render_template('rubricai_user.html')


@app.route('/account')
def account():
    if 'user_email' not in session:
        flash("Please log in to access your account.", "error")
        return redirect(url_for('login'))
    
    # Pass user data to the account template
    return render_template('account.html', email=session['user_email'])

# Route for Terms and Conditions page
@app.route('/terms-and-conditions')
def terms_and_conditions():
    return render_template('terms_and_conditions.html')

# Route for Privacy Policy page
@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

# Logout route
@app.route('/logout', methods=['POST'])
def logout():
    # Remove the user's email from the session
    session.pop('user_email', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('editor'))

# ---------------
# FORGOT PASSWORD 
# ---------------

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')  # Get the email from the form
        print(f"Email received: {email}")  # Debugging: Print the email received

        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Check if the email exists in the database
            cur.execute("SELECT email_address FROM users WHERE email_address = %s", (email,))
            user = cur.fetchone()
            print(f"Database query result for email '{email}': {user}")  # Debugging: Print the database query result

            if user:
                # Generate a secure token
                token = os.urandom(16).hex()
                print(f"Generated token: {token}")  # Debugging: Print the generated token

                # Insert the token into the password_resets table
                cur.execute(
                    """
                    INSERT INTO password_resets (email_address, token, expires_at) 
                    VALUES (%s, %s, NOW() + interval '1 hour')
                    """,
                    (email, token)
                )
                conn.commit()
                print("Token saved to database.")  # Debugging: Confirm token was saved to the database

                # Construct the reset link
                reset_link = f"https://adaptable-learning-production.up.railway.app/reset_password?token={token}"
                print(f"Generated reset link: {reset_link}")  # Debugging: Print the reset link

                # Send the reset link via email
                subject = "Password Reset Request"
                message = f"Click the link to reset your password: {reset_link}"
                sender_email = "careplanCTO@gmail.com"
                send_email(sender_email, email, subject, message)
                print("Reset link email sent.")  # Debugging: Confirm email was sent

                flash("A password reset link has been sent to your email.", "info")
            else:
                print(f"No account found for email: {email}")  # Debugging: Email not found in the database
                flash("No account found with that email address.", "error")

            cur.close()
            conn.close()

        except Exception as e:
            print(f"Error in forgot_password route: {e}")  # Debugging: Print the exception
            flash("An error occurred while processing your request. Please try again.", "error")

    return render_template('forgot_password.html')


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    # Extract the token from the query string
    token = request.args.get('token')
    print(f"[DEBUG] Token received: {token}")

    # Check if token is missing
    if not token:
        print("[DEBUG] Missing token")
        return "Access denied: Missing token.", 403

    # GET request: Render the reset_password form
    if request.method == 'GET':
        try:
            print("[DEBUG] Rendering reset_password.html...")
            return render_template('reset_password.html', token=token)
        except Exception as e:
            print(f"[DEBUG] Error rendering template: {e}")
            return f"Error rendering page: {e}", 500

    # POST request: Process the reset form
    elif request.method == 'POST':
        print("[DEBUG] Processing POST request for password reset...")
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or not confirm_password:
            print("[DEBUG] Missing password fields")
            return "Both password fields are required.", 400

        if new_password != confirm_password:
            print("[DEBUG] Passwords do not match")
            flash("Passwords do not match.", "error")
            return redirect(request.url)

        # Verify the token and update the password
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Validate the token in the database
            cur.execute(
                "SELECT email_address FROM password_resets WHERE token = %s AND expires_at > NOW()", 
                (token,)
            )
            user = cur.fetchone()
            print(f"[DEBUG] User fetched for token: {user}")

            if not user:
                print("[DEBUG] Invalid or expired token")
                return "Access denied: Invalid or expired token.", 403

            # Hash the new password and update the database
            hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
            cur.execute(
                "UPDATE users SET password = %s WHERE email_address = %s", 
                (hashed_password, user[0])
            )
            conn.commit()

            # Delete the used token
            cur.execute("DELETE FROM password_resets WHERE token = %s", (token,))
            conn.commit()

            print("[DEBUG] Password reset successful")
            flash("Your password has been reset successfully!", "success")
            return redirect(url_for('login'))

        except Exception as e:
            print(f"[DEBUG] Error during password reset: {e}")
            return f"An error occurred: {e}", 500

    # If somehow neither GET nor POST is handled, return a generic error
    print("[DEBUG] Unsupported request method")
    return "Method not allowed.", 405


# -----------------------
# RUBRIC AI FUNCTIONALITY
# -----------------------


# Helper: Extract text from an image using OCR
def extract_text_from_image(image_path):
    try:
        return pytesseract.image_to_string(Image.open(image_path))
    except Exception as e:
        return str(e)

# Helper: Extract text from a PDF (using PyMuPDF or OCR for images)
def extract_text_from_pdf(pdf_path):
    try:
        # Try extracting text directly from the PDF
        pdf_doc = fitz.open(pdf_path)
        pdf_text = ""
        for page in pdf_doc:
            pdf_text += page.get_text()
        pdf_doc.close()
        if pdf_text.strip():  # If text is found, return it
            return pdf_text

        # If no text is found, fallback to OCR
        images = convert_from_path(pdf_path)
        text = ""
        for image in images:
            text += pytesseract.image_to_string(image)
        return text
    except Exception as e:
        return str(e)

# Route: Handle file upload and text extraction
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

    # Determine file type and extract text
    if file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        text = extract_text_from_image(file_path)
    elif file.filename.lower().endswith('.pdf'):
        text = extract_text_from_pdf(file_path)
    else:
        return jsonify({"error": "Unsupported file format"}), 400

    # Remove the uploaded file after processing
    os.remove(file_path)

    return jsonify({"text": text}), 200

# Route: GPT processing (enhanced for rubric-based grading with percentage ranges)
@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        assignment = data.get("assignment", "")
        rubric = data.get("rubric", "")
        mode = data.get("mode", "Feedback")

        print(f"Mode recieved {mode}")

        if not assignment or not rubric:
            return jsonify({"error": "Both assignment and rubric are required."}), 400

        # Define the grade ranges
        grade_ranges = {
            "A": (86, 100),
            "B": (73, 85),
            "C+": (67, 72),
            "C": (60, 66),
            "C-": (50, 59),
        }

        # Updated prompt to generate a table format
        if mode == "Feedback":

            prompt = (
                f" Grade the following assignment based on the rubric provided. Provide feedback in an HTML table format."
                f" Each row should include: Criterion, Points Earned/Max Points, and Feedback. After the table, summarize with:"
                f" 'Total Points', 'Percentage', 'Grade', and 'General Feedback'."
                f" The General Feedback should be very detailed in what they did correct and how they can improve their work"
                f" Ensure the output is formatted cleanly as valid HTML without any additional markers or code block wrappers.\n\n"
                f" Use the following grading scale for the final grade:\n"
                f"- A: 86-100%\n"
                f"- B: 73-85%\n"
                f"- C+: 67-72%\n"
                f"- C: 60-66%\n"
                f"- C-: 50-59%\n\n"
                f"Rubric:\n{rubric}\n\n"
                f"Assignment:\n{assignment}\n\n"
                f"After you have all of this data, the format of your response should be as follows (example):\n\n"
                f"<table>\n"
                f"  <tr>\n"
                f"    <th>Criterion</th>\n"
                f"    <th>Points Earned/Max Points</th>\n"
                f"    <th>Feedback</th>\n"
                f"  </tr>\n"
                f"  <tr>\n"
                f"    <td>Criterion 1</td>\n"
                f"    <td>2/4</td>\n"
                f"    <td>Feedback about Criterion 1</td>\n"
                f"  </tr>\n"
                f"  <tr>\n"
                f"    <td>Criterion 2</td>\n"
                f"    <td>3/4</td>\n"
                f"    <td>Feedback about Criterion 2</td>\n"
                f"  </tr>\n"
                f"</table>\n"
                f"<p><strong>Total Points:</strong> 9/12</p>\n"
                f"<p><strong>Grade:</strong> B (75%)</p>\n"
                f"<p><strong>General Feedback:</strong> Feedback goes here</p>\n"
            )

        elif mode == "Perfect Score":
            print("Entering Perfect Score mode...")
            prompt = (
                f"Using the provided rubric, create a perfect-scoring version of the student's assignment."
                f" Your goal is to produce a response that meets 100% when graded against the rubric."
                f" Ensure you strictly eliminate all spelling and grammar mistakes."
                f" Begin by thoroughly analyzing the student's assignment to identify its structure, format, and style."
                f" Recognize and adapt to the specific layout and structure used in the student's assignment. This may include paragraphs, lists, sections, tables, diagrams, or other unique organizational formats."
                f" Match your perfected version's layout and structure precisely to the format identified in the student's assignment."
                f" Continuously reference the rubric to ensure all criteria are fully addressed and maximized to their highest potential."
                f" For all formats, use appropriate HTML elements to match the layout and structure accurately:\n"
                f"1. For structured text with sections:\n"
                f"   - Use `<h2>` for the main title.\n"
                f"   - Use `<h3>` for subsections or headings.\n"
                f"   - Use `<p>` for paragraphs.\n"
                f"2. For lists or enumerated items:\n"
                f"   - Use `<ul>` or `<ol>` with `<li>` for each item.\n"
                f"3. For tabular or comparative data:\n"
                f"   - Use `<table>` with `<tr>`, `<th>`, and `<td>` for rows and cells.\n"
                f"4. For specialized formats (e.g., dialogues, scripts, or structured Q&A):\n"
                f"   - Use a combination of tags like `<h3>`, `<p>`, `<ul>`, `<ol>`, `<li>`, `<code>`, or any other relevant elements to accurately represent the structure.\n"
                f"Ensure your perfected version aligns with the identified structure while maintaining professional and polished language and tone that feels natural to the student's style."
                f" Expand and enhance each part of the assignment to provide depth and specificity, ensuring every criterion in the rubric is satisfied for a perfect score."
                f" Exclude the student's original assignment and the rubric from your response."
                f" Provide only the perfected version of the assignment formatted cleanly in valid HTML."
                f" Ensure the output is formatted cleanly as valid HTML without any additional markers or code block wrappers.\n\n"
                f" Double-check your response against the rubric to confirm it meets all criteria for a score of 90% or higher.\n\n"
                f"Rubric:\n{rubric}\n\n"
                f"Student's Work:\n{assignment}\n"
            )



        else:
            return jsonify({"error": "Invalid mode specified."}), 400    
    

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a teacher grading assignments fairly based on rubrics. You are also a great writer who can create perfect scoring assignments based off of rubrics"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.8,
        )

        # Extract GPT output
        gpt_output = response.choices[0].message.content.strip()

        # Extract "Total Points" from GPT's response
        total_points_line = next(
            (line for line in gpt_output.split("\n") if line.startswith("Total Points:")), None
        )
        if total_points_line:
            total_points = total_points_line.split(":")[1].strip().split("/")
            points_earned = int(total_points[0])
            max_points = int(total_points[1])
            percentage = (points_earned / max_points) * 100

            # Determine letter grade based on percentage
            letter_grade = next(
                (grade for grade, (low, high) in grade_ranges.items() if low <= percentage <= high),
                "F"  # Default to F if no range matches
            )

            # Append calculated grade to the output
            gpt_output += f"<p>Grade: {letter_grade} ({percentage:.2f}%)</p>"

        return jsonify({"output": gpt_output}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



if __name__ == '__main__':
    port = int(os.getenv("PORT", 5001))  # Use Railway's PORT environment variable or default to 5001
    app.run(debug=True, host='0.0.0.0', port=port)

