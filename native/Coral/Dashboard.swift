import SwiftUI

struct HomeView: View {
    @EnvironmentObject var store: CoralStore
    @State private var extended = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                HStack(spacing: 22) {
                    Mascot(size: 92)
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Make room for your next idea.").font(.system(size: 27, weight: .heavy, design: .rounded))
                        Text("Your workspace is ready when you are.").foregroundStyle(CoralTheme.muted)
                    }
                }.coralCard(CoralTheme.cream)
                SessionControls()
                if let usage = store.usage {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 20) { QuotaCard(usage: usage); IdleCard(usage: usage, showExtended: $extended) }
                        VStack(spacing: 20) { QuotaCard(usage: usage); IdleCard(usage: usage, showExtended: $extended) }
                    }
                }
                HStack { Text("Coming up next").font(.title3.bold()); Spacer(); Image(systemName: "calendar").foregroundStyle(CoralTheme.blue) }
                if store.schedules.filter({ $0.paused == 0 }).isEmpty {
                    EmptyCard(symbol: "calendar.badge.plus", title: "Let Coral take the next shift", detail: "Add a scheduled task to run while you’re away. Results will be waiting in your workspace.")
                } else {
                    ForEach(Array(store.schedules.filter { $0.paused == 0 }.prefix(3))) { schedule in
                        HStack(spacing: 16) {
                            Image(systemName: "calendar").font(.title2).foregroundStyle(CoralTheme.blue)
                            VStack(alignment: .leading, spacing: 5) { Text(schedule.title).font(.headline); Text(Date(timeIntervalSince1970: schedule.nextRun), style: .date).font(.caption).foregroundStyle(CoralTheme.muted); Text(Date(timeIntervalSince1970: schedule.nextRun), style: .time).font(.caption) }
                            Spacer(); Text(schedule.recurrence.capitalized).font(.caption.bold()).foregroundStyle(CoralTheme.orange)
                        }.coralCard()
                    }
                }
                if !store.notifications.isEmpty {
                    Text("Your inbox").font(.title3.bold())
                    ForEach(Array(store.notifications.prefix(6))) { item in
                        HStack {
                            Image(systemName: item.read == 0 ? "envelope.badge.fill" : "envelope.open").foregroundStyle(CoralTheme.blue)
                            Text(item.title).font(.subheadline.bold()); Spacer()
                            if item.read == 0 { Button("Mark read") { store.perform { _ = try await store.api.raw("/notifications/" + item.id + "/read", method: "POST") } } }
                        }.coralCard()
                    }
                }
            }.padding(24).frame(maxWidth: 1100).frame(maxWidth: .infinity)
        }.background(CoralTheme.canvas).sheet(isPresented: $extended) { NavigationStack { ExtendedView().toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { extended = false } } } } }
    }
}

struct SessionControls: View {
    @EnvironmentObject var store: CoralStore
    @State private var showProfiles = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Label("Your Codespace", systemImage: "shippingbox.fill").font(.headline); Spacer(); StatusBadge(state: store.profile?.state ?? "unconfigured") }
            if let error = store.profile?.error, !error.isEmpty { Text(error).font(.caption).foregroundStyle(CoralTheme.red) }
            if let profile = store.profile, !profile.codespace.isEmpty {
                Text(profile.repository).font(.subheadline).foregroundStyle(CoralTheme.muted)
                HStack(spacing: 14) {
                    Button { store.command("start") } label: { Label("Resume workspace", systemImage: "play.fill") }
                        .buttonStyle(TactileButtonStyle(color: CoralTheme.green)).disabled(store.busy || profile.busy || profile.ready)
                    Button { store.command("stop") } label: { Label("Stop", systemImage: "stop.fill") }
                        .buttonStyle(TactileButtonStyle(color: .white)).disabled(store.busy || !(profile.ready || profile.busy))
                }
            } else if store.profile?.busy != true {
                Text("Create a starter workspace or connect an existing Codespace to install Hermes.").font(.subheadline).foregroundStyle(CoralTheme.muted)
                Button { showProfiles = true } label: { Label("Connect a Codespace", systemImage: "plus.circle.fill") }
                    .buttonStyle(TactileButtonStyle(color: CoralTheme.green)).disabled(store.profile == nil)
            }
            if store.profile?.busy == true {
                ProgressView(store.profile?.state == "stopping" ? "Stopping your Codespace…" : "Starting your Codespace and preparing Hermes…")
                    .font(.subheadline)
            }
            if let usage = store.usage {
                HStack { Label("Session \(TimeFormat.duration(usage.sessionSeconds))", systemImage: "clock"); Spacer(); Text("4-hour daily limit").foregroundStyle(CoralTheme.muted) }.font(.caption.bold())
            }
        }.coralCard()
            .sheet(isPresented: $showProfiles) {
                NavigationStack {
                    ProfilesView().navigationTitle("Connect a Codespace")
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showProfiles = false } } }
                }
                #if os(macOS)
                .frame(minWidth: 580, minHeight: 490)
                #endif
            }
    }
}

struct QuotaCard: View {
    let usage: Usage
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Daily allowance", systemImage: "hourglass").font(.headline)
            Text(TimeFormat.duration(usage.remainingSeconds)).font(.system(size: 32, weight: .heavy, design: .rounded)).foregroundStyle(Color(hex: 0x46A302))
            Text("remaining of 4 hours").font(.subheadline).foregroundStyle(CoralTheme.muted)
            ProgressView(value: usage.remainingSeconds, total: usage.allowanceSeconds).tint(CoralTheme.green)
            Text("\(TimeFormat.duration(usage.usedSeconds)) used · resets at 00:00 UTC").font(.caption.bold()).foregroundStyle(CoralTheme.muted)
        }.frame(minWidth: 260).coralCard()
    }
}

struct IdleCard: View {
    let usage: Usage
    @Binding var showExtended: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(usage.extendedUntil == nil ? "Time until inactivity" : "Extended mode", systemImage: "timer").font(.headline)
            Text(usage.session == nil ? "Sleeping" : TimeFormat.countdown(usage.inactivitySeconds)).font(.system(size: 32, weight: .heavy, design: .rounded)).foregroundStyle(CoralTheme.orange)
            Text(usage.extendedUntil == nil ? "Coral sleeps after 10 minutes without interaction." : "Inactivity timeout is paused until your extension expires.").font(.subheadline).foregroundStyle(CoralTheme.muted)
            Button("Extended mode") { showExtended = true }.buttonStyle(TactileButtonStyle()).disabled(usage.session == nil)
        }.frame(minWidth: 260).coralCard(CoralTheme.cream)
    }
}

struct UsageView: View {
    @EnvironmentObject var store: CoralStore
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let usage = store.usage {
                    QuotaCard(usage: usage)
                    Text("Session history").font(.title2.bold())
                    Text("This account’s four-hour allowance is shared across profiles. Only one profile runs at a time.").foregroundStyle(CoralTheme.muted)
                    ForEach(usage.history) { session in
                        HStack {
                            VStack(alignment: .leading, spacing: 7) {
                                Text(Date(timeIntervalSince1970: session.started), style: .date).font(.headline)
                                Text(session.mode.capitalized + " · " + (session.ended == nil ? "In progress" : session.reason.replacingOccurrences(of: "_", with: " "))).font(.caption).foregroundStyle(CoralTheme.muted)
                            }
                            Spacer()
                            Text(TimeFormat.duration((session.ended ?? usage.serverTime) - session.started)).font(.headline)
                        }.coralCard()
                    }
                    if usage.history.isEmpty { EmptyCard(symbol: "chart.bar", title: "A fresh start", detail: "Your sessions and scheduled work will appear here.") }
                    Text("Recent daily usage for this profile").font(.headline)
                    ForEach(usage.daily, id: \.day) { day in HStack { Text(day.day); Spacer(); Text(TimeFormat.duration(day.seconds)) }.coralCard() }
                }
            }.padding(24).frame(maxWidth: 900).frame(maxWidth: .infinity)
        }.background(CoralTheme.canvas)
    }
}

struct ExtendedView: View {
    @EnvironmentObject var store: CoralStore
    @State private var minutes = 30
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Image(systemName: "timer").font(.system(size: 48)).foregroundStyle(CoralTheme.orange)
                Text("A little more breathing room.").font(.largeTitle.bold())
                Text("Keep your workspace awake while you step away. Choose a duration up to two hours; Coral still stops before your daily allowance runs out.").foregroundStyle(CoralTheme.muted)
                Picker("Keep awake for", selection: $minutes) { ForEach([15, 30, 60, 90, 120], id: \.self) { Text("\($0) minutes").tag($0) } }.pickerStyle(.menu)
                if let until = store.usage?.extendedUntil { Label("Expires \(Date(timeIntervalSince1970: until).formatted(date: .omitted, time: .shortened))", systemImage: "clock.fill").font(.headline) }
                Button("Enable extended mode") { store.command("extended", body: ["seconds": minutes * 60]) }.buttonStyle(TactileButtonStyle()).disabled(store.busy || store.profile?.ready != true)
                Button("Return to normal mode") { store.command("extended", body: ["seconds": 0]) }.buttonStyle(TactileButtonStyle(color: .white)).disabled(store.busy || store.usage?.extendedUntil == nil)
            }.coralCard(CoralTheme.cream).padding(24).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }.background(CoralTheme.canvas)
    }
}
