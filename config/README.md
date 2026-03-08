# Google OAuth2 Setup Instructions

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing one.
3. Enable the **Gmail API**:
   - Navigate to **APIs & Services > Library**.
   - Search for "Gmail API" and enable it.

## 2. Configure OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**.
2. Choose **External** (for personal/testing) or **Internal** (for workspace).
3. Fill in the required fields (App name, user support email, developer contact email).
4. Add the following scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
5. Add your email as a test user (if using External type).

## 3. Create OAuth 2.0 Client ID

1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > OAuth client ID**.
3. Choose **Desktop application** as the application type.
4. Give it a name (e.g., "Gmail Receipt Parser").
5. Click **Create**.
6. Download the JSON file and rename it to `client_secrets.json`.
7. Place `client_secrets.json` in the `config/` directory.

## 4. Update `.env` file

Add the following environment variable to your `.env` file (optional):

```
GOOGLE_APPLICATION_CREDENTIALS=config/client_secrets.json
```

## 5. First Run Authorization

When you run the script for the first time:

1. The script will open a browser window asking you to log in with your Google account.
2. Grant the requested permissions (Gmail read-only access).
3. The authorization token will be saved as `config/token.json` for future runs.

## Notes

- The `client_secrets.example.json` file shows the expected structure. **Do not commit your actual `client_secrets.json`** (keep it private).
- If you change the OAuth scopes, delete `token.json` to force re-authorization.
- For production use, consider using a Service Account instead of OAuth2 for automated scripts.