from codex_api import app, db
from sqlalchemy import text

# List all relevant tables to truncate
TABLES = [
    'users', 'profiles', 'projects', 'experiments', 'protocol_versions', 'experiment_steps',
    'file_attachments', 'chat_channels', 'chat_messages', 'grants', 'grant_applications',
    'awards', 'grant_milestones', 'discovery_items', 'collaboration_suggestions'
]

with app.app_context():
    db.session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE;"))
    db.session.commit()
    print('All tables truncated.')
