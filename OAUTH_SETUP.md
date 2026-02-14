# OAuth Sign-In Setup

The app supports "Sign in with Discogs" so users can authenticate via OAuth instead of manually entering an API token.

## For App Users

1. Open Settings (expand the settings panel if collapsed).
2. Click **🔐 Sign in with Discogs**.
3. Your browser opens the Discogs authorization page.
4. Approve the app.
5. You're signed in automatically. No need to copy a token.

**Requirements:** The app must have consumer credentials configured (see below). If you see an error, your distributor has not set this up yet.

## For App Developers/Distributors

To enable OAuth sign-in, you need a Discogs application:

1. Go to [discogs.com/settings/developers](https://www.discogs.com/settings/developers).
2. Click **Create an application**.
3. Fill in:
   - **Application Name:** Discogs Vinyl Sorter
   - **Description:** (see main README)
   - **Callback URL:** `http://127.0.0.1:8765/callback`
4. Create the application and copy the **Consumer Key** and **Consumer Secret**.

5. Create a `.env` file in the project directory (or set environment variables):

```
DISCOGS_CONSUMER_KEY=your_consumer_key_here
DISCOGS_CONSUMER_SECRET=your_consumer_secret_here
```

6. The app will now show the "Sign in with Discogs" button. Users who sign in will have their OAuth tokens stored (encrypted) in the config file.

**Note:** Consumer credentials are per-application, not per-user. One registration is enough for all users of your distribution.
