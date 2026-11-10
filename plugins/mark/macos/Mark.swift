// Mark menu bar app: runs the board server (`mark board --serve`) while it runs, shows how many
// gates wait on the human, and offers Open / Check for Updates / Preferences / Quit. Once a day (or on
// Check for Updates, which reports the result) it updates the Claude
// plugin (`mark app update`); when that moved, it rebuilds itself from the new plugin and restarts
// the board once no session runs. Built by `mark app install` (lib/mark/app.py), which writes
// Info.plist with MarkCLI (the launcher, ~/.local/bin/mark) and MarkApp (this binary, for the
// login item). macOS only; AppKit + Foundation, no dependencies.
import AppKit

let bundleID = "com.marksuits.mark"
let info = Bundle.main.infoDictionary ?? [:]
let markCLI = info["MarkCLI"] as? String
    ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin/mark").path
let appBinary = info["MarkApp"] as? String ?? Bundle.main.executablePath ?? ""
let markVersion = info["CFBundleShortVersionString"] as? String ?? "?"
let loginPlist = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/LaunchAgents/\(bundleID).plist")

func markHome() -> URL {
    if let h = ProcessInfo.processInfo.environment["MARK_HOME"], !h.isEmpty { return URL(fileURLWithPath: h) }
    return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".mark")
}

/// `mark <args>` outside any project, with the PATH a login item lacks (claude, git, node).
func mark(_ args: [String], wait: Bool = true, service: Bool = false, output: Pipe? = nil) -> Process {
    let p = Process()
    if let output { p.standardOutput = output; p.standardError = output }
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

/// `mark --version`: the plugin the launcher runs right now.
func markVersionNow() -> String {
    let pipe = Pipe()
    _ = mark(["--version"], output: pipe)
    return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
}

/// The board's logo: a dark rounded square with a white "M". Template (menu bar): the M is cut out.
func logo(_ side: CGFloat, template: Bool) -> NSImage {
    NSImage(size: NSSize(width: side, height: side), flipped: false) { r in
        let box = template ? r : r.insetBy(dx: side * 0.1, dy: side * 0.1)  // app icons keep the usual margin
        (template ? NSColor.black : NSColor(srgbRed: 0x1b / 255, green: 0x1b / 255, blue: 0x1f / 255, alpha: 1)).setFill()
        NSBezierPath(roundedRect: box, xRadius: box.width * 0.225, yRadius: box.width * 0.225).fill()
        if template { NSGraphicsContext.current?.compositingOperation = .destinationOut }
        let font = NSFont.systemFont(ofSize: box.height * 0.56, weight: .bold)
        let m = NSAttributedString(string: "M", attributes: [.font: font, .foregroundColor: NSColor.white])
        // centre the capital itself, not its line box (which includes the descender)
        m.draw(at: NSPoint(x: box.midX - m.size().width / 2, y: box.midY - font.capHeight / 2 + font.descender))
        return true
    }
}

/// `Mark --iconset <dir>`: the app icon as PNGs for iconutil (`mark app install` runs it at build time).
if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "--iconset" {
    let dir = URL(fileURLWithPath: CommandLine.arguments[2])
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    for pt in [16, 32, 128, 256, 512] {
        for scale in [1, 2] {
            let px = pt * scale
            let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8,
                                       samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                       colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
            logo(CGFloat(px), template: false).draw(in: NSRect(x: 0, y: 0, width: px, height: px))
            NSGraphicsContext.restoreGraphicsState()
            let name = "icon_\(pt)x\(pt)\(scale == 2 ? "@2x" : "").png"
            guard (try? rep.representation(using: .png, properties: [:])?.write(to: dir.appendingPathComponent(name))) != nil
            else { exit(1) }
        }
    }
    exit(0)
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var board: Process?
    var quitting = false
    var restartPending = false  // the plugin updated: restart the board once nothing runs
    var checking = false
    var port: Int?
    var prefs: NSWindow?
    var loginBox: NSButton?
    var noteLabel: NSTextField?

    func applicationDidFinishLaunching(_ note: Notification) {
        if NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).count > 1 {
            NSApp.terminate(nil)  // one Mark per user
            return
        }
        item.button?.image = logo(16, template: true)
        item.button?.image?.isTemplate = true
        item.button?.image?.accessibilityDescription = "Mark"
        item.button?.imagePosition = .imageLeading
        let menu = NSMenu()
        menu.addItem(withTitle: "Open", action: #selector(open), keyEquivalent: "o")
        menu.addItem(withTitle: "Check for Updates…", action: #selector(checkNow), keyEquivalent: "")
        menu.addItem(withTitle: "Preferences…", action: #selector(showPrefs), keyEquivalent: ",")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Mark", action: #selector(quit), keyEquivalent: "q")
        item.menu = menu
        _ = mark(["board", "--stop"])  // a board a Claude session started: this app runs it from now on
        startBoard()
        Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
        poll()
        DispatchQueue.main.asyncAfter(deadline: .now() + 60) { self.checkUpdate() }
        Timer.scheduledTimer(withTimeInterval: 24 * 3600, repeats: true) { [weak self] _ in self?.checkUpdate() }
    }

    @objc func checkNow() { checkUpdate(report: true) }

    /// Runs on the main thread; `report` shows what `mark app update` said.
    func checkUpdate(report: Bool = false) {
        guard !checking else { return }
        checking = true
        DispatchQueue.global(qos: .utility).async {
            let before = markVersionNow()
            let pipe = Pipe()
            _ = mark(["app", "update"], output: pipe)
            let said = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let after = markVersionNow()
            let moved = !after.isEmpty && after != before
            if moved { _ = mark(["app", "install", "--no-open"]) }  // the rebuilt app takes over at its next launch
            DispatchQueue.main.async {
                self.checking = false
                if moved { self.restartPending = true }
                guard report else { return }
                let alert = NSAlert()
                alert.messageText = moved ? "Mark updated to \(after)" : "Check for Updates"
                alert.informativeText = (said.isEmpty ? "No answer from `mark app update`." : said)
                    + (moved ? "\n\nThe board restarts on it once no session runs; this app at its next launch." : "")
                NSApp.activate(ignoringOtherApps: true)
                alert.runModal()
            }
        }
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
                let projects = obj["projects"] as? [[String: Any]] ?? []
                let human = projects.reduce(0) { $0 + ($1["human"] as? Int ?? 0) }
                self.show(human)
                if self.restartPending, !projects.contains(where: { $0["running"] as? Bool == true }) {
                    self.restartPending = false
                    self.board?.terminate()  // its termination handler starts the new plugin's board
                }
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
        "Mark \(markVersion)" + (port.map { " · board on 127.0.0.1:\($0)" } ?? "")
            + "\nUpdates the Claude plugin once a day."
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
