# Telegram-Jira Bot

A comprehensive Telegram bot that seamlessly integrates with Jira to help teams manage issues and projects directly from Telegram. Create, manage, and track Jira issues without leaving your chat!

## 🌟 Features

### 🎫 Issue Management
- **Quick Issue Creation**: Send any message to create issues in your default project
- **Advanced Creation**: Interactive wizard with project, type, and priority selection
- **Issue Tracking**: View, search, and manage your issues
- **Smart Parsing**: Automatic priority and type detection from messages
- **Bulk Operations**: Manage multiple issues efficiently

### 📂 Project Management
- **Multi-Project Support**: Handle multiple Jira projects simultaneously
- **Project Sync**: Synchronize project data with Jira
- **Access Control**: Admin-controlled project creation and management
- **Statistics**: Detailed project analytics and reporting

### 🧙‍♂️ Interactive Wizards
- **Setup Wizard**: Guided initial configuration
- **Quick Setup**: Fast default project configuration
- **Issue Creation Wizard**: Step-by-step issue creation
- **Project Setup Wizard**: Guided project creation (admin only)

### ⚙️ User Preferences
- **Default Projects**: Set your preferred project for quick creation
- **Custom Defaults**: Configure default priority and issue types
- **UI Preferences**: Customize display options and formatting
- **Notification Settings**: Control bot notifications

### 🔧 Admin Features
- **User Management**: View and manage bot users
- **System Monitoring**: Bot status and performance metrics
- **Data Synchronization**: Sync with Jira for latest updates
- **Maintenance Tools**: Database cleanup and optimization

### 🚀 Advanced Features
- **Command Shortcuts**: Quick commands for power users
- **Search & Filters**: Advanced issue search capabilities
- **Time Tracking**: Integration with Jira time tracking
- **Comments**: Add and view issue comments
- **File Attachments**: Support for file uploads (configurable)

## 📋 Requirements

- Python 3.9+
- Telegram Bot Token
- Jira Cloud/Server instance
- Jira API Token

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/telegram-jira-bot.git
cd telegram-jira-bot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure the Bot

```bash
cp .env.example .env
# Edit .env with your configuration
```

Required configuration:
- `TELEGRAM_TOKEN`: Get from [@BotFather](https://t.me/BotFather)
- `JIRA_DOMAIN`: Your Jira domain (e.g., company.atlassian.net)
- `JIRA_EMAIL`: Your Jira account email
- `JIRA_API_TOKEN`: Generate from [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)

### 4. Run the Bot

```bash
python main.py
```

### 5. Start Using

1. Send `/start` to your bot
2. Run `/wizard` for guided setup
3. Add projects (admin only): `/addproject KEY "Project Name" "Description"`
4. Set your default project: `/setdefault KEY`
5. Send any message to create your first issue!

## 🎮 Commands

### Basic Commands
- `/start` - Welcome message and initial setup
- `/help` - Show detailed help and commands
- `/wizard` - Interactive setup wizard
- `/quick` - Quick setup for new users
- `/status` - Bot status and your statistics

### Project Commands
- `/projects` - List available projects
- `/addproject <KEY> <Name> [Description]` - Add new project (admin)
- `/editproject <KEY>` - Edit project details (admin)
- `/deleteproject <KEY>` - Delete project (admin)
- `/setdefault <KEY>` - Set your default project

### Issue Commands
- `/create` - Interactive issue creation
- `/myissues` - Your recent issues
- `/listissues [filters]` - List all issues with optional filters
- `/searchissues <query>` - Search issues by text

### Admin Commands
- `/users` - List all users and statistics
- `/syncjira` - Synchronize data with Jira
- `/config` - View/edit bot configuration (super admin)
- `/broadcast <message>` - Send message to all users (super admin)
- `/maintenance` - Maintenance tools (super admin)

### Shortcuts
Power users can use shortcuts for faster access:
- `/p` → `/projects`
- `/c` → `/create`
- `/mi` → `/myissues`
- `/s` → `/status`
- `/w` → `/wizard`
- `/ap` → `/addproject` (admin)
- `/u` → `/users` (admin)

## 💡 Usage Examples

### Quick Issue Creation
```
# Simple issue
Login button not working

# With priority
HIGH BUG App crashes on startup

# With type and priority
STORY User wants dark mode feature

# With custom priority
LOWEST IMPROVEMENT Add tooltips to buttons
```

### Advanced Filtering
```bash
# List issues with filters
/listissues project=WEBAPP type=Bug priority=High

# Search for specific issues
/searchissues authentication error
```

### Project Management
```bash
# Add a new project
/addproject MOBILE "Mobile App" "iOS and Android application"

# Edit project
/editproject MOBILE

# Sync all projects with Jira
/syncjira
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `TELEGRAM_TOKEN` | Telegram bot token | - | ✅ |
| `JIRA_DOMAIN` | Jira domain | - | ✅ |
| `JIRA_EMAIL` | Jira account email | - | ✅ |
| `JIRA_API_TOKEN` | Jira API token | - | ✅ |
| `DATABASE_PATH` | SQLite database file | `bot_data.db` | ❌ |
| `LOG_LEVEL` | Logging level | `INFO` | ❌ |
| `MAX_SUMMARY_LENGTH` | Max issue summary length | `200` | ❌ |
| `DEFAULT_PRIORITY` | Default issue priority | `Medium` | ❌ |
| `DEFAULT_ISSUE_TYPE` | Default issue type | `Task` | ❌ |
| `ALLOWED_USERS` | Comma-separated user IDs | (all users) | ❌ |
| `ADMIN_USERS` | Comma-separated admin IDs | - | ❌ |
| `ENABLE_WIZARDS` | Enable interactive wizards | `true` | ❌ |

See `.env.example` for complete configuration options.

### User Roles

1. **User**: Basic issue creation and management
2. **Admin**: Project management, user statistics
3. **Super Admin**: System configuration, broadcasting, maintenance

### Security Features

- **User Access Control**: Restrict bot access to specific users
- **Role-based Permissions**: Different capabilities for different user types
- **Rate Limiting**: Prevent API abuse
- **Input Validation**: Comprehensive validation of all inputs
- **Secure API Communication**: HTTPS-only Jira communication

## 🏗️ Architecture

### Project Structure
```
telegram_jira_bot/
├── config/          # Configuration management
├── models/          # Data models (Project, Issue, User, etc.)
├── services/        # Core services (Database, Jira, Telegram)
├── handlers/        # Command and callback handlers
├── utils/           # Utilities (validators, formatters, constants)
└── tests/           # Test suite
```

### Key Components

- **Database Manager**: SQLite-based data persistence
- **Jira Service**: Jira API integration with retry logic
- **Telegram Service**: Telegram bot API wrapper
- **Handler System**: Modular command and callback handling
- **Wizard System**: Interactive guided workflows
- **Validation System**: Comprehensive input validation

## 🧪 Testing

Run the test suite:
```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=telegram_jira_bot --cov-report=html

# Run specific test file
pytest tests/test_models.py
```

## 📊 Monitoring

The bot includes comprehensive monitoring and logging:

- **Application Logs**: Detailed logging with rotation
- **User Activity**: Track user actions and bot usage
- **Performance Metrics**: Monitor response times and errors
- **Database Statistics**: Monitor database size and performance
- **Jira API Metrics**: Track API usage and response times

## 🔄 Maintenance

### Regular Tasks
- Monitor logs for errors and warnings
- Review user activity and usage patterns
- Update Jira API tokens before expiration
- Backup database regularly
- Check for bot updates

### Database Maintenance
```bash
# Access bot maintenance tools
/maintenance

# Available operations:
# - Database cleanup (remove expired sessions)
# - Cache clearing
# - Database optimization (VACUUM)
# - Database backup
```

## 🛡️ Security Considerations

1. **API Token Security**:
   - Store tokens in environment variables
   - Rotate tokens regularly
   - Use strong Jira account passwords

2. **Access Control**:
   - Restrict bot access to trusted users
   - Use admin roles appropriately
   - Monitor user activity

3. **Data Protection**:
   - Regularly backup database
   - Use HTTPS for all communications
   - Validate all user inputs

4. **Monitoring**:
   - Monitor logs for suspicious activity
   - Set up alerts for errors
   - Review user permissions regularly

## 🐛 Troubleshooting

### Common Issues

**Bot doesn't respond**:
- Check Telegram token validity
- Verify bot is running
- Check logs for errors

**Jira connection fails**:
- Verify Jira domain format
- Check API token validity
- Ensure Jira permissions are correct

**Database errors**:
- Check database file permissions
- Verify disk space
- Check database file integrity

**Permission errors**:
- Verify user IDs in configuration
- Check admin role assignments
- Review Jira project permissions

### Debugging

Enable debug logging:
```bash
LOG_LEVEL=DEBUG python main.py
```

Check specific logs:
```bash
tail -f telegram_jira_bot.log | grep ERROR
```

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/telegram-jira-bot.git

# Install development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest

# Run linting
flake8 telegram_jira_bot/
mypy telegram_jira_bot/
```

## 📝 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for the excellent Telegram bot framework
- [aiohttp](https://github.com/aio-libs/aiohttp) for async HTTP client
- [Atlassian](https://www.atlassian.com/) for providing Jira APIs

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/telegram-jira-bot/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/telegram-jira-bot/discussions)
- **Documentation**: [Wiki](https://github.com/yourusername/telegram-jira-bot/wiki)

## 🚀 Roadmap

### Upcoming Features
- [ ] Advanced JQL query support
- [ ] Issue templates
- [ ] Webhook support for real-time updates
- [ ] Multi-language support
- [ ] Slack integration
- [ ] Advanced reporting and analytics
- [ ] Custom field support
- [ ] Agile board integration
- [ ] Mobile app companion

### Version History
- **v2.1.0**: Current version with wizards and enhanced features
- **v2.0.0**: Multi-project support and admin features
- **v1.0.0**: Initial release with basic functionality

---

**Made with ❤️ for better team collaboration**

Transform your team's workflow with seamless Jira integration in Telegram. Create issues, track progress, and stay organized without leaving your chat!