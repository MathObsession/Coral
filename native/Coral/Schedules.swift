import SwiftUI

struct SchedulesView: View {
    @EnvironmentObject var store: CoralStore
    @State private var editing: ScheduledTask?
    @State private var showEditor = false
    @State private var filter = "All"
    var filtered: [ScheduledTask] { store.schedules.filter { filter == "All" || (filter == "Active" ? $0.paused == 0 : $0.paused == 1) } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 18) {
                    Label("Let your ideas keep moving.", systemImage: "calendar.badge.clock").font(.title2.bold())
                    Text("Coral wakes your Codespace, runs Hermes, saves the result, and puts your workspace back to sleep.").foregroundStyle(CoralTheme.muted)
                    Button { editing = nil; showEditor = true } label: { Label("New schedule", systemImage: "plus.circle.fill") }.buttonStyle(TactileButtonStyle(color: CoralTheme.green))
                }.coralCard()
                Picker("Filter", selection: $filter) { ForEach(["All", "Active", "Paused"], id: \.self) { Text($0).tag($0) } }.pickerStyle(.segmented)
                ForEach(filtered) { schedule in
                    VStack(alignment: .leading, spacing: 18) {
                        HStack { Image(systemName: "calendar").foregroundStyle(CoralTheme.blue); Text(schedule.title).font(.headline); Spacer(); StatusBadge(state: schedule.paused == 1 ? "paused" : "active") }
                        Text(schedule.prompt).lineLimit(3).foregroundStyle(CoralTheme.muted)
                        Text("\(schedule.recurrence.capitalized) · \(Date(timeIntervalSince1970: schedule.nextRun).formatted())").font(.caption.bold())
                        Text("Duration limit: \(TimeFormat.duration(Double(schedule.durationLimit)))").font(.caption).foregroundStyle(CoralTheme.muted)
                        HStack {
                            Button("Edit") { editing = schedule; showEditor = true }.buttonStyle(TactileButtonStyle(color: .white))
                            Button(schedule.paused == 1 ? "Resume" : "Pause") { toggle(schedule) }.buttonStyle(TactileButtonStyle(color: schedule.paused == 1 ? CoralTheme.green : CoralTheme.orange))
                            Spacer()
                            Button(role: .destructive) { remove(schedule) } label: { Image(systemName: "trash") }.accessibilityLabel("Delete schedule")
                        }.disabled(store.busy)
                    }.coralCard()
                }
                if filtered.isEmpty { EmptyCard(symbol: "calendar", title: "No schedules yet", detail: "Set a one-time, daily, weekly, or recurring task. Times run in UTC; the picker shows your local time.") }
                Text("Execution history").font(.title2.bold())
                ForEach(store.tasks.filter { $0.scheduleId != nil }) { task in TaskCard(task: task) }
            }.padding(24).frame(maxWidth: 1000).frame(maxWidth: .infinity)
        }.background(CoralTheme.canvas).sheet(isPresented: $showEditor) { ScheduleEditor(schedule: editing).environmentObject(store) }
    }
    func toggle(_ schedule: ScheduledTask) { var body = schedule.body; body["paused"] = schedule.paused == 0; store.perform { _ = try await store.api.raw(store.root + "/schedules/" + schedule.id, method: "PUT", body: body) } }
    func remove(_ schedule: ScheduledTask) { store.perform { _ = try await store.api.raw(store.root + "/schedules/" + schedule.id, method: "DELETE") } }
}

struct ScheduleEditor: View {
    @EnvironmentObject var store: CoralStore
    @Environment(\.dismiss) var dismiss
    let schedule: ScheduledTask?
    @State var title = ""
    @State var prompt = ""
    @State var recurrence = "once"
    @State var date = Date().addingTimeInterval(3600)
    @State var interval = 60
    @State var duration = 15
    var body: some View {
        NavigationStack {
            Form {
                Section("Task") { TextField("Name", text: $title); TextField("What should Hermes do?", text: $prompt, axis: .vertical).lineLimit(3...8) }
                Section("Timing") {
                    Picker("Repeat", selection: $recurrence) { ForEach(["once", "daily", "weekly", "recurring"], id: \.self) { Text($0.capitalized).tag($0) } }
                    DatePicker("Next run", selection: $date)
                    if recurrence == "recurring" { Stepper("Every \(interval) minutes", value: $interval, in: 5...10080, step: 5) }
                    Stepper("Stop after \(duration) minutes", value: $duration, in: 1...120)
                }
                Section { Text("Daily and weekly repeats use fixed UTC intervals. They may shift by one local hour when daylight saving changes. Scheduled work waits until your interactive session ends.").font(.caption).foregroundStyle(CoralTheme.muted) }
            }.navigationTitle(schedule == nil ? "New schedule" : "Edit schedule")
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Save") { save() }.disabled(title.isEmpty || prompt.isEmpty || store.busy)
                    }
                }.onAppear { if let schedule { title = schedule.title; prompt = schedule.prompt; recurrence = schedule.recurrence; date = Date(timeIntervalSince1970: schedule.nextRun); interval = schedule.intervalSeconds / 60; duration = schedule.durationLimit / 60 } }
        }
        #if os(macOS)
        .frame(width: 580, height: 560)
        #endif
    }
    func save() {
        let path = store.root + "/schedules" + (schedule.map { "/" + $0.id } ?? "")
        store.perform {
            _ = try await store.api.raw(path, method: schedule == nil ? "POST" : "PUT", body: ["title": title, "prompt": prompt, "recurrence": recurrence, "next_run": date.timeIntervalSince1970, "interval_seconds": max(300, interval * 60), "duration_limit": duration * 60, "paused": schedule?.paused == 1])
            dismiss()
        }
    }
}
