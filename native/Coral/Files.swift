import SwiftUI

struct FilesView: View {
    @EnvironmentObject var store: CoralStore
    @State private var directory = ""
    @State private var files: [WorkspaceFile] = []
    @State private var selected: String?
    @State private var content = ""
    @State private var original = ""
    @State private var newName = ""
    @State private var loading = false
    @State private var showingEditor = false
    @State private var pendingFile: WorkspaceFile?
    @State private var unsaved = false
    @State private var editorProfileId = ""
    var body: some View {
        Group {
            if store.profile?.ready != true { EmptyCard(symbol: "folder", title: "Your files are sleeping safely", detail: "Start your workspace to browse and edit the repository.").padding(24) }
            else {
                #if os(macOS)
                HSplitView { browser.frame(minWidth: 240, idealWidth: 300, maxWidth: 400); editor.frame(minWidth: 400) }
                #else
                browser.sheet(isPresented: $showingEditor) { NavigationStack { editor.navigationTitle(selected?.split(separator: "/").last.map(String.init) ?? "Editor").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { if content != original { unsaved = true } else { showingEditor = false } } } } }.interactiveDismissDisabled(content != original) }
                #endif
            }
        }.background(CoralTheme.canvas)
            .onAppear {
                editorProfileId = store.selectedId
                if let draft = store.editorDrafts[store.selectedId] {
                    selected = draft.path; content = draft.content; original = draft.original
                }
            }
            .onDisappear {
                persistDraft()
            }
            .onChange(of: store.selectedId) { _, newId in
                persistDraft(); editorProfileId = newId; directory = ""; files = []
                if let draft = store.editorDrafts[newId] { selected = draft.path; content = draft.content; original = draft.original }
                else { selected = nil; content = ""; original = "" }
            }
            .task(id: store.selectedId + directory + (store.profile?.state ?? "")) { await load() }
            .confirmationDialog("Discard unsaved changes?", isPresented: $unsaved, titleVisibility: .visible) {
                Button("Discard changes", role: .destructive) { if let file = pendingFile { Task { await open(file) }; pendingFile = nil } else { showingEditor = false }; content = original }
                Button("Keep editing", role: .cancel) { pendingFile = nil }
            }
    }
    var browser: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Button { directory = directory.split(separator: "/").dropLast().joined(separator: "/"); store.interaction("file") } label: { Image(systemName: "arrow.up") }.disabled(directory.isEmpty)
                Text(directory.isEmpty ? "Workspace" : directory).font(.headline).lineLimit(1)
                Spacer(); Button { Task { await load() }; store.interaction("file") } label: { Image(systemName: "arrow.clockwise") }.accessibilityLabel("Refresh files")
            }.padding(.horizontal, 16)
            List(files) { file in
                Button {
                    if content != original { pendingFile = file; unsaved = true }
                    else { Task { await open(file) } }
                } label: { HStack { Image(systemName: file.directory ? "folder.fill" : "doc.text").foregroundStyle(file.directory ? CoralTheme.orange : CoralTheme.blue); Text(file.name).lineLimit(1); Spacer() }.padding(.vertical, 8) }.buttonStyle(.plain)
            }.listStyle(.plain)
            HStack { TextField("New file name", text: $newName); Button("Create") { selected = [directory, newName].filter { !$0.isEmpty }.joined(separator: "/"); content = ""; original = ""; showingEditor = true; newName = "" }.disabled(newName.isEmpty) }.padding(16)
            if loading { ProgressView().padding() }
        }.padding(.top, 20)
    }
    var editor: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Text(selected ?? "Select a file").font(.headline).lineLimit(1); Spacer(); if content != original { Text("Unsaved").font(.caption).foregroundStyle(CoralTheme.orange) }; Button("Save") { save() }.buttonStyle(TactileButtonStyle(color: CoralTheme.green)).disabled(selected == nil || store.busy) }
            if selected != nil {
                TextEditor(text: $content).font(.system(size: 14, design: .monospaced)).scrollContentBackground(.hidden).padding(12).background(.white, in: RoundedRectangle(cornerRadius: 16))
                    .onChange(of: content) { _, _ in store.interaction("file") }
            } else { EmptyCard(symbol: "doc.text", title: "A place for your work", detail: "Open a UTF-8 file from the browser, or create a new one.") }
            Text("UTF-8 · up to 1 MB · saved in your Codespace").font(.caption).foregroundStyle(CoralTheme.muted)
        }.padding(22)
    }
    func load() async {
        guard store.profile?.ready == true else { files = []; return }
        let loadingProfileId = store.selectedId
        let loadingRoot = store.root
        loading = true; defer { loading = false }
        do {
            var parts = URLComponents(); parts.queryItems = [URLQueryItem(name: "path", value: directory)]
            let response: FilesResponse = try await store.api.request(loadingRoot + "/files?" + (parts.percentEncodedQuery ?? ""))
            guard store.selectedId == loadingProfileId else { return }
            files = response.files
        } catch { store.error = error.localizedDescription }
    }
    func open(_ file: WorkspaceFile) async {
        store.interaction("file")
        if file.directory { directory = file.path; return }
        do {
            let openingProfileId = store.selectedId
            var parts = URLComponents(); parts.queryItems = [URLQueryItem(name: "path", value: file.path)]
            let response: FileResponse = try await store.api.request(store.root + "/file?" + (parts.percentEncodedQuery ?? ""))
            guard store.selectedId == openingProfileId else { return }
            selected = file.path; content = response.content; original = response.content; showingEditor = true
        } catch { store.error = error.localizedDescription }
    }
    func save() {
        guard let selected else { return }
        let snapshot = content
        store.perform {
            _ = try await store.api.raw(store.root + "/file", method: "PUT", body: ["path": selected, "content": snapshot])
            original = snapshot; await load()
        }
    }
    func persistDraft() {
        if let selected, !editorProfileId.isEmpty { store.editorDrafts[editorProfileId] = (selected, content, original) }
    }
}
