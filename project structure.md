telegram_jira_bot/
├── requirements.txt
├── README.md
├── .env.example
├── setup.py
├── main.py
├── config/
│   ├── __init__.py
│   └── settings.py
├── models/
│   ├── __init__.py
│   ├── project.py
│   ├── issue.py
│   ├── user.py
│   └── enums.py
├── services/
│   ├── __init__.py
│   ├── database.py
│   ├── jira_service.py
│   └── telegram_service.py
├── handlers/
│   ├── __init__.py
│   ├── admin_handlers.py
│   ├── project_handlers.py
│   ├── issue_handlers.py
│   ├── wizard_handlers.py
│   └── base_handler.py
├── utils/
│   ├── __init__.py
│   ├── validators.py
│   ├── formatters.py
│   ├── decorators.py
│   └── constants.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_services.py
    ├── test_handlers.py
    └── conftest.py