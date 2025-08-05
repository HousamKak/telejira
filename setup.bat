@echo off
REM Windows setup script for Telegram-Jira Bot

python -m venv venv || exit /b

call venv\Scripts\activate || exit /b

pip install -r requirements.txt
IF EXIST requirements-dev.txt (
    pip install -r requirements-dev.txt
)

pre-commit install

IF NOT EXIST .env (
    copy .env.example .env
    echo Created .env from .env.example. Please update it with your credentials.
)

echo Setup complete.
