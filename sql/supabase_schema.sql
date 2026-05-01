-- Supabase schema for Mail AI
-- Run this in Supabase SQL editor (Project -> SQL Editor -> New query)

-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Users table
CREATE TABLE IF NOT EXISTS app_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL UNIQUE,
  display_name text,
  created_at timestamptz DEFAULT now(),
  last_login_at timestamptz
);

-- Gmail tokens (encrypted)
CREATE TABLE IF NOT EXISTS gmail_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  provider text NOT NULL DEFAULT 'google',
  token_json_encrypted text NOT NULL,
  updated_at timestamptz DEFAULT now(),
  CONSTRAINT gmail_tokens_email_provider_unique UNIQUE (email, provider),
  CONSTRAINT gmail_tokens_user_fk FOREIGN KEY (email) REFERENCES app_users (email) ON DELETE CASCADE
);

-- Message summaries cache
CREATE TABLE IF NOT EXISTS message_summaries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  message_id text NOT NULL,
  summary_json jsonb NOT NULL,
  fetched_at timestamptz DEFAULT now(),
  CONSTRAINT message_summaries_unique UNIQUE (email, message_id),
  CONSTRAINT message_summaries_user_fk FOREIGN KEY (email) REFERENCES app_users (email) ON DELETE CASCADE
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_gmail_tokens_email ON gmail_tokens (email);
CREATE INDEX IF NOT EXISTS idx_message_summaries_email ON message_summaries (email);
