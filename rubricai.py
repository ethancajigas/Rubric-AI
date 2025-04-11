from flask import Flask, request, jsonify, render_template
import openai
import os
import pytesseract
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from PIL import Image
from dotenv import load_dotenv

load_dotenv()  # Load .env variables

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Check if OpenAI API key is set in environment
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it using: export OPENAI_API_KEY='your-api-key'")

# Strip any whitespace or newlines from the API key
openai.api_key = os.getenv("OPENAI_API_KEY").strip()

# -----------
# PAGE ROUTES
# -----------

# Home route
@app.route('/')
def home():
    return render_template('rubricai.html')

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

        print(f"Mode received {mode}")

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

