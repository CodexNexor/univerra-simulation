"""
Configuration Management
Loads configuration from the .env file in the project root directory
"""

import os
from dotenv import load_dotenv
from .utils.llm_base import normalize_openai_base_url

# Load the .env file from the project root directory
# Path: Univerra/.env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If no .env in root directory, try loading environment variables (for production)
    load_dotenv(override=True)


class Config:
    """Flask configuration class"""

    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'univerra-secret-key')
    AUTH_SECRET_KEY = os.environ.get('AUTH_SECRET_KEY', SECRET_KEY)
    AUTH_TOKEN_MAX_AGE_SECONDS = int(os.environ.get('AUTH_TOKEN_MAX_AGE_SECONDS', str(7 * 24 * 60 * 60)))
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

    # JSON configuration - disable ASCII escaping, display non-ASCII characters directly (instead of \uXXXX format)
    JSON_AS_ASCII = False

    # LLM configuration (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = normalize_openai_base_url(os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1'))
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

    # Tavily web research configuration
    TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
    TAVILY_BASE_URL = os.environ.get('TAVILY_BASE_URL', 'https://api.tavily.com')
    TAVILY_MAX_RESULTS = int(os.environ.get('TAVILY_MAX_RESULTS', '3'))
    TAVILY_SEARCH_DEPTH = os.environ.get('TAVILY_SEARCH_DEPTH', 'advanced')
    TAVILY_TIMEOUT_SECONDS = int(os.environ.get('TAVILY_TIMEOUT_SECONDS', '20'))
    TAVILY_MAX_AGE_DAYS = int(os.environ.get('TAVILY_MAX_AGE_DAYS', '120'))

    # Reddit research configuration
    REDDIT_RESEARCH_ENABLED = os.environ.get('REDDIT_RESEARCH_ENABLED', 'True').lower() == 'true'
    REDDIT_USER_AGENT = os.environ.get(
        'REDDIT_USER_AGENT',
        'UniverraResearchBot/1.0 (+https://localhost; contact: local-dev)'
    )
    REDDIT_TIMEOUT_SECONDS = int(os.environ.get('REDDIT_TIMEOUT_SECONDS', '20'))
    REDDIT_MAX_SUBQUERIES = int(os.environ.get('REDDIT_MAX_SUBQUERIES', '4'))
    REDDIT_POSTS_PER_QUERY = int(os.environ.get('REDDIT_POSTS_PER_QUERY', '3'))
    REDDIT_COMMENTS_PER_POST = int(os.environ.get('REDDIT_COMMENTS_PER_POST', '4'))
    REDDIT_MAX_AGE_DAYS = int(os.environ.get('REDDIT_MAX_AGE_DAYS', '365'))

    # MongoDB user/profile/history storage
    MONGODB_URI = os.environ.get('MONGODB_URI')
    MONGODB_DB_NAME = os.environ.get('MONGODB_DB_NAME', 'univerra')
    MONGODB_TIMEOUT_MS = int(os.environ.get('MONGODB_TIMEOUT_MS', '5000'))

    # In-memory API rate limits. These protect local/dev deployments and small
    # production instances; place a gateway/WAF in front for distributed limits.
    RATE_LIMIT_AUTH_ATTEMPTS = int(os.environ.get('RATE_LIMIT_AUTH_ATTEMPTS', '5'))
    RATE_LIMIT_AUTH_WINDOW_SECONDS = int(os.environ.get('RATE_LIMIT_AUTH_WINDOW_SECONDS', '900'))
    RATE_LIMIT_GRAPH_GENERATE_PER_HOUR = int(os.environ.get('RATE_LIMIT_GRAPH_GENERATE_PER_HOUR', '20'))
    RATE_LIMIT_GRAPH_BUILD_PER_HOUR = int(os.environ.get('RATE_LIMIT_GRAPH_BUILD_PER_HOUR', '30'))
    RATE_LIMIT_SIMULATION_CREATE_PER_HOUR = int(os.environ.get('RATE_LIMIT_SIMULATION_CREATE_PER_HOUR', '30'))
    RATE_LIMIT_SIMULATION_PREPARE_PER_HOUR = int(os.environ.get('RATE_LIMIT_SIMULATION_PREPARE_PER_HOUR', '10'))
    RATE_LIMIT_SIMULATION_START_PER_HOUR = int(os.environ.get('RATE_LIMIT_SIMULATION_START_PER_HOUR', '20'))
    RATE_LIMIT_REPORT_GENERATE_PER_HOUR = int(os.environ.get('RATE_LIMIT_REPORT_GENERATE_PER_HOUR', '20'))

    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing configuration
    DEFAULT_CHUNK_SIZE = 500  # Default chunk size
    DEFAULT_CHUNK_OVERLAP = 50  # Default overlap size

    # OASIS simulation configuration
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    # OASIS platform available actions configuration
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    # Report Agent configuration
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    # Simulation scaling defaults
    SIMULATION_MIN_AGENT_COUNT = int(os.environ.get('SIMULATION_MIN_AGENT_COUNT', '8'))
    SIMULATION_MAX_SYNTHETIC_AGENTS = int(os.environ.get('SIMULATION_MAX_SYNTHETIC_AGENTS', '8'))

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY is not configured")
        return errors
