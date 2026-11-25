#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
coral_device="${1:-}"
if [ -z "$coral_device" ]; then
  echo 'Pass an available iPhone simulator UUID from: xcrun simctl list devices available' >&2
  exit 1
fi
xcrun simctl boot "$coral_device" || true
xcrun simctl bootstatus "$coral_device" -b
xcodebuild -project native/Coral.xcodeproj -scheme Coral-iOS -sdk iphonesimulator -derivedDataPath build/native-ios -destination "id=$coral_device" CODE_SIGNING_ALLOWED=NO build
xcrun simctl install "$coral_device" build/native-ios/Build/Products/Debug-iphonesimulator/Coral-iOS.app
xcrun simctl launch "$coral_device" com.coral.workspace.ios
mkdir -p build/screenshots
xcrun simctl io "$coral_device" screenshot build/screenshots/iphone.png
echo 'Verify GitHub sign-in or Settings → Open local workspace; then connect owner/repo in Profiles.'
