#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pytest backend/tests -q
node --test website/tests/*.test.cjs
node --check website/app.js
bash -n codespace/install.sh scripts/*.sh
if [ -d /Applications/Xcode.app/Contents/Developer ]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi
xcodebuild -project native/Coral.xcodeproj -scheme Coral-macOS -derivedDataPath build/native-mac -destination 'platform=macOS' CODE_SIGNING_ALLOWED=NO build-for-testing
xcodebuild -project native/Coral.xcodeproj -scheme Coral-iOS -sdk iphonesimulator -derivedDataPath build/native-ios -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
