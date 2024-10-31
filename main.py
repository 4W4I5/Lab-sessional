"""
1) NavBar and Buttons
    i) each page must have a nav bar w links to 3 pages i.e. Home page, Form(Create portfolio) and Portfolio page (View portfolio)
    ii) Forward and backward nav buttons must be present on all pages
2) Pages
    i) Home page: Must have a welcome message
        - Create ans show a portfolio button with the message Create and showcase your professional portfolio
        - It should have a background image
        - There should be a prominent button labelled "Create and showcase your professional portfolio"
        - The button should be styled using Bootstrap to stand out, and it should link to the form page (/create-portoflio)
    ii) Form page: Must have a form to create a portfolio
        - Input fields: First Name, Last Name, Email, Phone Number, Profile Picture (Upload Image), Short Bio, Skills or Expertise i.e. Python + Web Dev, Link to any online profiles i.e. LinkedIn + Github
        - Submit button: Submit
        - Use SQLModel as the DB
    iii) Portfolio page: Must show the portfolio
        - Use bootstrap for styling
        - Use any given template to display the portfolio in a good way
    iv) Portfolio Download Page: Must have a button to download the portfolio
"""

import os
import random
import shutil
import string
import time
from typing import Annotated

from bcrypt import gensalt, hashpw
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from pydantic import BaseModel, EmailStr
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlmodel import Field, Session, SQLModel, create_engine, select
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse, PlainTextResponse

# Directory to store uploaded profile pictures
UPLOAD_DIR = "./static/uploads/"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# CSRF Configuration
class CsrfSettings(BaseModel):
    secret_key: str = os.environ.get(
        "SECRET_KEY", "secretkey"
    )  # Replace with a secure secret key
    cookie_same_site: str = "none"


# Data class for portfolios
class Portfolio(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    Fname: str = Field(min_length=1, max_length=50)
    Lname: str = Field(min_length=1, max_length=50)
    Email: str = Field(index=True)
    Phone: str = Field(
        default=None, regex=r"^\+?1?\d{9,15}$"
    )  # Applying regex validation with Field
    ProfilePicture: str = Field(default=None)
    Bio: str = Field(max_length=500)
    Skills: str = Field(max_length=250)
    LinkedIn: str = Field(default=None)
    GitHub: str = Field(default=None)


@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()


# DB Setup
sqlite_file_name = "./portfolio_database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

app = FastAPI()


# Mount the 'static' directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="./templates")


# Middleware for session management
app.add_middleware(SessionMiddleware, secret_key="i212764")


@app.exception_handler(CsrfProtectError)
def csrf_protect_exception_handler(request: Request, exc: CsrfProtectError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/csrftoken/")
async def get_csrf_token(csrf_protect: CsrfProtect = Depends()):
    # response = JSONResponse(status_code=200, content={"csrf_token": "cookie"})
    # csrf_protect.set_csrf_cookie(csrf_protect.generate_csrf_tokens(response))
    csrf_token, _ = csrf_protect.generate_csrf_tokens()
    return {"csrf_token": csrf_token}


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# Routes for portfolio creation, viewing, and downloading


@app.get("/")
async def home_page(
    request: Request, session: SessionDep, csrf_protect: CsrfProtect = Depends()
):
    """
    Home page route that displays a list of all portfolios with View and Download buttons.
    """
    try:
        csrf_token, signed_token = csrf_protect.generate_csrf_tokens()
    except CsrfProtectError as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.message})

    portfolios = session.exec(select(Portfolio)).all()

    response = templates.TemplateResponse(
        "index.html",
        {"request": request, "csrf_token": csrf_token, "portfolios": portfolios},
    )
    csrf_protect.set_csrf_cookie(signed_token, response)
    return response


@app.get("/create-portfolio/")
async def create_portfolio_form(
    request: Request, csrf_protect: CsrfProtect = Depends()
):
    """
    Portfolio creation form route.
    """
    csrf_token, signed_token = csrf_protect.generate_csrf_tokens()
    response = templates.TemplateResponse(
        "create_portfolio.html", {"request": request, "csrf_token": csrf_token}
    )
    csrf_protect.set_csrf_cookie(signed_token, response)
    return response


@app.post("/submit-portfolio/")
async def submit_portfolio(
    request: Request,
    session: SessionDep,
    csrf_protect: CsrfProtect = Depends(),
    fname: str = Form(...),
    lname: str = Form(...),
    email: EmailStr = Form(...),
    phone: str = Form(...),
    bio: str = Form(...),
    skills: str = Form(...),
    linkedin: str = Form(...),
    github: str = Form(...),
    profile_picture: UploadFile = File(...),
):
    """
    Handle form submission for portfolio creation.
    """

    try:
        await csrf_protect.validate_csrf(request)
        print("CSRF token is valid")
    except CsrfProtectError as e:
        print(f"Error: {e}")
        return JSONResponse(status_code=e.status_code, content={"detail": e.message})
    # Save the uploaded profile picture to the uploads directory
    picture_filename = f"{fname}_{lname}_{profile_picture.filename}"
    picture_path = os.path.join(UPLOAD_DIR, picture_filename)
    print(
        f"Got: \n\tFname={fname}\n\tLname={lname}\n\tEmail={email}\n\tPhone={phone}\n\tBio={bio}\n\tSkills={skills}\n\tLinkedIn={linkedin}\n\tGitHub={github}\n\tProfilePicture={picture_path}"
    )

    # Save the file on the server
    with open(picture_path, "wb") as buffer:
        shutil.copyfileobj(profile_picture.file, buffer)

    # Store portfolio details, including the profile picture path
    new_portfolio = Portfolio(
        Fname=fname,
        Lname=lname,
        Email=email,
        Phone=phone,
        Bio=bio,
        Skills=skills,
        LinkedIn=linkedin,
        GitHub=github,
        ProfilePicture=picture_path,  # Save path to the image in the database
    )

    session.add(new_portfolio)
    session.commit()
    session.refresh(new_portfolio)

    response = RedirectResponse(url=f"/portfolio/{new_portfolio.id}", status_code=302)
    csrf_protect.unset_csrf_cookie(response)
    return response


@app.get("/portfolio/{portfolio_id}")
async def view_portfolio(
    portfolio_id: int,
    request: Request,
    session: SessionDep,
    csrf_protect: CsrfProtect = Depends(),
):
    """
    View a portfolio by its ID and display View/Download buttons.
    """
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    response = templates.TemplateResponse(
        "portfolio.html", {"request": request, "portfolio": portfolio}
    )
    return response


@app.get("/download-portfolio/{portfolio_id}")
async def download_portfolio(portfolio_id: int, session: SessionDep):
    """
    Download a portfolio as a professionally styled PDF.
    """
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Define file path
    pdf_filename = f"portfolio_{portfolio_id}.pdf"
    pdf_path = os.path.join("static", "downloads", pdf_filename)

    # Ensure the downloads directory exists
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    # Create a PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []

    # Set up styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontSize=22,
        alignment=TA_CENTER,
        spaceAfter=20,
        textColor=colors.HexColor("#2E86C1"),
    )
    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Heading2"],
        fontSize=16,
        spaceBefore=10,
        spaceAfter=10,
        textColor=colors.HexColor("#1F618D"),
    )
    body_style = styles["BodyText"]
    body_style.spaceBefore = 6

    # Add portfolio title
    elements.append(
        Paragraph(f"Portfolio of {portfolio.Fname} {portfolio.Lname}", title_style)
    )
    elements.append(Spacer(1, 0.5 * inch))

    # Profile Picture (if exists)
    if portfolio.ProfilePicture:
        image_path = os.path.join(UPLOAD_DIR, portfolio.ProfilePicture.split("/")[-1])
        try:
            img = Image(image_path, 2 * inch, 2 * inch)
            img.hAlign = "CENTER"
            elements.append(img)
            elements.append(Spacer(1, 0.2 * inch))
        except Exception as e:
            print(f"Error loading image: {e}")

    # Personal Information Section
    personal_info = [
        ["Full Name:", f"{portfolio.Fname} {portfolio.Lname}"],
        ["Email:", portfolio.Email],
        ["Phone:", portfolio.Phone],
        ["LinkedIn:", portfolio.LinkedIn],
        ["GitHub:", portfolio.GitHub],
    ]

    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#AED6F1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ]
    )

    table = Table(personal_info, colWidths=[1.5 * inch, 4.5 * inch])
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.5 * inch))

    # Bio Section
    elements.append(Paragraph("Bio", subtitle_style))
    elements.append(Paragraph(portfolio.Bio, body_style))
    elements.append(Spacer(1, 0.5 * inch))

    # Skills Section
    elements.append(Paragraph("Skills", subtitle_style))
    elements.append(Paragraph(portfolio.Skills, body_style))

    # Build the PDF
    doc.build(elements)

    # Return the PDF file as a response
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_filename)
