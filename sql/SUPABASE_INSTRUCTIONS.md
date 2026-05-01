Steps to create the Supabase schema and configure the app

1) Create the tables
- Open your Supabase project dashboard -> SQL Editor -> New query
- Copy the contents of `sql/supabase_schema.sql` and run it.

2) Set environment variables for the backend (server-side only)
- On your server (or in your development `.env`), set:

SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
SUPABASE_ANON_KEY=<your-anon-key>  # optional for frontend
TOKEN_ENCRYPTION_KEY=<optional-secret-to-derive-encryption-key>

- Example `.env` (do NOT commit secrets to source control):

SUPABASE_URL=https://ivynseqmsuiafiomrcmw.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<paste-service-role-key-here>
SUPABASE_ANON_KEY=<paste-anon-key-here>

3) Verify the store from Python (quick test)
- Install `requests` and `cryptography` in your Python env if not already installed.
- Run a short Python snippet (replace values as appropriate):

```python
from mail_ai.supabase_store import SupabaseConfig, SupabaseStore
config = SupabaseConfig(
    url='https://ivynseqmsuiafiomrcmw.supabase.co',
    service_role_key='<SERVICE_ROLE_KEY>',
    token_encryption_key=None,
)
store = SupabaseStore(config)
print(store.ensure_user('you@example.com', 'You'))
```

4) Run the app
- Ensure the environment variables are set and start the backend as you normally do.

Notes
- This project uses the Supabase REST `rest/v1` endpoints for simple upsert/lookup operations. For schema creation you must use the SQL editor or a Postgres client.
- Keep the `SUPABASE_SERVICE_ROLE_KEY` secret — it grants full DB privileges.
