-- Add notebook_entries and notebook_attachments tables
CREATE TABLE notebook_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  user_name VARCHAR(255),
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  device VARCHAR(255),
  location VARCHAR(255),
  session_id VARCHAR(255),
  experiment_id VARCHAR(255),
  version VARCHAR(50),
  visibility VARCHAR(50) DEFAULT 'team',
  content TEXT,
  structured JSONB,
  diffs JSONB
);

CREATE TABLE notebook_attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_id UUID REFERENCES notebook_entries(id) ON DELETE CASCADE,
  filename VARCHAR(255),
  storage_path VARCHAR(255),
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
