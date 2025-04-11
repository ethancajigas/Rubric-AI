# Rubric-AI

## Setup Instructions

1. Clone the repository and navigate to it:
   ```bash
   git clone https://github.com/yourusername/Rubric-AI.git
   cd Rubric-AI
   ```

2. Create and activate a virtual environment:
   ```bash
   # On macOS/Linux
   python -m venv venv
   source venv/bin/activate

   # On Windows
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your OpenAI API key:
   ```bash
   export OPENAI_API_KEY='your-api-key'
   ```
   Replace 'your-api-key' with your actual OpenAI API key. You can get one from [OpenAI's website](https://platform.openai.com/api-keys).

5. Run the application:
   ```bash
   python rubricai.py
   ```

Note: You'll need to set the OPENAI_API_KEY environment variable each time you open a new terminal. To make it permanent, you can add the export command to your shell's configuration file (e.g., ~/.bashrc, ~/.zshrc).

To deactivate the virtual environment when you're done:
```bash
deactivate
```
