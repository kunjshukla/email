import streamlit as st
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64
import pickle
import requests

# Load environment variables from .env file
load_dotenv()

# Gmail API setup
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose'
]
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'

def get_gmail_service():
    """Get Gmail API service instance."""
    creds = None
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            
        if not os.path.exists(CREDENTIALS_FILE):
            st.error("""
            Gmail API credentials not found. Please follow these steps:
            1. Go to Google Cloud Console (https://console.cloud.google.com)
            2. Enable Gmail API
            3. Create OAuth 2.0 credentials
            4. Download the credentials and save as 'credentials.json'
            5. Place the file in the project directory
            """)
            return None
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES,
                redirect_uri='http://localhost:8080'
            )
            
            creds = flow.run_local_server(
                port=8080,
                prompt='consent',
                access_type='offline',
                authorization_prompt_message='Please authorize the application to send emails'
            )
            
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
            
            return build('gmail', 'v1', credentials=creds)
            
        except Exception as flow_error:
            st.error(f"""
            Error during authentication flow: {str(flow_error)}
            
            Please ensure:
            1. You've enabled Gmail API in Google Cloud Console
            2. You've added the correct scopes in OAuth consent screen
            3. Your credentials.json is valid and up to date
            4. You're using a Google account with access
            """)
            return None
    
    except Exception as e:
        st.error(f"Unexpected error during Gmail authentication: {str(e)}")
        return None

def send_email(service, to_email, subject, html_content):
    """Send an email using Gmail API."""
    message = MIMEMultipart('alternative')
    message['to'] = to_email
    message['subject'] = subject
    
    html_part = MIMEText(html_content, 'html')
    message.attach(html_part)
    
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    try:
        message = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        return True, "Email sent successfully!"
    except Exception as e:
        return False, f"Error sending email: {str(e)}"

# Define the path to the templates folder
TEMPLATES_DIR = "TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "Templates")"

def get_html_files(directory):
    """Returns a list of HTML files in the specified directory."""
    files = []
    if os.path.exists(directory) and os.path.isdir(directory):
        for f in os.listdir(directory):
            if f.endswith(".html"):
                files.append(f)
    return files

def main():
    st.set_page_config(layout="wide")
    st.title("HTML Email Template Viewer & Editor")

    # --- Gemini API Key from Environment Variable ---
    api_key = os.getenv("GEMINI_API_KEY")
    
    # --- Gmail Configuration ---
    st.sidebar.subheader("Gmail Configuration")
    
    if not os.path.exists(CREDENTIALS_FILE):
        st.sidebar.warning("""
        Gmail API setup required:
        1. Go to Google Cloud Console
        2. Enable Gmail API
        3. Create OAuth 2.0 credentials
        4. Download as 'credentials.json'
        5. Place in project directory
        """)
    
    if st.sidebar.button("Authenticate Gmail"):
        service = get_gmail_service()
        if service:
            st.session_state.gmail_service = service
            st.sidebar.success("Gmail authentication successful! You can now send emails.")
        else:
            st.sidebar.error("""
            Gmail authentication failed. Please check:
            1. credentials.json is present
            2. Gmail API is enabled
            3. OAuth consent screen is configured
            4. You're using a Google account with access
            """)

    if "gmail_service" not in st.session_state:
        st.session_state.gmail_service = None

    if not api_key:
        st.sidebar.error("Gemini API key not found in environment variables. Please set GEMINI_API_KEY in the .env file.")
        genai.configure(api_key=None)
    else:
        genai.configure(api_key=api_key)

    # Initialize session state variables if they don't exist
    if "selected_file_content" not in st.session_state:
        st.session_state.selected_file_content = ""
    if "displayed_html_content" not in st.session_state:
        st.session_state.displayed_html_content = ""
    if "selected_file_name" not in st.session_state:
        st.session_state.selected_file_name = None
    if "ai_prompt_input" not in st.session_state:
        st.session_state.ai_prompt_input = ""

    # --- HTML Viewer Section ---
    st.header("HTML Template Viewer")
    html_files = get_html_files(TEMPLATES_DIR)

    if not html_files:
        st.warning(f"No HTML files found in the '{TEMPLATES_DIR}' folder.")
        st.info(f"Please add some .html files to the '{TEMPLATES_DIR}' folder and refresh the page.")
        if not os.path.exists(TEMPLATES_DIR):
            st.info(f"The '{TEMPLATES_DIR}' folder does not exist.")
    else:
        selected_file_option = st.selectbox(
            "Select an HTML template:", 
            html_files, 
            key="html_selector",
            index=html_files.index(st.session_state.selected_file_name) if st.session_state.selected_file_name in html_files else 0
        )

        if selected_file_option and (st.session_state.selected_file_name != selected_file_option or not st.session_state.selected_file_content):
            st.session_state.selected_file_name = selected_file_option
            file_path = os.path.join(TEMPLATES_DIR, st.session_state.selected_file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                st.session_state.selected_file_content = content
                st.session_state.displayed_html_content = content
            except Exception as e:
                st.error(f"Error reading file {st.session_state.selected_file_name}: {e}")
                st.session_state.selected_file_content = ""
                st.session_state.displayed_html_content = ""

    if st.session_state.displayed_html_content:
        st.subheader(f"Preview: {st.session_state.selected_file_name}")
        st.components.v1.html(st.session_state.displayed_html_content, height=600, scrolling=True)
        
        st.markdown("---")
        st.subheader("Send Email")
        
        col1, col2 = st.columns(2)
        with col1:
            recipient_email = st.text_input("Recipient Email Address")
        with col2:
            email_subject = st.text_input("Email Subject", 
                                        value=f"Email from {st.session_state.selected_file_name}")
        
        if st.button("Send Email"):
            if not recipient_email:
                st.error("Please enter a recipient email address.")
            elif not email_subject:
                st.error("Please enter an email subject.")
            else:
                n8n_webhook_url = "https://kantom-luke12.app.n8n.cloud/webhook/send-html-email"
                payload = {
                    "to": recipient_email,
                    "subject": email_subject,
                    "body": st.session_state.displayed_html_content
                }
                try:
                    response = requests.post(n8n_webhook_url, json=payload, timeout=10)
                    if response.status_code == 200:
                        st.success("Email successfully sent via n8n workflow!")
                    else:
                        st.error(f"Failed to send email. n8n responded with status code {response.status_code}: {response.text}")
                except Exception as e:
                    st.error(f"Error sending request to n8n webhook: {e}")

    elif st.session_state.selected_file_name:
        st.subheader(f"Preview: {st.session_state.selected_file_name}")
        st.warning("No content to display for this file. It might be empty or an error occurred.")

    st.markdown("---")
    st.header("AI Content Editor")

    st.session_state.ai_prompt_input = st.text_area(
        "Describe the changes you want for the selected HTML template:",
        value=st.session_state.ai_prompt_input,
        height=150,
        key="ai_prompt_text_area_widget"
    )

    if st.button("Generate AI Changes", key="generate_ai_changes_button"):
        prompt = st.session_state.ai_prompt_input.strip()
        if not prompt:
            st.warning("Please enter a description of the changes you want.")
        elif not api_key:
            st.error("Gemini API key not set in environment variables. Please set GEMINI_API_KEY in the .env file.")
        elif not st.session_state.selected_file_content:
            st.warning("No HTML template selected or content is empty. Please select a template to edit.")
        else:
            try:
                system_prompt_html_edit = (
                    "You are an expert HTML editor. Your task is to modify only the textual content "
                    "within the existing HTML structure based on the user's request. "
                    "Preserve all HTML tags, attributes, and the overall layout. "
                    "Do not add new HTML elements unless explicitly asked. Do not remove existing elements unless asked. "
                    "Only output the complete, raw, modified HTML content. No explanations, no apologies, just the HTML."
                )
                user_request_for_html = (
                    f"Given the following HTML template:\n\n```html\n{st.session_state.selected_file_content}\n```\n\n" 
                    f"Please apply the following changes: {prompt}\n\n" 
                    f"Remember to only output the full, raw, modified HTML content."
                )

                with st.spinner("AI is updating the HTML content..."):
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(
                        f"{system_prompt_html_edit}\n\n{user_request_for_html}",
                        generation_config={
                            "temperature": 0.2,
                            "max_output_tokens": 8192
                        }
                    )
                    modified_html = response.text.strip()

                if modified_html.startswith("```html\n") and modified_html.endswith("\n```"):
                    modified_html = modified_html[len("```html\n"):-len("\n```")]
                elif modified_html.startswith("```html") and modified_html.endswith("```"):
                    modified_html = modified_html[len("```html"):-len("```")]
                elif modified_html.startswith("```") and modified_html.endswith("```"):
                    modified_html = modified_html[len("```"):-len("```")]
                modified_html = modified_html.strip()

                if not (modified_html.startswith("<") and modified_html.endswith(">")):
                    error_message = f"AI response did not seem to be valid HTML. Got: {modified_html[:200]}..."
                    st.error(error_message)
                else:
                    st.session_state.displayed_html_content = modified_html
                    try:
                        original_filename = st.session_state.selected_file_name
                        if original_filename:
                            base, ext = os.path.splitext(original_filename)
                            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                            new_filename = f"{base}_ai_edited_{timestamp_str}{ext}"
                            new_filepath = os.path.join(TEMPLATES_DIR, new_filename)
                            with open(new_filepath, "w", encoding="utf-8") as f_new:
                                f_new.write(modified_html)
                            st.success(f"Saved AI-modified template as: {new_filename}")
                    except Exception as save_e:
                        st.error(f"Error saving the modified HTML copy: {save_e}")

                    st.session_state.ai_prompt_input = ""
                    st.rerun()

            except Exception as e:
                error_msg = f"Error calling Gemini API: {e}"
                st.error(error_msg)
                st.rerun()

if __name__ == "__main__":
    main()
