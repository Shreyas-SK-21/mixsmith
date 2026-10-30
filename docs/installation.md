# Mixsmith Installation & Setup Guide

---

## Prerequisites

- **Python**: Version 3.10 or higher.
- **Spotify Developer App**: Free Spotify account with developer app registration.

---

## 1. Installation

### From Source (Recommended for Developers)

```bash
git clone https://github.com/Shreyas-SK-21/mixsmith.git
cd mixsmith
pip install -e .
```

### Direct Pip Install

```bash
pip install -r requirements.txt
```

---

## 2. Spotify App Setup

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Log in and click **Create App**.
3. Fill in:
   - **App name**: `Mixsmith` (or any name you prefer)
   - **App description**: `Music curation engine`
   - **Redirect URI**: `http://127.0.0.1:8888/callback` (Required)
   - **APIs used**: Web API
4. Save and click **Settings** to find your **Client ID** and **Client Secret**.

---

## 3. Configuration & Authentication

### Option A: Interactive CLI Setup

```bash
python -m mixsmith.cli auth setup
```
Follow the prompt to paste your Client ID and Client Secret. Mixsmith will open your browser to log in via Spotify OAuth.

### Option B: Environment Variables / `.env`

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in:
```ini
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```
Then log in:
```bash
python -m mixsmith.cli auth login
```

---

## 4. Verification

Verify that your authentication is active:
```bash
python -m mixsmith.cli auth status
```
Output should indicate `[OK] Authenticated as: <Your Name>`.
