# Manual Test Checklist: Chrome Extension Popup & Configuration

Since automated testing cannot interact directly with Chrome Extension popups, Chrome store configurations, or microphone prompt dialogs, this checklist details the steps to manually verify the extension's behavior and settings.

---

## 1. Prerequisites and Setup
- [ ] **Load Unpacked Extension**: Open `chrome://extensions/`, enable Developer Mode, click "Load unpacked", and select the `chrome-extension/` directory.
- [ ] **FastAPI Server Running**: Ensure the backend FastAPI server is running locally on `http://127.0.0.1:8000`.
- [ ] **Chrome Console Opened**: Open the Extension Popup's Developer Console by right-clicking the extension icon and choosing **Inspect popup**.

---

## 2. Authentication Screen
- [ ] **Initial State Verification**:
  - Open the popup for the first time.
  - Verify that the **Login Screen** is displayed.
  - Assert that fields for Username and Password are blank.
- [ ] **Invalid Login Test**:
  - Enter invalid credentials (e.g. `admin` / `wrongpassword`).
  - Click **Sign In**.
  - Verify that a red error toast is displayed: `⚠ Invalid username or password`.
- [ ] **Valid Login & State Persistency**:
  - Enter `admin` / `admin123` (or any valid HR account).
  - Click **Sign In**.
  - Verify transition to the **App Screen** showing candidate statistics and active state controls.
  - Close the popup and open it again. Verify the session persists and you do not need to log in again.
- [ ] **Logout Flow**:
  - Click the user avatar/profile card and select **Log Out**.
  - Verify instant redirection to the login screen and clearing of `sai_auth` from `chrome.storage.local`.

---

## 3. Permissions & Audio Source Checks
- [ ] **Mic Permission Request**:
  - Verify the popup displays a status bar checking for microphone access.
  - If permissions are not granted, verify that the popup requests mic access upon clicking the Mic icon/button.
  - Grant microphone permissions via the Chrome prompt and verify that the status changes to green: `✓ Mic Access Active`.
- [ ] **API Connection Status Indicator**:
  - When the backend server is active, verify that a green dot/indicator with `Connected to localhost:8000` is displayed at the footer.
  - Stop the backend server. Verify that the indicator turns red within 5 seconds, reading `Disconnected`.

---

## 4. Extension Logging & Local Storage
- [ ] **Storage Syncing**:
  - Log in to the extension.
  - In the Extension Console, run: `chrome.storage.local.get('sai_auth', console.log)`.
  - Verify that the returned object contains the valid token, username, and role.
- [ ] **Active Session State**:
  - While an interview is active (or simulated), run: `chrome.storage.local.get(['sai_cc_log', 'sai_cc_words'], console.log)`.
  - Verify that the local log contains array objects of captured transcript items.
