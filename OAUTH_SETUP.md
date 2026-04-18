# OAuth Sign-In Setup

The app supports "Sign in with Discogs" so users can authenticate via OAuth instead of manually entering an API token.

## For App Users

1. Open Settings (expand the settings panel if collapsed).
2. Click **🔐 Sign in with Discogs**.
3. Your browser opens the Discogs authorization page.
4. Approve the app.
5. You're signed in automatically. No need to copy a token.

**Requirements:** The build must include OAuth consumer credentials (bundled in the app or via environment). If you see "no OAuth app is configured," either your distributor did not ship credentials, or you can use **Advanced → Personal Access Token** instead.

## For App Developers/Distributors

To enable one-click sign-in for everyone **without** asking users to create a `.env` file:

1. Go to [discogs.com/settings/developers](https://www.discogs.com/settings/developers).
2. Click **Create an application**.
3. Fill in:
   - **Application Name:** Discogs Vinyl Sorter (or your product name)
   - **Description:** (see main README)
   - **Callback URL:** `http://127.0.0.1:8765/callback`
4. Create the application and copy the **Consumer Key** and **Consumer Secret**.

5. **Recommended (end-user friendly):** Paste those values into `core/discogs_oauth_app.py`:

```python
BUNDLED_DISCOGS_CONSUMER_KEY = "your_consumer_key_here"
BUNDLED_DISCOGS_CONSUMER_SECRET = "your_consumer_secret_here"
```

Redistribute your build. All users can use **Sign in with Discogs** with no extra configuration.

**Alternative (developers / CI):** Set environment variables or a `.env` file instead; they override the bundled values when both `DISCOGS_CONSUMER_KEY` and `DISCOGS_CONSUMER_SECRET` are set:

```
DISCOGS_CONSUMER_KEY=your_consumer_key_here
DISCOGS_CONSUMER_SECRET=your_consumer_secret_here
```

**Note:** Consumer credentials are per-application, not per-user. One Discogs app registration is enough for all users of your distribution.
