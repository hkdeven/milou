#!/bin/bash
# Install Milou as a Mac application.
#
# Builds a double-clickable Milou.app, and optionally a login item that keeps it
# running. Everything stays on this machine: the app binds 127.0.0.1, the
# tokens live in your Keychain, and nothing is published anywhere.
#
#   ./mac/install.sh              install the app
#   ./mac/install.sh --login-item also start it when you log in
#   ./mac/install.sh --uninstall  remove both

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$HOME/Applications/Milou.app"
AGENT="$HOME/Library/LaunchAgents/com.milou.console.plist"
CONFIG="$HOME/.milou/console.json"
PORT="${MILOU_PORT:-8080}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer is for macOS. On anything else, run:" >&2
  echo "  python3 -m milou_news.cli serve --config console.json --open" >&2
  exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl unload "$AGENT" 2>/dev/null || true
  rm -f "$AGENT"
  rm -rf "$APP"
  echo "Removed Milou.app and the login item."
  echo "Your configuration in $CONFIG and your Keychain sign-ins were left alone."
  echo "To remove those too: rm -rf ~/.milou  &&  python3 -m milou_news.cli login forget"
  exit 0
fi

PYTHON="$(command -v python3 || true)"
if [[ -z "$PYTHON" ]]; then
  echo "python3 was not found. Install it from python.org or with: xcode-select --install" >&2
  exit 1
fi

# --- configuration -----------------------------------------------------------
mkdir -p "$HOME/.milou"
if [[ ! -f "$CONFIG" ]]; then
  cp "$REPO/console.example.json" "$CONFIG"
  chmod 600 "$CONFIG"
  echo "Wrote a starting configuration to $CONFIG"
  echo "  Fill in your Zoho portal, project and statuses before enabling writes."
fi

# --- the application bundle --------------------------------------------------
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Milou</string>
  <key>CFBundleDisplayName</key><string>Milou</string>
  <key>CFBundleIdentifier</key><string>com.milou.console</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Milou</string>
  <!-- No Dock icon and no menu bar: this opens a browser tab and gets out of
       the way, rather than pretending to be a window it does not have. -->
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/Milou" <<LAUNCHER
#!/bin/bash
# Start the console if it is not already running, then open it signed in.
set -euo pipefail
REPO="$REPO"
PORT="$PORT"
cd "\$REPO"

if /usr/bin/nc -z 127.0.0.1 "\$PORT" 2>/dev/null; then
  # Already running: just open it. The browser will ask for the password,
  # which is in your Keychain under "milou".
  open "http://127.0.0.1:\$PORT/"
  exit 0
fi

exec "$PYTHON" -m milou_news.cli serve --config "$CONFIG" --port "\$PORT" --open \
  >> "\$HOME/.milou/console.log" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/Milou"

echo "Installed $APP"

# --- optional login item -----------------------------------------------------
if [[ "${1:-}" == "--login-item" ]]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.milou.console</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-m</string>
    <string>milou_news.cli</string>
    <string>serve</string>
    <string>--config</string><string>$CONFIG</string>
    <string>--port</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/.milou/console.log</string>
  <key>StandardErrorPath</key><string>$HOME/.milou/console.log</string>
</dict>
</plist>
PLIST
  launchctl unload "$AGENT" 2>/dev/null || true
  launchctl load "$AGENT"
  echo "Installed the login item; Milou will start when you log in."
fi

cat <<NEXT

Next:
  1. open $APP            (or find Milou in ~/Applications)
  2. $PYTHON -m milou_news.cli login outlook --config $CONFIG
  3. $PYTHON -m milou_news.cli login zoho    --config $CONFIG

Until you sign in, every routine reads the committed fixtures and every action
is a rehearsal that changes nothing. docs/going-live.md has the rest.
NEXT
