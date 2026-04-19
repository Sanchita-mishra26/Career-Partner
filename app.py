import os
import re
from datetime import timedelta
from functools import wraps
from io import BytesIO

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import inspect, or_, text
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from PyPDF2 import PdfReader
from docx import Document

from db import Base, SessionLocal, engine
from models import Conversation, ResumeAnalysis, User


def create_app() -> Flask:
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    allowed_extensions = {"pdf", "docx", "txt"}

    role_skill_map = {
        "data scientist": [
            "python", "sql", "statistics", "machine learning", "pandas", "numpy", "scikit-learn",
            "data visualization", "a/b testing", "feature engineering",
        ],
        "machine learning engineer": [
            "python", "sql", "machine learning", "deep learning", "pytorch", "tensorflow", "docker",
            "mlops", "api development", "cloud",
        ],
        "backend developer": [
            "python", "flask", "sql", "api development", "testing", "docker", "git", "system design",
        ],
        "frontend developer": [
            "html", "css", "javascript", "react", "typescript", "responsive design", "ui/ux", "testing",
        ],
        "full stack developer": [
            "html", "css", "javascript", "react", "python", "flask", "sql", "api development", "git",
            "docker",
        ],
    }

    def is_allowed_file(file_name: str) -> bool:
        if "." not in file_name:
            return False
        extension = file_name.rsplit(".", 1)[1].lower()
        return extension in allowed_extensions

    def read_resume_content(file_name: str, file_bytes: bytes) -> str:
        extension = file_name.rsplit(".", 1)[1].lower()

        if extension == "txt":
            return file_bytes.decode("utf-8", errors="ignore")

        if extension == "pdf":
            reader = PdfReader(BytesIO(file_bytes))
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            return "\n".join(pages)

        if extension == "docx":
            document = Document(BytesIO(file_bytes))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)

        return ""

    def normalize_word(word: str) -> str:
        return re.sub(r"\s+", " ", word.strip().lower())

    def infer_core_skills(resume_text: str) -> set[str]:
        known_skills = {
            "python", "sql", "machine learning", "deep learning", "statistics", "pandas", "numpy",
            "scikit-learn", "tensorflow", "pytorch", "flask", "django", "fastapi", "docker", "kubernetes",
            "aws", "gcp", "azure", "api development", "system design", "git", "data visualization",
            "power bi", "tableau", "a/b testing", "feature engineering", "html", "css", "javascript",
            "react", "typescript", "node.js", "ci/cd", "mlops", "nlp", "computer vision", "communication",
        }

        lower_text = resume_text.lower()
        found = set()
        for skill in known_skills:
            if skill in lower_text:
                found.add(skill)
        return found

    def build_fallback_resume_analysis(resume_text: str, role: str) -> str:
        normalized_role = normalize_word(role)
        selected_skills = role_skill_map.get(normalized_role)
        if not selected_skills:
            selected_skills = [
                "python", "sql", "communication", "problem solving", "project portfolio", "interview prep",
            ]

        resume_skills = infer_core_skills(resume_text)
        required_skills = [normalize_word(skill) for skill in selected_skills]

        matched = [skill for skill in required_skills if skill in resume_skills]
        missing = [skill for skill in required_skills if skill not in resume_skills]
        coverage = int((len(matched) / max(len(required_skills), 1)) * 100)

        action_steps = [
            "Tailor your resume summary directly to the target role and include measurable outcomes.",
            "Add 2-3 project bullets that prove impact using metrics (latency, revenue, accuracy, or time saved).",
            "Strengthen weak skill areas using one focused project per missing skill cluster.",
            "Prepare interview stories using STAR format for technical and teamwork scenarios.",
        ]

        analysis_lines = [
            f"Target Role: {role}",
            "",
            "Overall Match:",
            f"- Estimated role-fit coverage: {coverage}%",
            "",
            "Required Skillset:",
        ]
        analysis_lines.extend([f"- {skill.title()}" for skill in required_skills])

        analysis_lines.append("")
        analysis_lines.append("Your Evident Skills:")
        if matched:
            analysis_lines.extend([f"- {skill.title()}" for skill in matched])
        else:
            analysis_lines.append("- No strong skill matches detected from resume text.")

        analysis_lines.append("")
        analysis_lines.append("Missing Skills / Gaps:")
        if missing:
            analysis_lines.extend([f"- {skill.title()}" for skill in missing])
        else:
            analysis_lines.append("- No critical gaps detected for this role baseline.")

        analysis_lines.append("")
        analysis_lines.append("Priority Action Plan:")
        analysis_lines.extend([f"- {step}" for step in action_steps])

        analysis_lines.append("")
        analysis_lines.append("Suggested 30-Day Plan:")
        analysis_lines.append("- Week 1: Resume rewrite + keyword optimization for ATS.")
        analysis_lines.append("- Week 2: Build one role-aligned portfolio project.")
        analysis_lines.append("- Week 3: Add missing tooling skills and publish project write-up.")
        analysis_lines.append("- Week 4: Mock interviews + targeted applications.")

        return "\n".join(analysis_lines)

    def get_ai_client_and_model() -> tuple[object | None, str | None]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None, None

        try:
            from openai import OpenAI

            if api_key.startswith("sk-or-v1"):
                return OpenAI(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                ), "openai/gpt-4o-mini"

            return OpenAI(api_key=api_key), "gpt-4.1-mini"
        except Exception:
            return None, None

    def build_resume_analysis(resume_text: str, role: str) -> str:
        client, model = get_ai_client_and_model()
        if client is None or model is None:
            return build_fallback_resume_analysis(resume_text, role)

        try:
            completion = client.chat.completions.create(
                model=model,
                temperature=0.3,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert career coach and ATS resume reviewer. "
                            "Return concise, practical guidance with clear sections."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Analyze this resume for the target role and provide:\n"
                            "1) role fit summary\n"
                            "2) required skillset\n"
                            "3) missing skills\n"
                            "4) resume improvement bullets\n"
                            "5) interview prep roadmap\n"
                            "6) 30-day upskilling plan\n\n"
                            f"Target role: {role}\n\nResume:\n{resume_text[:12000]}"
                        ),
                    },
                ],
            )
            return completion.choices[0].message.content.strip()
        except Exception:
            return build_fallback_resume_analysis(resume_text, role)

    def build_ai_response(prompt: str) -> str:
        clean_prompt = prompt.strip()
        client, model = get_ai_client_and_model()

        if client is not None and model is not None:
            try:
                completion = client.chat.completions.create(
                    model=model,
                    temperature=0.4,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are AI Career Copilot. Give concise, actionable career guidance "
                                "for resumes, job search, interviews, and skill growth."
                            ),
                        },
                        {"role": "user", "content": clean_prompt},
                    ],
                )
                message = completion.choices[0].message.content
                if message and message.strip():
                    return message.strip()
            except Exception:
                pass

        return (
            "Thanks for your question. Here is a starter direction: "
            f"{clean_prompt}.\n\n"
            "Next step: refine this prompt with role, context, and expected output format."
        )

    def ensure_schema_compatibility() -> None:
        inspector = inspect(engine)
        if "users" not in inspector.get_table_names():
            return

        existing_columns = {column["name"] for column in inspector.get_columns("users")}
        migration_sql = []

        if "full_name" not in existing_columns:
            migration_sql.append(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(120) NOT NULL DEFAULT ''"
            )
        if "created_at" not in existing_columns:
            migration_sql.append(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at DATETIME NULL"
            )

        if not migration_sql:
            return

        with engine.begin() as connection:
            for statement in migration_sql:
                connection.execute(text(statement))

            if "created_at" not in existing_columns:
                connection.execute(text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
                connection.execute(
                    text("ALTER TABLE users MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
                )

    ensure_schema_compatibility()
    Base.metadata.create_all(bind=engine)

    @app.before_request
    def load_logged_in_user() -> None:
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
            return

        db = SessionLocal()
        try:
            g.user = db.query(User).filter(User.id == user_id).first()
        finally:
            db.close()

    def login_required(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if g.user is None:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            return view_func(*args, **kwargs)

        return wrapped_view

    @app.route("/")
    def home():
        if g.user:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not full_name or len(full_name) < 2:
                flash("Please enter your full name.", "danger")
                return render_template("signup.html")

            if "@" not in email or "." not in email:
                flash("Please provide a valid email address.", "danger")
                return render_template("signup.html")

            if len(username) < 3 or " " in username:
                flash("Username must be at least 3 characters and contain no spaces.", "danger")
                return render_template("signup.html")

            if len(password) < 8:
                flash("Password must be at least 8 characters long.", "danger")
                return render_template("signup.html")

            if password != confirm_password:
                flash("Password and confirm password do not match.", "danger")
                return render_template("signup.html")

            db = SessionLocal()
            try:
                existing_user = (
                    db.query(User)
                    .filter(or_(User.email == email, User.username == username))
                    .first()
                )
                if existing_user:
                    flash("Email or username already exists. Please use a different one.", "danger")
                    return render_template("signup.html")

                user = User(
                    full_name=full_name,
                    email=email,
                    username=username,
                    password_hash=generate_password_hash(password),
                )
                db.add(user)
                db.commit()

                flash("Account created successfully. Please log in.", "success")
                return redirect(url_for("login"))
            except IntegrityError:
                db.rollback()
                flash("Email or username already exists. Please use a different one.", "danger")
            finally:
                db.close()

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            identity = request.form.get("identity", "").strip().lower()
            password = request.form.get("password", "")
            remember_me = request.form.get("remember_me") == "on"

            if not identity or not password:
                flash("Please enter both username/email and password.", "danger")
                return render_template("login.html")

            db = SessionLocal()
            try:
                user = (
                    db.query(User)
                    .filter(or_(User.email == identity, User.username == identity))
                    .first()
                )
            finally:
                db.close()

            if user is None or not check_password_hash(user.password_hash, password):
                flash("Invalid credentials. Please try again.", "danger")
                return render_template("login.html")

            session.clear()
            session["user_id"] = user.id
            session.permanent = remember_me

            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.route("/logout", methods=["POST", "GET"])
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out successfully.", "info")
        return redirect(url_for("login"))

    @app.route("/forgot-password")
    def forgot_password():
        return render_template("forgot_password.html")

    @app.route("/dashboard", methods=["GET"])
    @login_required
    def dashboard():
        db = SessionLocal()
        try:
            recent_conversations = (
                db.query(Conversation)
                .filter(Conversation.user_id == g.user.id)
                .order_by(Conversation.created_at.desc())
                .limit(5)
                .all()
            )
            recent_resume_analyses = (
                db.query(ResumeAnalysis)
                .filter(ResumeAnalysis.user_id == g.user.id)
                .order_by(ResumeAnalysis.created_at.desc())
                .limit(5)
                .all()
            )
        finally:
            db.close()

        return render_template(
            "dashboard.html",
            recent_conversations=recent_conversations,
            recent_resume_analyses=recent_resume_analyses,
        )

    @app.route("/resume/analyze", methods=["POST"])
    @login_required
    def analyze_resume():
        target_role = request.form.get("target_role", "").strip()
        resume_file = request.files.get("resume_file")

        if not target_role:
            flash("Please enter the role you are applying for.", "danger")
            return redirect(url_for("dashboard"))

        if resume_file is None or not resume_file.filename:
            flash("Please upload a resume file.", "danger")
            return redirect(url_for("dashboard"))

        file_name = secure_filename(resume_file.filename)
        if not file_name or not is_allowed_file(file_name):
            flash("Unsupported file type. Upload PDF, DOCX, or TXT.", "danger")
            return redirect(url_for("dashboard"))

        file_bytes = resume_file.read()
        if not file_bytes:
            flash("Uploaded file is empty.", "danger")
            return redirect(url_for("dashboard"))

        try:
            resume_text = read_resume_content(file_name, file_bytes).strip()
        except Exception:
            flash("Could not read this file. Please upload a valid PDF, DOCX, or TXT resume.", "danger")
            return redirect(url_for("dashboard"))

        if len(resume_text) < 60:
            flash("Resume content is too short to analyze. Please upload a complete resume.", "danger")
            return redirect(url_for("dashboard"))

        analysis_text = build_resume_analysis(resume_text=resume_text, role=target_role)

        db = SessionLocal()
        try:
            entry = ResumeAnalysis(
                user_id=g.user.id,
                file_name=file_name,
                target_role=target_role,
                resume_text=resume_text[:30000],
                analysis_text=analysis_text,
            )
            db.add(entry)
            db.commit()
            flash("Resume analyzed successfully.", "success")
            return redirect(url_for("view_resume_analysis", analysis_id=entry.id))
        finally:
            db.close()

    @app.route("/resume/<int:analysis_id>", methods=["GET"])
    @login_required
    def view_resume_analysis(analysis_id: int):
        db = SessionLocal()
        try:
            analysis = (
                db.query(ResumeAnalysis)
                .filter(ResumeAnalysis.id == analysis_id, ResumeAnalysis.user_id == g.user.id)
                .first()
            )
        finally:
            db.close()

        if analysis is None:
            flash("Resume analysis not found.", "warning")
            return redirect(url_for("dashboard"))

        return render_template("resume_analysis_detail.html", analysis=analysis)

    @app.route("/resume/<int:analysis_id>/delete", methods=["POST"])
    @login_required
    def delete_resume_analysis(analysis_id: int):
        db = SessionLocal()
        try:
            analysis = (
                db.query(ResumeAnalysis)
                .filter(ResumeAnalysis.id == analysis_id, ResumeAnalysis.user_id == g.user.id)
                .first()
            )
            if analysis is None:
                flash("Resume analysis not found.", "warning")
                return redirect(url_for("dashboard"))

            db.delete(analysis)
            db.commit()
            flash("Resume analysis deleted.", "info")
        finally:
            db.close()

        return redirect(url_for("dashboard"))

    @app.route("/conversation/new", methods=["POST"])
    @login_required
    def new_conversation():
        prompt = request.form.get("prompt", "").strip()
        if not prompt:
            flash("Please enter a prompt before submitting.", "danger")
            return redirect(url_for("dashboard"))

        response = build_ai_response(prompt)
        db = SessionLocal()
        try:
            entry = Conversation(user_id=g.user.id, prompt=prompt, response=response)
            db.add(entry)
            db.commit()
            flash("Conversation saved.", "success")
            return redirect(url_for("view_history_item", conversation_id=entry.id))
        finally:
            db.close()

    @app.route("/history", methods=["GET"])
    @login_required
    def history():
        search = request.args.get("q", "").strip()
        db = SessionLocal()
        try:
            query = db.query(Conversation).filter(Conversation.user_id == g.user.id)
            if search:
                like_term = f"%{search}%"
                query = query.filter(
                    or_(Conversation.prompt.ilike(like_term), Conversation.response.ilike(like_term))
                )

            conversations = query.order_by(Conversation.created_at.desc()).all()
        finally:
            db.close()

        return render_template("history.html", conversations=conversations, search=search)

    @app.route("/history/<int:conversation_id>", methods=["GET"])
    @login_required
    def view_history_item(conversation_id: int):
        db = SessionLocal()
        try:
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == g.user.id,
                )
                .first()
            )
        finally:
            db.close()

        if conversation is None:
            flash("Conversation not found.", "warning")
            return redirect(url_for("history"))

        return render_template("conversation_detail.html", conversation=conversation)

    @app.route("/history/<int:conversation_id>/delete", methods=["POST"])
    @login_required
    def delete_history_item(conversation_id: int):
        db = SessionLocal()
        try:
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == g.user.id,
                )
                .first()
            )
            if conversation is None:
                flash("Conversation not found.", "warning")
                return redirect(url_for("history"))

            db.delete(conversation)
            db.commit()
            flash("Conversation deleted.", "info")
        finally:
            db.close()

        return redirect(url_for("history"))

    @app.route("/history/clear", methods=["POST"])
    @login_required
    def clear_history():
        db = SessionLocal()
        try:
            db.query(Conversation).filter(Conversation.user_id == g.user.id).delete()
            db.commit()
            flash("All conversation history has been cleared.", "info")
        finally:
            db.close()

        return redirect(url_for("history"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
