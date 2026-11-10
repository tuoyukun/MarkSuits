// Mark menu bar app: runs the board server (`mark board --serve`) while it runs, shows how many
// gates wait on the human, and offers Open / Preferences / Quit. Built by Formula/marksuits.rb,
// which writes Info.plist with MarkCLI (the `mark` to run) and MarkApp (this binary, by its
// stable opt path, for the login item). macOS only; AppKit + Foundation, no dependencies.
import AppKit

let bundleID = "com.marksuits.mark"
let info = Bundle.main.infoDictionary ?? [:]
let markCLI = info["MarkCLI"] as? String ?? "/opt/homebrew/bin/mark"
let appBinary = info["MarkApp"] as? String ?? Bundle.main.executablePath ?? ""
let markVersion = info["CFBundleShortVersionString"] as? String ?? "?"
let loginPlist = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/LaunchAgents/\(bundleID).plist")

func markHome() -> URL {
    if let h = ProcessInfo.processInfo.environment["MARK_HOME"], !h.isEmpty { return URL(fileURLWithPath: h) }
    return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".mark")
}

/// `mark <args>` outside any project, with the PATH a login item lacks (claude, git, node).
func mark(_ args: [String], wait: Bool = true, service: Bool = false) -> Process {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: markCLI)
    p.arguments = args
    p.currentDirectoryURL = URL(fileURLWithPath: "/")
    var env = ProcessInfo.processInfo.environment
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    env["PATH"] = ["\(home)/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"].joined(separator: ":")
    if service { env["MARK_SERVICE"] = "app" }  // only the board this app runs: it exits when the app does
    p.environment = env
    try? p.run()
    if wait { p.waitUntilExit() }
    return p
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var board: Process?
    var quitting = false
    var update: [String: Any]?
    var port: Int?
    var prefs: NSWindow?
    var loginBox: NSButton?
    var noteLabel: NSTextField?

    func applicationDidFinishLaunching(_ note: Notification) {
        if NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).count > 1 {
            NSApp.terminate(nil)  // one Mark per user
            return
        }
        item.button?.image = NSImage(systemSymbolName: "checklist", accessibilityDescription: "Mark")
        item.button?.image?.isTemplate = true
        item.button?.imagePosition = .imageLeading
        let menu = NSMenu()
        menu.addItem(withTitle: "Open", action: #selector(open), keyEquivalent: "o")
        menu.addItem(withTitle: "Preferences…", action: #selector(showPrefs), keyEquivalent: ",")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Mark", action: #selector(quit), keyEquivalent: "q")
        item.menu = menu
        _ = mark(["board", "--stop"])  // a board a Claude session started: this app runs it from now on
        startBoard()
        Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
        poll()
    }

    func startBoard() {
        let p = mark(["board", "--serve"], wait: false, service: true)
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) {  // keep it alive, unless quitting
                guard let self, !self.quitting else { return }
                self.startBoard()
            }
        }
        board = p
    }

    /// The live board's port (MARK_HOME/board.json), then the home's cards: gates waiting on the human.
    func poll() {
        guard let data = try? Data(contentsOf: markHome().appendingPathComponent("board.json")),
              let st = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let port = st["port"] as? Int,
              let url = URL(string: "http://127.0.0.1:\(port)/api/projects") else { return show(nil) }
        self.port = port
        URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
            let obj = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            DispatchQueue.main.async {
                guard let self, let obj else { self?.show(nil); return }
                self.update = obj["update"] as? [String: Any]
                let human = (obj["projects"] as? [[String: Any]] ?? []).reduce(0) { $0 + ($1["human"] as? Int ?? 0) }
                self.show(human)
            }
        }.resume()
    }

    func show(_ human: Int?) {
        item.button?.title = (human ?? 0) > 0 ? " \(human!)" : ""
        item.button?.toolTip = human == nil ? "Mark: board starting…"
            : human! > 0 ? "Mark: \(human!) waiting on you" : "Mark: nothing waits on you"
        noteLabel?.stringValue = prefsNote()
    }

    @objc func open() { _ = mark(["board"], wait: false) }  // opens the browser signed in

    @objc func quit() {
        quitting = true
        board?.terminate()
        board?.waitUntilExit()
        NSApp.terminate(nil)
    }

    // MARK: Preferences

    func prefsNote() -> String {
        var lines = ["Mark \(markVersion)" + (port.map { " · board on 127.0.0.1:\($0)" } ?? "")]
        if let u = update, let cmd = u["cmd"] as? String {
            let plugin = u["plugin"] as? String ?? ""
            lines.append(plugin.isEmpty ? "The Claude plugin is not installed. Run:" : "The Claude plugin is \(plugin). Run:")
            lines.append(cmd)
        }
        return lines.joined(separator: "\n")
    }

    @objc func showPrefs() {
        if prefs == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 440, height: 150), styleMask: [.titled, .closable],
                             backing: .buffered, defer: false)
            w.title = "Mark Preferences"
            w.isReleasedWhenClosed = false
            let box = NSButton(checkboxWithTitle: "Launch Mark at login", target: self, action: #selector(toggleLogin))
            let label = NSTextField(wrappingLabelWithString: "")
            label.isSelectable = true
            label.textColor = .secondaryLabelColor
            let stack = NSStackView(views: [box, label])
            stack.orientation = .vertical
            stack.alignment = .leading
            stack.spacing = 12
            stack.edgeInsets = NSEdgeInsets(top: 20, left: 20, bottom: 20, right: 20)
            w.contentView = stack
            label.widthAnchor.constraint(equalToConstant: 400).isActive = true
            (prefs, loginBox, noteLabel) = (w, box, label)
            w.center()
        }
        loginBox?.state = FileManager.default.fileExists(atPath: loginPlist.path) ? .on : .off
        noteLabel?.stringValue = prefsNote()
        NSApp.activate(ignoringOtherApps: true)
        prefs?.makeKeyAndOrderFront(nil)
    }

    /// A per-user LaunchAgent that starts this app at login; unchecking removes it.
    @objc func toggleLogin(_ sender: NSButton) {
        if sender.state == .on {
            let plist: [String: Any] = ["Label": bundleID, "ProgramArguments": [appBinary], "RunAtLoad": true,
                                        "ProcessType": "Interactive"]
            try? FileManager.default.createDirectory(at: loginPlist.deletingLastPathComponent(), withIntermediateDirectories: true)
            let ok = (try? PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0))
                .map { (try? $0.write(to: loginPlist)) != nil } ?? false
            if !ok { sender.state = .off }
        } else {
            try? FileManager.default.removeItem(at: loginPlist)
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)  // menu bar only, no Dock icon
app.run()
