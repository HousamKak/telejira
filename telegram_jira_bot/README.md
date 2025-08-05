# 🤖 Telegram-Jira Bot

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tested with pytest](https://img.shields.io/badge/tested%20with-pytest-red.svg)](https://docs.pytest.org/)

A comprehensive Telegram bot that seamlessly integrates with Jira to help teams manage issues and projects directly from Telegram. Create, manage, and track Jira issues without leaving your chat!

## 🌟 Features

### 🎫 Issue Management
- **Quick Issue Creation**: Send any message to create issues in your default project
- **Interactive Wizards**: Step-by-step guided issue creation with project, type, and priority selection
- **Smart Parsing**: Automatic priority and type detection from messages (e.g., "HIGH BUG Login broken")
- **Issue Tracking**: View, search, and manage your issues with rich formatting
- **Bulk Operations**: Manage multiple issues efficiently
- **Comments**: Add and view issue comments directly in Telegram

### 📂 Project Management
- **Multi-Project Support**: Handle multiple Jira projects simultaneously
- **Project Sync**: Synchronize project data with Jira automatically
- **Access Control**: Admin-controlled project creation and management
- **Statistics**: Detailed project analytics and reporting
- **Default Projects**: Set preferred projects for quick issue creation

### 🧙‍♂️ Interactive Wizards
- **Setup Wizard**: Guided initial configuration for new users
- **Quick Setup**: Fast default project configuration
- **Issue Creation Wizard**: Step-by-step issue creation with all options
- **Project Setup Wizard**: Guided project creation (admin only)

### ⚙️ User Preferences
- **Default Settings**: Configure default priority, issue types, and projects
- **UI Customization**: Customize display options and message formatting
- **Notification Settings**: Control bot notifications and updates
- **Role-Based Access**: Different capabilities for users, admins, and super admins

### 🔧 Admin Features
- **User Management**: View and manage bot users with detailed statistics
- **System Monitoring**: Bot status, performance metrics, and health checks
- **Data Synchronization**: Sync with Jira for latest updates and consistency
- **Maintenance Tools**: Database cleanup, optimization, and backup utilities
- **Broadcasting**: Send announcements to all users (super admin only)

### 🚀 Advanced Features
- **Command Shortcuts**: Quick commands for power users (`/p` → `/projects`)
- **Search & Filters**: Advanced issue search with JQL-like capabilities
- **Time Tracking**: Integration with Jira time tracking (if enabled)
- **Inline Keyboards**: Modern UI with clickable buttons and menus
- **File Attachments**: Support for file uploads to issues (configurable)
- **Webhook Support**: Real-time updates from Jira (planned)

## 📋 Requirements

- **Python**: 3.9 or higher
- **Telegram Bot Token**: From [@BotFather](https://t.me/BotFather)
- **Jira Instance**: Cloud or Server with API access
- **Jira API Token**: From [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/telegram-jira-bot.git
cd telegram-jira-bot
```

### 2. Install Dependencies

```bash
# Using pip
pip install -r requirements.txt

# Using pip with development dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Using the package (after setup)
pip install -e .
```

On Windows, you can run the setup script to automate these steps:

```bat
setup.bat
```

This will create a virtual environment, install dependencies (including `requirements-dev.txt` if present), install pre-commit hooks, and copy `.env.example` to `.env` if it doesn't exist.

### 3. Configure the Bot

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your configuration
nano .env  # or use your preferred editor
```

If you ran `setup.bat`, the `.env` file was created automatically. Open it and update the credentials as needed.

**Required configuration:**
```env
TELEGRAM_TOKEN=your_bot_token_from_botfather
JIRA_DOMAIN=your-company.atlassian.net
JIRA_EMAIL=your-jira-email@company.com
JIRA_API_TOKEN=your_jira_api_token
```

### 4. Run the Bot

```bash
# Direct execution
python main.py

# Using the installed package
telegram-jira-bot

# Using the shortcut command
tg-jira
```

### 5. Start Using the Bot

1. **Send `/start`** to your bot in Telegram
2. **Run `/wizard`** for guided setup
3. **Add projects** (admin only): `/addproject KEY "Project Name" "Description"`
4. **Set your default project**: `/setdefault KEY`
5. **Create your first issue**: Just send any message!

Example:
```
HIGH BUG Login button not working on mobile devices
```

## 🎮 Commands Reference

### Basic Commands
| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message and initial setup | `/start` |
| `/help` | Show detailed help and commands | `/help` |
| `/wizard` | Interactive setup wizard | `/wizard` |
| `/status` | Bot status and your statistics | `/status` |

### Project Commands
| Command | Description | Example |
|---------|-------------|---------|
| `/projects` | List available projects | `/projects` |
| `/setdefault <KEY>` | Set your default project | `/setdefault WEBAPP` |

### Issue Commands  
| Command | Description | Example |
|---------|-------------|---------|
| `/create` | Interactive issue creation | `/create` |
| `/myissues` | Your recent issues | `/myissues` |
| `/listissues [filters]` | List all issues with optional filters | `/listissues project=WEBAPP` |
| `/searchissues <query>` | Search issues by text | `/searchissues login error` |

### Admin Commands (Admin Only)
| Command | Description | Example |
|---------|-------------|---------|
| `/addproject <KEY> <name> [desc]` | Add new project | `/addproject MOBILE "Mobile App"` |
| `/editproject <KEY>` | Edit project details | `/editproject WEBAPP` |
| `/deleteproject <KEY>` | Delete project | `/deleteproject OLD` |
| `/users` | List all users and statistics | `/users` |
| `/syncjira` | Synchronize data with Jira | `/syncjira` |

### Super Admin Commands (Super Admin Only)
| Command | Description | Example |
|---------|-------------|---------|
| `/config` | View/edit bot configuration | `/config` |
| `/broadcast <message>` | Send message to all users | `/broadcast Server maintenance tonight` |
| `/maintenance` | Maintenance tools | `/maintenance` |

### Command Shortcuts
Power users can use shortcuts for faster access:
| Shortcut | Full Command | Description |
|----------|--------------|-------------|
| `/p` | `/projects` | List projects |
| `/c` | `/create` | Create issue |
| `/mi` | `/myissues` | My issues |
| `/s` | `/status` | Bot status |
| `/w` | `/wizard` | Setup wizard |
| `/ap` | `/addproject` | Add project (admin) |
| `/u` | `/users` | List users (admin) |

## 💡 Usage Examples

### Quick Issue Creation
```bash
# Simple issue
Login button not working

# With priority
HIGH BUG App crashes on startup

# With type and priority  
STORY User wants dark mode feature

# With custom priority
LOWEST IMPROVEMENT Add tooltips to buttons
```

### Advanced Issue Management
```bash
# Create with wizard for full control
/create

# List your issues
/myissues

# Search for specific issues
/searchissues authentication error

# List issues with filters
/listissues project=WEBAPP type=Bug priority=High
```

### Project Management
```bash
# List all projects
/projects

# Set default project for quick creation
/setdefault WEBAPP

# Add a new project (admin only)
/addproject MOBILE "Mobile App" "iOS and Android application"

# Sync all projects with Jira
/syncjira
```

### User Roles and Permissions
```bash
# Regular users can:
- Create and manage their own issues
- View projects and other users' issues
- Set personal preferences

# Admins can additionally:
- Add/edit/delete projects
- View user statistics
- Sync data with Jira

# Super admins can additionally:
- Configure bot settings
- Broadcast messages to all users
- Access maintenance tools
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| **Core Settings** | | | |
| `TELEGRAM_TOKEN` | Telegram bot token | - | ✅ |
| `JIRA_DOMAIN` | Jira domain (e.g., company.atlassian.net) | - | ✅ |
| `JIRA_EMAIL` | Jira account email | - | ✅ |
| `JIRA_API_TOKEN` | Jira API token | - | ✅ |
| **Database** | | | |
| `DATABASE_PATH` | SQLite database file path | `bot_data.db` | ❌ |
| `DATABASE_POOL_SIZE` | Connection pool size | `10` | ❌ |
| `DATABASE_TIMEOUT` | Connection timeout (seconds) | `30` | ❌ |
| **Bot Behavior** | | | |
| `MAX_SUMMARY_LENGTH` | Max issue summary length | `100` | ❌ |
| `MAX_DESCRIPTION_LENGTH` | Max issue description length | `2000` | ❌ |
| `MAX_ISSUES_PER_PAGE` | Issues per page in lists | `10` | ❌ |
| `SESSION_TIMEOUT_HOURS` | User session timeout | `24` | ❌ |
| **Defaults** | | | |
| `DEFAULT_PRIORITY` | Default issue priority | `Medium` | ❌ |
| `DEFAULT_ISSUE_TYPE` | Default issue type | `Task` | ❌ |
| **Security** | | | |
| `ALLOWED_USERS` | Comma-separated user IDs | (all users) | ❌ |
| `ADMIN_USERS` | Comma-separated admin IDs | - | ❌ |
| `SUPER_ADMIN_USERS` | Comma-separated super admin IDs | - | ❌ |
| `RATE_LIMIT_PER_MINUTE` | Rate limit per minute | `60` | ❌ |
| **Logging** | | | |
| `LOG_LEVEL` | Logging level | `INFO` | ❌ |
| `LOG_FILE` | Log file path | `telegram_jira_bot.log` | ❌ |
| `LOG_MAX_SIZE` | Max log file size (bytes) | `10485760` | ❌ |
| **Features** | | | |
| `ENABLE_WIZARDS` | Enable interactive wizards | `true` | ❌ |
| `ENABLE_SHORTCUTS` | Enable command shortcuts | `true` | ❌ |
| `ENABLE_NOTIFICATIONS` | Enable notifications | `true` | ❌ |
| `ENABLE_TIME_TRACKING` | Enable time tracking | `true` | ❌ |

See `.env.example` for complete configuration options with descriptions.

### User Roles

#### 👤 User (Default)
- Create and manage own issues
- View projects and issue lists
- Set personal preferences
- Use all basic bot features

#### 🛡️ Admin
- All user permissions plus:
- Add, edit, and delete projects
- View user statistics and activity
- Sync data with Jira
- Access admin commands

#### 👑 Super Admin
- All admin permissions plus:
- Configure bot settings
- Broadcast messages to all users
- Access maintenance and diagnostic tools
- Manage user roles

### Security Features

- **Access Control**: Restrict bot usage to specific Telegram users
- **Role-based Permissions**: Different capabilities based on user roles
- **Rate Limiting**: Prevent API abuse and spam
- **Input Validation**: Comprehensive validation of all user inputs
- **Secure Communications**: HTTPS-only Jira API communication
- **Audit Logging**: Track all user actions and system events

## 🏗️ Architecture

### Project Structure
```
telegram_jira_bot/
├── config/                 # Configuration management
│   ├── __init__.py
│   └── settings.py        # Bot configuration and validation
├── models/                # Data models
│   ├── __init__.py
│   ├── project.py         # Project model
│   ├── issue.py          # Issue and comment models
│   ├── user.py           # User model
│   └── enums.py          # Enumerations (Priority, Type, Status, Role)
├── services/              # Core services
│   ├── __init__.py
│   ├── database.py       # SQLite database manager
│   ├── jira_service.py   # Jira API integration
│   └── telegram_service.py # Telegram bot API wrapper
├── handlers/              # Command and callback handlers
│   ├── __init__.py
│   ├── base_handler.py   # Base handler with common functionality
│   ├── project_handlers.py # Project management commands
│   ├── issue_handlers.py # Issue management commands
│   ├── admin_handlers.py # Admin-only commands
│   └── wizard_handlers.py # Interactive wizard workflows
├── utils/                # Utility modules
│   ├── __init__.py
│   ├── validators.py     # Input validation functions
│   ├── formatters.py     # Message formatting utilities
│   ├── decorators.py     # Common decorators
│   └── constants.py      # Application constants
└── tests/                # Test suite
    ├── __init__.py
    ├── conftest.py       # Pytest configuration and fixtures
    ├── test_models.py    # Model tests
    ├── test_services.py  # Service tests
    └── test_handlers.py  # Handler tests
```

### Key Components

#### Database Manager
- **SQLite-based**: Lightweight, serverless database
- **Connection Pooling**: Efficient connection management
- **Transaction Support**: ACID compliance for data integrity
- **Migration Support**: Schema versioning and updates

#### Jira Service
- **REST API Integration**: Full Jira REST API support
- **Retry Logic**: Automatic retry for transient failures
- **Rate Limiting**: Respect Jira API rate limits
- **Error Handling**: Comprehensive error handling and logging

#### Telegram Service
- **Bot API Wrapper**: Clean interface to Telegram Bot API
- **Inline Keyboards**: Modern UI with clickable buttons
- **Message Formatting**: Rich text formatting with MarkdownV2
- **File Handling**: Support for file uploads and downloads

#### Handler System
- **Modular Design**: Separate handlers for different functionality
- **Permission Checks**: Role-based access control
- **Error Handling**: Graceful error handling and user feedback
- **Session Management**: User session and state management

#### Wizard System
- **Interactive Workflows**: Step-by-step guided processes
- **State Management**: Conversation state persistence
- **Input Validation**: Real-time input validation and feedback
- **Cancellation Support**: Cancel workflows at any time

## 🧪 Testing

The project includes a comprehensive test suite with unit tests, integration tests, and test utilities.

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov pytest-mock

# Run all tests
pytest

# Run with coverage report
pytest --cov=telegram_jira_bot --cov-report=html

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m database      # Database tests only
pytest -m network       # Network-dependent tests only

# Run specific test files
pytest tests/test_models.py
pytest tests/test_services.py
pytest tests/test_handlers.py

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x
```

### Test Structure

- **`tests/conftest.py`**: Pytest configuration, fixtures, and test utilities
- **`tests/test_models.py`**: Tests for data models and enums
- **`tests/test_services.py`**: Tests for database, Jira, and Telegram services
- **`tests/test_handlers.py`**: Tests for command handlers and user interactions

### Test Coverage

The test suite aims for high coverage across all components:

- **Models**: Data validation, serialization, business logic
- **Services**: API integration, database operations, error handling
- **Handlers**: Command processing, permission checks, user interactions
- **Utilities**: Validation functions, formatters, decorators

### Continuous Integration

```bash
# Lint code
flake8 telegram_jira_bot/
black --check telegram_jira_bot/
isort --check-only telegram_jira_bot/

# Type checking
mypy telegram_jira_bot/

# Security checks
bandit -r telegram_jira_bot/

# Run full test suite with coverage
pytest --cov=telegram_jira_bot --cov-fail-under=80
```

## 📊 Monitoring and Logging

### Application Logs
The bot includes comprehensive logging with configurable levels:

```bash
# View live logs
tail -f telegram_jira_bot.log

# Filter by level
grep "ERROR" telegram_jira_bot.log
grep "WARNING" telegram_jira_bot.log

# Monitor specific components
grep "JiraService" telegram_jira_bot.log
grep "DatabaseManager" telegram_jira_bot.log
```

### Performance Monitoring
- **Response Times**: Track command processing times
- **API Metrics**: Monitor Jira API usage and response times
- **Database Performance**: Log slow queries and connection issues
- **Memory Usage**: Track memory consumption and potential leaks

### User Activity Tracking
- **Command Usage**: Track which commands are used most frequently
- **Error Rates**: Monitor user-facing errors and issues
- **Session Analytics**: User engagement and session duration
- **Issue Creation Patterns**: Analyze issue creation trends

### Health Checks
```bash
# Check bot status
/status

# Admin health check (admin only)
/maintenance

# View system statistics
/users  # Shows user activity stats
```

## 🛡️ Security Considerations

### API Security
1. **Token Management**:
   - Store tokens in environment variables, never in code
   - Rotate Jira API tokens regularly (recommended every 90 days)
   - Use strong, unique passwords for Jira accounts

2. **Access Control**:
   - Restrict bot access to trusted Telegram users only
   - Use admin roles judiciously, follow principle of least privilege
   - Regularly review user permissions and access levels

3. **Data Protection**:
   - Enable HTTPS for all Jira API communications
   - Regularly backup the SQLite database
   - Validate and sanitize all user inputs

### Infrastructure Security
1. **Server Security**:
   - Keep the host system updated with security patches
   - Use firewall rules to restrict unnecessary network access
   - Monitor system logs for suspicious activity

2. **Application Security**:
   - Regularly update Python dependencies
   - Use virtual environments to isolate dependencies
   - Enable comprehensive logging for security auditing

3. **Incident Response**:
   - Have a plan for token rotation in case of compromise
   - Monitor logs for unusual activity patterns
   - Know how to quickly disable the bot if needed

## 🐛 Troubleshooting

### Common Issues

#### Bot Doesn't Respond
```bash
# Check if bot is running
ps aux | grep python
ps aux | grep telegram-jira-bot

# Check logs for errors
tail -n 50 telegram_jira_bot.log

# Verify Telegram token
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Test bot connectivity
python -c "
import asyncio
from telegram_jira_bot.services.telegram_service import TelegramService
service = TelegramService('YOUR_TOKEN')
# Test will show connection status
"
```

#### Jira Connection Issues
```bash
# Test Jira credentials
curl -u email@example.com:api_token \
  https://your-domain.atlassian.net/rest/api/2/myself

# Check domain format (should NOT include https://)
# Correct: company.atlassian.net
# Incorrect: https://company.atlassian.net

# Verify API token (not password)
# Generate new token at: https://id.atlassian.com/manage-profile/security/api-tokens
```

#### Database Issues
```bash
# Check database file permissions
ls -la bot_data.db

# Test database connectivity
sqlite3 bot_data.db ".tables"

# Check database integrity
sqlite3 bot_data.db "PRAGMA integrity_check;"

# View recent errors
grep "DatabaseManager" telegram_jira_bot.log | tail -20
```

#### Permission Errors
```bash
# Check user configuration in .env
echo $ALLOWED_USERS
echo $ADMIN_USERS

# Verify user ID format (should be string of numbers)
# Get your Telegram user ID: message @userinfobot

# Check role assignments
grep "role" telegram_jira_bot.log
```

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
# Set environment variable
export LOG_LEVEL=DEBUG

# Or edit .env file
LOG_LEVEL=DEBUG

# Restart bot
python main.py
```

Debug logs include:
- All API requests and responses
- Database queries and results
- User permission checks
- Command processing steps
- Error stack traces

### Performance Issues

```bash
# Monitor resource usage
top -p $(pgrep -f telegram-jira-bot)

# Check database size
ls -lh bot_data.db

# View slow operations
grep "slow" telegram_jira_bot.log

# Database optimization (if needed)
sqlite3 bot_data.db "VACUUM;"
```

### Getting Help

1. **Check Logs**: Always check `telegram_jira_bot.log` first
2. **Search Issues**: Look for similar problems in GitHub issues
3. **Create Issue**: Provide logs, configuration (without secrets), and steps to reproduce
4. **Community**: Join discussions for tips and best practices

## 🤝 Contributing

We welcome contributions! Here's how to get started:

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/yourusername/telegram-jira-bot.git
cd telegram-jira-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run tests to ensure everything works
pytest
```

### Development Workflow

1. **Create Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**:
   - Follow the existing code style and patterns
   - Add tests for new functionality
   - Update documentation as needed

3. **Run Quality Checks**:
   ```bash
   # Format code
   black telegram_jira_bot/
   isort telegram_jira_bot/
   
   # Lint code
   flake8 telegram_jira_bot/
   
   # Type checking
   mypy telegram_jira_bot/
   
   # Run tests
   pytest --cov=telegram_jira_bot
   ```

4. **Commit and Push**:
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   git push origin feature/your-feature-name
   ```

5. **Create Pull Request**:
   - Provide clear title and description
   - Link any related issues
   - Ensure all checks pass

### Code Style Guidelines

- **Python Style**: Follow PEP 8, use Black for formatting
- **Type Hints**: Use type hints for all functions and methods
- **Documentation**: Add docstrings for all public functions
- **Error Handling**: Use specific exceptions and provide helpful messages
- **Testing**: Write tests for new features and bug fixes

### Areas for Contribution

- **New Features**: Issue templates, advanced JQL queries, webhook support
- **Integrations**: Slack support, other issue trackers, CI/CD integrations
- **UI/UX**: Better message formatting, more interactive features
- **Performance**: Query optimization, caching, async improvements
- **Documentation**: Tutorials, API documentation, deployment guides
- **Testing**: More test coverage, integration tests, performance tests

## 📝 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Excellent Telegram bot framework
- [aiohttp](https://github.com/aio-libs/aiohttp) - Async HTTP client for Jira API
- [Atlassian](https://www.atlassian.com/) - For providing comprehensive Jira APIs
- [SQLite](https://www.sqlite.org/) - Reliable embedded database
- [pytest](https://pytest.org/) - Powerful testing framework

## 📞 Support

- **🐛 Bug Reports**: [GitHub Issues](https://github.com/yourusername/telegram-jira-bot/issues)
- **💡 Feature Requests**: [GitHub Discussions](https://github.com/yourusername/telegram-jira-bot/discussions)
- **📖 Documentation**: [Project Wiki](https://github.com/yourusername/telegram-jira-bot/wiki)
- **💬 Community**: [Telegram Channel](https://t.me/telegram_jira_bot) (coming soon)

## 🚀 Roadmap

### Version 2.2.0 (Next Release)
- [ ] Advanced JQL query support for power users
- [ ] Issue templates for consistent issue creation
- [ ] Custom field support for specialized workflows
- [ ] Webhook support for real-time Jira updates
- [ ] Improved search with fuzzy matching

### Version 2.3.0 (Future)
- [ ] Multi-language support (i18n)
- [ ] Slack integration for cross-platform support
- [ ] Advanced reporting and analytics dashboard
- [ ] Mobile app companion
- [ ] API for third-party integrations

### Version 3.0.0 (Long-term)
- [ ] Support for multiple issue trackers (GitHub, GitLab, etc.)
- [ ] AI-powered issue categorization and routing
- [ ] Advanced workflow automation
- [ ] Enterprise features (SSO, audit logs, compliance)
- [ ] Cloud-hosted service option

---

**Made with ❤️ for better team collaboration**

Transform your team's workflow with seamless Jira integration in Telegram. Create issues, track progress, and stay organized without leaving your chat!

⭐ **Star this repository** if you find it useful!

📢 **Share with your team** and improve your workflow today!