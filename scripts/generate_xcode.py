#!/usr/bin/env python3
"""Deterministic Xcode project; no package manager or generator installation needed."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
PROJECT = NATIVE / "Coral.xcodeproj"


def uid(value):
    return hashlib.sha1(value.encode()).hexdigest()[:24].upper()


objects = {}


def add(key, value):
    objects[uid(key)] = value
    return uid(key)


def ids(items):
    return "(" + ",".join(items) + ",)" if items else "()"


def ref(path, kind):
    return add(path, '{isa = PBXFileReference; lastKnownFileType = ' + kind + '; path = "' + path + '"; sourceTree = "<group>";}')


def main():
    asset = NATIVE / "Coral/Assets.xcassets"
    mascot = asset / "Mascot.imageset"
    mascot.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "assets/mascot.png", mascot / "mascot.png")
    (mascot / "Contents.json").write_text(json.dumps({"images": [{"filename": "mascot.png", "idiom": "universal"}], "info": {"version": 1, "author": "xcode"}}))
    (asset / "Contents.json").write_text(json.dumps({"info": {"version": 1, "author": "xcode"}}))
    source_refs = [ref(str(p.relative_to(NATIVE)), "sourcecode.swift") for p in sorted((NATIVE / "Coral").glob("*.swift"))]
    resource_ref = ref("Coral/Assets.xcassets", "folder.assetcatalog")
    test_ref = ref("CoralTests/CoralTests.swift", "sourcecode.swift")
    config_ref = ref("Config.xcconfig", "text.xcconfig")
    info_ref = ref("Coral/Info.plist", "text.plist.xml")
    targets = []
    products = []
    for platform, sdk, product_id in [("macOS", "macosx", "com.coral.workspace.mac"), ("iOS", "iphoneos", "com.coral.workspace.ios"), ("Tests", "macosx", "com.coral.workspace.tests")]:
        name = "Coral-" + platform
        is_test = platform == "Tests"
        extension = "xctest" if is_test else "app"
        product = add(name + "product", '{isa = PBXFileReference; explicitFileType = wrapper.' + ("cfbundle" if is_test else "application") + '; path = "' + name + '.' + extension + '"; sourceTree = BUILT_PRODUCTS_DIR;}')
        products.append(product)
        sources = []
        for source in ([test_ref] if is_test else source_refs):
            sources.append(add(name + source, '{isa = PBXBuildFile; fileRef = ' + source + ';}'))
        build_resource = add(name + "resource", '{isa = PBXBuildFile; fileRef = ' + resource_ref + ';}')
        source_phase = add(name + "sources", '{isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ' + ids(sources) + '; runOnlyForDeploymentPostprocessing = 0;}')
        resource_phase = add(name + "resources", '{isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ' + ids([] if is_test else [build_resource]) + '; runOnlyForDeploymentPostprocessing = 0;}')
        frameworks = add(name + "frameworks", '{isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0;}')
        configs = []
        for mode in ["Debug", "Release"]:
            settings = 'PRODUCT_NAME = "$(TARGET_NAME)"; PRODUCT_MODULE_NAME = Coral; PRODUCT_BUNDLE_IDENTIFIER = ' + product_id + '; SDKROOT = ' + sdk + '; SWIFT_VERSION = 5.0; MACOSX_DEPLOYMENT_TARGET = 14.0; IPHONEOS_DEPLOYMENT_TARGET = 17.0; CODE_SIGN_STYLE = Automatic; SWIFT_EMIT_LOC_STRINGS = YES; ENABLE_USER_SCRIPT_SANDBOXING = YES; '
            if is_test:
                settings += 'GENERATE_INFOPLIST_FILE = YES; BUNDLE_LOADER = "$(TEST_HOST)"; TEST_HOST = "$(BUILT_PRODUCTS_DIR)/Coral-macOS.app/Contents/MacOS/Coral-macOS"; PRODUCT_MODULE_NAME = CoralTests;'
            else:
                settings += 'INFOPLIST_FILE = Coral/Info.plist; GENERATE_INFOPLIST_FILE = NO; ENABLE_APP_SANDBOX = NO; '
            if platform == "iOS":
                settings += 'TARGETED_DEVICE_FAMILY = "1,2"; SUPPORTED_PLATFORMS = "iphoneos iphonesimulator"; '
            else:
                settings += 'SUPPORTED_PLATFORMS = macosx; '
            settings += 'SWIFT_OPTIMIZATION_LEVEL = ' + ('"-Onone"' if mode == "Debug" else '"-O"') + ';'
            if mode == "Debug":
                settings += 'ENABLE_TESTABILITY = YES;'
            if not is_test:
                settings += 'ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;'
            configs.append(add(name + mode, '{isa = XCBuildConfiguration; baseConfigurationReference = ' + config_ref + '; buildSettings = {' + settings + '}; name = ' + mode + ';}'))
        config_list = add(name + "configs", '{isa = XCConfigurationList; buildConfigurations = ' + ids(configs) + '; defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;}')
        dependencies = []
        if is_test:
            proxy = add("testProxy", '{isa = PBXContainerItemProxy; containerPortal = ' + uid("project") + '; proxyType = 1; remoteGlobalIDString = ' + uid("Coral-macOStarget") + '; remoteInfo = "Coral-macOS";}')
            dependencies.append(add("testDependency", '{isa = PBXTargetDependency; target = ' + uid("Coral-macOStarget") + '; targetProxy = ' + proxy + ';}'))
        targets.append(add(name + "target", '{isa = PBXNativeTarget; buildConfigurationList = ' + config_list + '; buildPhases = ' + ids([source_phase, frameworks, resource_phase]) + '; buildRules = (); dependencies = ' + ids(dependencies) + '; name = "' + name + '"; productName = "' + name + '"; productReference = ' + product + '; productType = "com.apple.product-type.' + ('bundle.unit-test' if is_test else 'application') + '";}'))
    products_group = add("products", '{isa = PBXGroup; children = ' + ids(products) + '; name = Products; sourceTree = "<group>";}')
    main_group = add("main", '{isa = PBXGroup; children = ' + ids(source_refs + [resource_ref, test_ref, config_ref, info_ref, products_group]) + '; sourceTree = "<group>";}')
    project_configs = [add("project" + mode, '{isa = XCBuildConfiguration; buildSettings = {CLANG_ENABLE_MODULES = YES;}; name = ' + mode + ';}') for mode in ["Debug", "Release"]]
    project_config_list = add("projectConfigs", '{isa = XCConfigurationList; buildConfigurations = ' + ids(project_configs) + '; defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;}')
    add("project", '{isa = PBXProject; attributes = {LastUpgradeCheck = 2700;}; buildConfigurationList = ' + project_config_list + '; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; hasScannedForEncodings = 0; knownRegions = (en,Base,); mainGroup = ' + main_group + '; productRefGroup = ' + products_group + '; projectDirPath = ""; projectRoot = ""; targets = ' + ids(targets) + ';}')
    PROJECT.mkdir(exist_ok=True)
    (PROJECT / "project.pbxproj").write_text('// !$*UTF8*$!\n{archiveVersion = 1; classes = {}; objectVersion = 56; objects = {\n' + '\n'.join(k + ' = ' + v + ';' for k, v in objects.items()) + '\n}; rootObject = ' + uid("project") + ';}\n')
    schemes = PROJECT / "xcshareddata/xcschemes"
    schemes.mkdir(parents=True, exist_ok=True)
    for platform in ["macOS", "iOS"]:
        name = "Coral-" + platform
        reference = '<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="' + uid(name + "target") + '" BuildableName="' + name + '.app" BlueprintName="' + name + '" ReferencedContainer="container:Coral.xcodeproj"/>'
        test = '<Testables><TestableReference skipped="NO"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="' + uid("Coral-Teststarget") + '" BuildableName="Coral-Tests.xctest" BlueprintName="Coral-Tests" ReferencedContainer="container:Coral.xcodeproj"/></TestableReference></Testables>' if platform == "macOS" else '<Testables/>'
        (schemes / (name + ".xcscheme")).write_text('<?xml version="1.0" encoding="UTF-8"?><Scheme LastUpgradeVersion="2700" version="1.3"><BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">' + reference + '</BuildActionEntry></BuildActionEntries></BuildAction><TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES">' + test + '</TestAction><LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0"><BuildableProductRunnable runnableDebuggingMode="0">' + reference + '</BuildableProductRunnable></LaunchAction><ProfileAction buildConfiguration="Release"><BuildableProductRunnable runnableDebuggingMode="0">' + reference + '</BuildableProductRunnable></ProfileAction><AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/></Scheme>')
    print(PROJECT)


if __name__ == "__main__":
    main()
